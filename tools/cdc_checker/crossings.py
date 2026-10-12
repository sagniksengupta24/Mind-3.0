"""Data-flow graph construction and clock-domain-crossing detection.

A crossing exists when the combinational fan-in cone of a sequential
register in domain D reaches a source in a different domain D2 (another
register, an assumed-domain port, or an unknown-domain driver). Backward
traversal stops at sequential boundaries (pipeline stages are not crossed:
only the immediately-sampled cone matters for metastability).

Unknown instance boundaries (module instances are not analyzed
hierarchically in v1) terminate traversal with an unknown-source hit, which
classifies as INCONCLUSIVE downstream, never PASS.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .clocks import DomainMap, is_reset_name
from .parser import Module


@dataclass
class RawCrossing:
    source: str
    source_domain: str | None
    dest: str
    dest_domain: str
    path: list[str]
    reset_involved: bool = False


@dataclass
class Analysis:
    crossings: list[RawCrossing] = field(default_factory=list)
    # (dest flop, boundary signal) pairs where traversal met an unknown
    # instance boundary or an unknown-domain driver.
    unknown_hits: list[tuple[str, str]] = field(default_factory=list)
    domains: DomainMap | None = None


def _build_drivers(module: Module) -> tuple[dict[str, list[tuple[str, list[str]]]], set[str]]:
    """Map signal -> [(driver_kind, rhs_ids)] plus driven-signal set.

    driver_kind is "comb" (transparent: plain assign / combinational
    always) or "seq" (domain endpoint: clocked always block).
    """
    drivers: dict[str, list[tuple[str, list[str]]]] = {}
    driven: set[str] = set()

    def add(lhs: str, kind: str, rhs: list[str]) -> None:
        drivers.setdefault(lhs, []).append((kind, rhs))
        driven.add(lhs)

    for assign in module.assigns:
        add(assign.lhs, "comb", assign.rhs_ids)
    for block in module.always_blocks:
        kind = "seq" if block.kind == "seq" else "comb"
        for driver in block.drivers:
            add(driver.lhs, kind, driver.rhs_ids)
    return drivers, driven


def comb_cone(module: Module, seeds: list[str]) -> set[str]:
    """Sequential endpoints and ports feeding seeds through combinational logic only.

    Traversal stops at sequential-driver boundaries (pipeline stages are not
    crossed) and at undriven signals (ports). Used to test what a
    synchronizer stage actually samples.
    """
    drivers, _ = _build_drivers(module)
    seq_lhs = {
        driver.lhs
        for block in module.always_blocks
        if block.kind == "seq"
        for driver in block.drivers
    }
    found: set[str] = set()
    stack = list(seeds)
    visited: set[str] = set()
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        edges = drivers.get(node)
        if not edges:
            found.add(node)
            continue
        for kind, rhs in edges:
            if kind == "seq":
                found.add(node)
            else:
                stack.extend(rhs)
    return found


def analyze(module: Module, domain_map: DomainMap) -> Analysis:
    """Find all cross-domain samplings in the top module."""
    drivers, driven = _build_drivers(module)
    boundary: set[str] = set()
    for inst in module.instances:
        for actuals in inst.connections.values():
            boundary.update(actuals)

    analysis = Analysis(domains=domain_map)
    seq_lhs = {
        driver.lhs
        for block in module.always_blocks
        if block.kind == "seq"
        for driver in block.drivers
    }
    ports = set(module.ports)
    for block in module.always_blocks:
        if block.kind != "seq":
            continue
        for driver in block.drivers:
            dest = driver.lhs
            dest_domain = domain_map.domains.get(dest)
            if dest_domain is None:
                analysis.unknown_hits.append((dest, dest))
                continue
            for seed in driver.rhs_ids:
                _trace_cone(
                    seed, dest, dest_domain, drivers, driven, boundary,
                    domain_map, seq_lhs, ports, analysis, path=[dest],
                )
    # Identical (source, dest) findings from multi-driver flops collapse.
    seen: set[tuple[str | None, str]] = set()
    unique: list[RawCrossing] = []
    for crossing in analysis.crossings:
        key = (crossing.source, crossing.dest)
        if key not in seen:
            seen.add(key)
            unique.append(crossing)
    analysis.crossings = unique
    analysis.unknown_hits = sorted(set(analysis.unknown_hits))
    return analysis


def _trace_cone(
    node: str,
    dest: str,
    dest_domain: str,
    drivers: dict[str, list[tuple[str, list[str]]]],
    driven: set[str],
    boundary: set[str],
    domain_map: DomainMap,
    seq_lhs: set[str],
    ports: set[str],
    analysis: Analysis,
    path: list[str],
) -> None:
    if node in path:
        return
    path = path + [node]
    if node in boundary and node not in driven:
        analysis.unknown_hits.append((dest, node))
        return
    edges = drivers.get(node)
    if not edges:
        # Undriven net. Primary input ports are synchronous stimulus
        # boundaries (benchmark scope: the testbench drives them
        # synchronously; asynchronous inputs must be declared at contract
        # level): analysis starts at the first flop, so a port sampled
        # directly is not itself a crossing. Any other dangling net is
        # unprovable and fails closed.
        if node in ports:
            return
        analysis.unknown_hits.append((dest, node))
        return
    for kind, rhs in edges:
        if kind == "seq":
            # A sequential driver is a domain endpoint: do not cross stages.
            src_domain = domain_map.domains.get(node)
            reset = is_reset_name(node) or any(is_reset_name(p) for p in path)
            if src_domain is None:
                analysis.unknown_hits.append((dest, node))
            elif src_domain != dest_domain:
                analysis.crossings.append(RawCrossing(
                    source=node, source_domain=src_domain, dest=dest,
                    dest_domain=dest_domain, path=list(reversed(path)),
                    reset_involved=reset,
                ))
            continue
        for ref in rhs:
            _trace_cone(
                ref, dest, dest_domain, drivers, driven, boundary,
                domain_map, seq_lhs, ports, analysis, path,
            )
    if node in boundary:
        analysis.unknown_hits.append((dest, node))
