"""
Skill data models for Mind 3.0.
Encapsulates metadata, instruction markdown, domain references, and executable scripts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SkillMetadata(BaseModel):
    """Metadata extracted from SKILL.md YAML frontmatter."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    name: str = Field(min_length=1, description="Unique identifier for the skill")
    description: str = Field(min_length=1, description="Overview of skill capabilities")
    tags: list[str] = Field(default_factory=list, description="Keywords for capability routing")
    version: str = Field(default="1.0.0", description="Skill package semantic version")


class SkillReference(BaseModel):
    """Ancillary reference document providing in-depth domain rules."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    name: str = Field(min_length=1, description="Relative reference filename, e.g. references/rtl-design.md")
    content: str = Field(description="Full markdown body of the reference")
    summary: str = Field(default="", description="First paragraph or header summary")


class Skill(BaseModel):
    """Complete encapsulated skill bundle with instructions, references, and scripts."""

    model_config = ConfigDict(extra="ignore")

    metadata: SkillMetadata
    instructions: str = Field(description="Body of SKILL.md after frontmatter")
    references: dict[str, SkillReference] = Field(
        default_factory=dict, description="Mapped reference documents by relative path"
    )
    scripts: dict[str, str] = Field(
        default_factory=dict, description="Executable script contents by relative path"
    )
    assets: dict[str, bytes] = Field(
        default_factory=dict, description="Binary assets (e.g. sample images or schemas)"
    )
    archive_path: Path | None = Field(default=None, description="Source .skill archive path")


@dataclass(frozen=True)
class SkillMatch:
    """Outcome of skill routing for a user prompt."""

    skill: Skill | None
    score: float
    matched_keywords: list[str] = field(default_factory=list)
    relevant_references: list[SkillReference] = field(default_factory=list)
    suggested_domain: str = "GENERAL"
    reasoning: str = ""
