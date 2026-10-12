"""Clock-domain assignment for sequential registers.

Rules (documented, conservative):

* Every ``always @(posedge c)`` / ``always_ff @(posedge c)`` block assigns
  its driven registers to domain ``c``; ``negedge c`` still identifies
  clock signal ``c`` (same domain; edge recorded for reporting).
* A sequential block with zero clocks (``always @(*)``/``always_comb``) is
  combinational: transparent, no domain.
* A sequential block with two or more distinct clocks, or a register driven
  from blocks of different clocks, yields domain ``None`` (unknown) for
  that register; any crossing analysis touching it reports INCONCLUSIVE,
  never a silent PASS.
* Primary input ports are synchronous stimulus boundaries (the testbench
  drives them synchronously; asynchronous inputs must be declared at
  contract level): register-to-register transfers are analyzed, ports
  sampled directly by a first flop are not crossings in themselves.
* Reset signals (``rst*``, ``reset*``, ``arst*`` by name, polarity from
  usage) are identified for reporting; reset-involved crossings are
  classified INCONCLUSIVE unless the reset is consumed synchronously
  inside the destination domain (ordinary flop ``if (!rst_n)`` handling
  does not itself constitute a crossing).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .parser import Module

_RESET_RE = re.compile(r"^(rst|reset|arst|rst_n|reset_n|rstn)\w*$", re.I)


def is_reset_name(name: str) -> bool:
    """Heuristic reset-signal identification (documented, name-based)."""
    return bool(_RESET_RE.match(name))


@dataclass
class DomainMap:
    """Register -> clock-domain assignment (None means unknown)."""

    domains: dict[str, str | None]
    clocks: list[str]
    single_domain: str | None  # the sole domain when exactly one exists


def assign_domains(module: Module) -> DomainMap:
    """Assign every driven register to its clock domain."""
    domains: dict[str, set[str | None]] = {}
    clocks: list[str] = []
    for block in module.always_blocks:
        if block.kind != "seq":
            continue
        sigs = sorted({sig for _, sig in block.clocks})
        for sig in sigs:
            if sig not in clocks:
                clocks.append(sig)
        domain: str | None = sigs[0] if len(sigs) == 1 else None
        for driver in block.drivers:
            domains.setdefault(driver.lhs, set()).add(domain)
    resolved: dict[str, str | None] = {}
    for sig, doms in domains.items():
        resolved[sig] = next(iter(doms)) if len(doms) == 1 else None
    single = clocks[0] if len(clocks) == 1 else None
    return DomainMap(domains=resolved, clocks=clocks, single_domain=single)
