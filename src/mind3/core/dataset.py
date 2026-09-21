"""Dataset Curation & Fine-Tuning Engine for Mind 3.0.

Captures end-to-end multi-agent hardware trajectories:
(natural_language_spec -> contract -> initial_rtl -> gate_feedback -> repaired_rtl -> signoff)
and exports them into standardized instruction-tuning datasets (JSONL / ShareGPT)
for domain-specific LLM fine-tuning with Axolotl, Unsloth, or HuggingFace TRL.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class HardwareTrajectoryRecord:
    """Complete multi-turn design and repair trajectory for a single module."""

    session_id: str
    module_name: str
    functional_spec: str
    interface_contract_json: str
    initial_rtl: str
    repair_turns: list[dict[str, Any]] = field(default_factory=list)
    final_repaired_rtl: str = ""
    silicon_signoff_passed: bool = False
    timing_wns_ps: float | None = None
    branch_coverage: float | None = None


class FineTuningDatasetExporter:
    """Manages recording and exporting high-fidelity VLSI training datasets."""

    def __init__(self) -> None:
        """Initialize in-memory trajectory buffer."""
        self._trajectories: list[HardwareTrajectoryRecord] = []

    def record(self, trajectory: HardwareTrajectoryRecord) -> None:
        """Buffer a completed design trajectory."""
        self._trajectories.append(trajectory)

    def to_records(self) -> list[dict[str, Any]]:
        """Return all buffered records as dictionaries."""
        return [asdict(t) for t in self._trajectories]

    def export_jsonl(self, output_path: Path | str, signoff_only: bool = True) -> int:
        """Export buffered trajectories as standard instruction/input/output JSONL."""
        path = Path(output_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with open(path, "w", encoding="utf-8") as f:
            for traj in self._trajectories:
                if signoff_only and not traj.silicon_signoff_passed:
                    continue

                # Record 1: Architecture Intake & Contract Synthesis
                rec_contract = {
                    "instruction": "Synthesize a formal InterfaceContract from natural language specification.",
                    "input": traj.functional_spec,
                    "output": traj.interface_contract_json,
                    "module": traj.module_name,
                }
                f.write(json.dumps(rec_contract) + "\n")
                count += 1

                # Record 2: RTL Synthesis from Contract
                rec_rtl = {
                    "instruction": "Implement synthesizable SystemVerilog matching the strict InterfaceContract.",
                    "input": traj.interface_contract_json,
                    "output": traj.final_repaired_rtl or traj.initial_rtl,
                    "module": traj.module_name,
                }
                f.write(json.dumps(rec_rtl) + "\n")
                count += 1

                # Record 3: Targeted Repair Steps
                for turn in traj.repair_turns:
                    rec_repair = {
                        "instruction": "Repair the SystemVerilog RTL to resolve the EDA signoff gate violation.",
                        "input": (
                            f"Current RTL:\n{turn.get('failing_rtl', '')}\n\n"
                            f"EDA Failure Report:\n{turn.get('error_feedback', '')}"
                        ),
                        "output": turn.get("repaired_rtl", ""),
                        "module": traj.module_name,
                    }
                    f.write(json.dumps(rec_repair) + "\n")
                    count += 1
        return count

    def export_sharegpt(self, output_path: Path | str, signoff_only: bool = True) -> int:
        """Export trajectories in ShareGPT multi-turn conversational format."""
        path = Path(output_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with open(path, "w", encoding="utf-8") as f:
            for traj in self._trajectories:
                if signoff_only and not traj.silicon_signoff_passed:
                    continue

                conversations = [
                    {"from": "human", "value": f"Design module '{traj.module_name}': {traj.functional_spec}"},
                    {"from": "gpt", "value": f"```json\n{traj.interface_contract_json}\n```"},
                    {"from": "human", "value": "Implement the synthesizable SystemVerilog RTL."},
                    {"from": "gpt", "value": f"```systemverilog\n{traj.initial_rtl}\n```"},
                ]

                for turn in traj.repair_turns:
                    conversations.append({
                        "from": "human",
                        "value": f"EDA Gate Violation: {turn.get('error_feedback', '')}\nPlease repair the RTL.",
                    })
                    conversations.append({
                        "from": "gpt",
                        "value": f"```systemverilog\n{turn.get('repaired_rtl', '')}\n```",
                    })

                entry = {"conversations": conversations}
                f.write(json.dumps(entry) + "\n")
                count += 1
        return count
