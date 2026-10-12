"""Crossing classification: safe synchronizers vs unsafe crossings.

Per destination-domain flop, every cross-domain source is classified:

* ``SAFE_SYNCHRONIZER`` — single-bit source sampled through an exact
  two-flop chain (``s1 <= X; s2 <= s1``) with no bypass: nothing else in
  the destination domain consumes ``X`` or ``s1``.
* ``UNSAFE_DIRECT`` — single-bit source sampled with no chain.
* ``UNSAFE_BYPASS`` — a chain exists, but the raw source (or the first
  stage) is also consumed elsewhere in the destination domain.
* ``MULTIBIT_UNPROVEN`` — bus crossing without a proven handshake/FIFO.
  Per-bit synchronizers do not make a coherent multi-bit transfer safe.
* ``UNPROVEN_FIFO`` — dual-clock FIFO-like structure the checker cannot
  prove (names/pointers suggest a FIFO but the Gray-pointer + sync proof
  is incomplete). Never PASS.
* ``RESET_CROSSING`` — reset-involved crossing the checker cannot prove.
* ``UNKNOWN`` — unknown-domain drivers or instance boundaries in the cone.

Handshake directions are evaluated independently: a valid chain each way
classifies each direction on its own merits. Bundled data riding a
handshake without its own proof stays INCONCLUSIVE.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .clocks import DomainMap, is_reset_name
from .crossings import Analysis, RawCrossing, comb_cone
from .parser import Module


@dataclass
class ClassifiedCrossing:
    source: str
    source_domain: str | None
    destination: str
    destination_domain: str
    path: list[str]
    classification: str
    severity: str  # error | inconclusive | ok
    detail: str = ""


@dataclass
class Verdict:
    status: str  # PASS | FAIL | INCONCLUSIVE
    crossings: list[ClassifiedCrossing] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _consumers(module: Module, signals: set[str], domain: str, domain_map: DomainMap) -> set[str]:
    """Destination-domain flops whose combinational cone includes signals."""
    users: set[str] = set()
    for block in module.always_blocks:
        if block.kind != "seq":
            continue
        for driver in block.drivers:
            if domain_map.domains.get(driver.lhs) != domain:
                continue
            if signals & comb_cone(module, driver.rhs_ids):
                users.add(driver.lhs)
    return users


def _width_of(module: Module, sig: str) -> int:
    return module.widths.get(sig, 1)


def classify(module: Module, domain_map: DomainMap, analysis: Analysis) -> Verdict:
    """Classify every detected crossing; fail closed on anything unproven."""
    verdict = Verdict(status="PASS")
    by_dest: dict[str, list[RawCrossing]] = {}
    for crossing in analysis.crossings:
        by_dest.setdefault(crossing.dest, []).append(crossing)

    fifo_candidate = _fifo_candidate(module, domain_map)
    handshake = _handshake_chains(module, domain_map)

    for dest, crossings in sorted(by_dest.items()):
        for crossing in crossings:
            classified = _classify_one(module, domain_map, crossing, fifo_candidate, handshake)
            verdict.crossings.append(classified)
            if classified.severity == "error" and verdict.status == "PASS":
                verdict.status = "FAIL"
            elif classified.severity == "inconclusive" and verdict.status != "FAIL":
                verdict.status = "INCONCLUSIVE"

    for dest, sig in sorted(set(analysis.unknown_hits)):
        verdict.notes.append(f"{dest}: unknown-domain driver or instance boundary at {sig}")
        if verdict.status == "PASS":
            verdict.status = "INCONCLUSIVE"
        verdict.crossings.append(ClassifiedCrossing(
            source=sig, source_domain=None, destination=dest,
            destination_domain=domain_map.domains.get(dest) or "unknown",
            path=[dest, sig], classification="UNKNOWN",
            severity="inconclusive",
            detail="Driver domain cannot be determined; failing closed.",
        ))
    return verdict


def _classify_one(
    module: Module,
    domain_map: DomainMap,
    crossing: RawCrossing,
    fifo_candidate: bool,
    handshake: dict[str, bool],
) -> ClassifiedCrossing:
    src, dest, dom = crossing.source, crossing.dest, crossing.dest_domain
    base = dict(
        source=src, source_domain=crossing.source_domain, destination=dest,
        destination_domain=dom, path=crossing.path,
    )
    if crossing.reset_involved:
        return ClassifiedCrossing(
            **base, classification="RESET_CROSSING", severity="inconclusive",
            detail="Reset-involved crossing cannot be proven safe; failing closed.",
        )
    if fifo_candidate:
        return ClassifiedCrossing(
            **base, classification="UNPROVEN_FIFO", severity="inconclusive",
            detail="FIFO-like dual-clock structure without a complete proof; failing closed.",
        )
    width = _width_of(module, src)
    chain = _find_chain(module, domain_map, src, dest, dom)
    if chain is not None:
        stage1, stages = chain
        users_src = _consumers(module, {src}, dom, domain_map)
        users_s1 = _consumers(module, {stage1}, dom, domain_map)
        if users_src <= {stage1} and users_s1 <= stages and _stages_used(module, stages):
            if width == 1:
                return ClassifiedCrossing(
                    **base, classification="SAFE_SYNCHRONIZER", severity="ok",
                    detail=f"Exact 2-flop chain {src} -> {stage1} -> {sorted(stages)}, no bypass.",
                )
            return ClassifiedCrossing(
                **base, classification="MULTIBIT_UNPROVEN", severity="inconclusive",
                detail=f"Bus ({width}b) crossing even with staging is unproven without handshake/FIFO.",
            )
        return ClassifiedCrossing(
            **base, classification="UNSAFE_BYPASS", severity="error",
            detail=f"Synchronizer exists but {src}/{stage1} is also consumed outside the chain.",
        )
    if width != 1:
        return ClassifiedCrossing(
            **base, classification="MULTIBIT_UNPROVEN", severity="inconclusive",
            detail=f"Bus ({width}b) crossing without proven handshake/FIFO; failing closed.",
        )
    return ClassifiedCrossing(
        **base, classification="UNSAFE_DIRECT", severity="error",
        detail=f"{src} [{crossing.source_domain}] sampled directly in {dom} with no synchronizer.",
    )


def _drivers_of(module: Module, lhs: str, domain: str, domain_map: DomainMap) -> list[list[str]]:
    """All in-domain sequential driver right-hand sides for a register."""
    found: list[list[str]] = []
    for block in module.always_blocks:
        if block.kind != "seq":
            continue
        for driver in block.drivers:
            if driver.lhs == lhs and domain_map.domains.get(lhs) == domain:
                found.append(driver.rhs_ids)
    return found


def _same_domain_seq(module: Module, domain: str, domain_map: DomainMap) -> set[str]:
    return {
        driver.lhs
        for block in module.always_blocks
        if block.kind == "seq"
        for driver in block.drivers
        if domain_map.domains.get(driver.lhs) == domain
    }


def _find_chain(
    module: Module, domain_map: DomainMap, src: str, first: str, domain: str
) -> tuple[str, set[str]] | None:
    """Find exact two-flop chains ``first <= src-cone; s2 <= first``.

    Stage 1 (``first``, the crossing destination flop) must sample only
    the crossing source through combinational logic: every driver cone
    may contain ``src``, same-domain registers and constants, but no
    other-domain or unknown driver. Stage 2 flops sample exactly
    ``first``. Returns (stage1, {stage2...}) or None.
    """
    rhs_list = _drivers_of(module, first, domain, domain_map)
    if not rhs_list:
        return None
    union: set[str] = set()
    for rhs in rhs_list:
        union |= comb_cone(module, rhs)
    if src not in union:
        return None
    allowed = _same_domain_seq(module, domain, domain_map) | {src}
    for member in union:
        if member in allowed:
            continue
        # Undriven non-port nets and other-domain/unknown drivers taint it.
        return None
    stages: set[str] = set()
    allowed2 = _same_domain_seq(module, domain, domain_map) | {first}
    by_lhs: dict[str, list[list[str]]] = {}
    for block in module.always_blocks:
        if block.kind != "seq":
            continue
        for driver in block.drivers:
            lhs = driver.lhs
            if lhs == first or domain_map.domains.get(lhs) != domain:
                continue
            by_lhs.setdefault(lhs, []).append(driver.rhs_ids)
    for lhs, rhs_list in by_lhs.items():
        union2: set[str] = set()
        for rhs in rhs_list:
            union2 |= comb_cone(module, rhs)
        if first in union2 and all(m in allowed2 for m in union2):
            stages.add(lhs)
    if not stages:
        return None
    return first, stages


def _stages_used(module: Module, stages: set[str]) -> bool:
    """True when a chain stage feeds an output port or downstream logic."""
    for assign in module.assigns:
        if stages & set(assign.rhs_ids):
            return True
    for block in module.always_blocks:
        for driver in block.drivers:
            if driver.lhs in stages:
                continue
            if stages & set(driver.rhs_ids):
                return True
    for port in module.ports.values():
        if port.direction == "output" and port.name in stages:
            return True
    return False


def _fifo_candidate(module: Module, domain_map: DomainMap) -> bool:
    """Heuristic dual-clock FIFO detector (names + two domains).

    Conservative by design: a candidate is never PASSed, only routed to
    UNPROVEN_FIFO (INCONCLUSIVE). A Gray-pointer correctness proof is out
    of scope for v1, so any dual-clock FIFO-like structure fails closed.
    """
    if len(domain_map.clocks) < 2:
        return False
    names = [n.lower() for n in list(module.widths)]
    inst_names = [f"{i.module} {i.name}".lower() for i in module.instances]
    has_fifo = any("fifo" in n for n in names) or any("fifo" in n for n in inst_names)
    has_ptrs = any("ptr" in n for n in names) and (
        any("gray" in n for n in names) or any("wptr" in n for n in names)
    )
    return has_fifo or has_ptrs


def _handshake_chains(module: Module, domain_map: DomainMap) -> dict[str, bool]:
    """Detect structurally proven req/ack chains in both directions.

    Name matching (``*req*`` forward, ``*ack*``/``*rdy*`` backward) is only
    a selector; each reported direction requires an exact 2-flop chain
    proof (see _find_chain). Used to label bundled-data caveats.
    """
    result = {"forward": False, "backward": False}
    doms = domain_map.clocks
    same: dict[str, set[str]] = {
        dom: _same_domain_seq(module, dom, domain_map) for dom in doms
    }
    for src_dom in doms:
        for dst_dom in doms:
            if src_dom == dst_dom:
                continue
            for block in module.always_blocks:
                if block.kind != "seq":
                    continue
                for driver in block.drivers:
                    if domain_map.domains.get(driver.lhs) != dst_dom:
                        continue
                    for sig in driver.rhs_ids:
                        cone = comb_cone(module, [sig])
                        if not any(c in same[src_dom] for c in cone):
                            continue
                        if _find_chain(module, domain_map, sig, driver.lhs, dst_dom) is None:
                            continue
                        lowered = sig.lower()
                        if "req" in lowered:
                            result["forward"] = True
                        if "ack" in lowered or "rdy" in lowered:
                            result["backward"] = True
    return result
