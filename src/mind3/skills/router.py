"""
Skill router for Mind 3.0.
Analyzes user engineering intent and routes to the most specialized skill and reference documents.
"""

from __future__ import annotations

import re
from typing import Any

from .models import Skill, SkillMatch, SkillReference
from .registry import SkillRegistry


# Weighted keyword maps for fine-grained domain categorization
DOMAIN_PATTERNS: dict[str, dict[str, list[str]]] = {
    "semiconductor-vlsi": {
        "rtl": [
            "verilog", "systemverilog", "vhdl", "rtl", "module", "always_ff", "always_comb",
            "always", "assign", "latch", "blocking", "non-blocking", "testbench", "fsm",
            "counter", "arbiter", "fifo", "axi", "cdc", "synchronizer", "hdl", "iverilog",
        ],
        "physical_design": [
            "sta", "static timing", "setup", "hold", "slack", "timing closure", "skew",
            "sdc", "cts", "floorplan", "placement", "routing", "drc", "lvs", "antenna",
            "primetime", "genus", "innovus", "pvt", "corner", "lib", "lef", "def",
        ],
        "cdc_dft": [
            "cdc", "clock domain crossing", "clock domain", "synchronizer", "metastability",
            "two-ff", "2ff", "dft", "scan", "atpg", "scan chain", "boundary scan",
            "jtag", "bist", "scan_en", "scan_enable", "test mode", "dft insertion",
        ],
        "device_concepts": [
            "mosfet", "transistor", "threshold voltage", "vt", "body effect", "dibl",
            "subthreshold", "leakage", "finfet", "gaa", "feol", "beol", "fabrication",
            "gate oxide", "high-k", "saturation", "triode", "mobility", "scaling",
        ],
    },
    "industry-report-analyst": {
        "report_structure": [
            "report", "industry", "market", "landscape", "executive summary", "competitive",
            "deep dive", "state of", "analysis report", "citable", "deloitte", "mckinsey",
        ],
        "timeline_chart": [
            "timeline", "dot-plot", "roadmap", "milestone", "planned vs actual", "delay",
            "tsmc", "intel 18a", "n3e", "n2", "foundry", "tape-out", "tapeout", "chart",
        ],
    },
}


class SkillRouter:
    """Matches engineering requests to registered skills and selects context references."""

    def __init__(self, registry: SkillRegistry) -> None:
        self.registry: SkillRegistry = registry

    def route(self, prompt: str) -> SkillMatch:
        """Evaluate a prompt against all registered skills and compute relevance scores."""
        lower_prompt = prompt.lower()
        best_skill: Skill | None = None
        best_score = 0.0
        best_keywords: list[str] = []
        best_references: list[SkillReference] = []
        suggested_domain = "GENERAL"
        reasoning = "Default general engineering routing."

        for skill in self.registry.list_skills():
            skill_name = skill.metadata.name
            skill_score = 0.0
            matched_kws: list[str] = []
            selected_refs: list[SkillReference] = []

            # Check if skill has specific domain pattern rules
            patterns = DOMAIN_PATTERNS.get(skill_name, {})
            if patterns:
                for subcategory, keywords in patterns.items():
                    sub_score = 0
                    sub_kws = []
                    for kw in keywords:
                        # Whole word or substring match
                        pattern = r"\b" + re.escape(kw) + r"\b"
                        if re.search(pattern, lower_prompt):
                            sub_score += 2.0
                            sub_kws.append(kw)
                        elif kw in lower_prompt:
                            sub_score += 1.0
                            sub_kws.append(kw)

                    if sub_score > 0:
                        skill_score += sub_score
                        matched_kws.extend(sub_kws)

                        # Match corresponding reference document if available
                        if subcategory == "rtl" and "references/rtl-design.md" in skill.references:
                            selected_refs.append(skill.references["references/rtl-design.md"])
                            suggested_domain = "RTL"
                        elif subcategory == "physical_design" and "references/physical-design.md" in skill.references:
                            selected_refs.append(skill.references["references/physical-design.md"])
                            suggested_domain = "PHYSICAL_DESIGN"
                        elif subcategory == "cdc_dft":
                            if "references/cdc-dft.md" in skill.references:
                                selected_refs.append(skill.references["references/cdc-dft.md"])
                            suggested_domain = "CDC_DFT"
                        elif subcategory == "device_concepts" and "references/device-concepts.md" in skill.references:
                            selected_refs.append(skill.references["references/device-concepts.md"])
                            suggested_domain = "VLSI_DEVICE"
                        elif subcategory == "report_structure" and "references/report_structure.md" in skill.references:
                            selected_refs.append(skill.references["references/report_structure.md"])
                            suggested_domain = "INDUSTRY_REPORT"
                        elif subcategory == "timeline_chart":
                            if "references/report_structure.md" in skill.references and skill.references["references/report_structure.md"] not in selected_refs:
                                selected_refs.append(skill.references["references/report_structure.md"])
                            suggested_domain = "INDUSTRY_REPORT"
            else:
                # Generic keyword matching on skill description and name
                words = set(re.findall(r"\w+", lower_prompt))
                desc_words = set(re.findall(r"\w+", skill.metadata.description.lower()))
                common = words.intersection(desc_words)
                skill_score = float(len(common))
                matched_kws = list(common)
                selected_refs = list(skill.references.values())[:2]

            if skill_score > best_score:
                best_score = skill_score
                best_skill = skill
                best_keywords = matched_kws
                # Deduplicate references
                seen_names = set()
                deduped_refs = []
                for r in selected_refs:
                    if r.name not in seen_names:
                        seen_names.add(r.name)
                        deduped_refs.append(r)
                best_references = deduped_refs
                reasoning = (
                    f"Matched skill '{skill_name}' with score {best_score:.1f} "
                    f"via keywords: {', '.join(sorted(set(matched_kws))[:5])}"
                )

        # Normalize score to [0.0, 1.0] threshold
        normalized_score = min(1.0, best_score / 10.0) if best_score > 0 else 0.0

        if best_skill is None or normalized_score < 0.1:
            return SkillMatch(
                skill=None,
                score=0.0,
                matched_keywords=[],
                relevant_references=[],
                suggested_domain="SOFTWARE",
                reasoning="No specialized domain skill triggered; routing to baseline software execution.",
            )

        return SkillMatch(
            skill=best_skill,
            score=normalized_score,
            matched_keywords=sorted(set(best_keywords)),
            relevant_references=best_references,
            suggested_domain=suggested_domain,
            reasoning=reasoning,
        )
