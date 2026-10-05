"""
Skill registry for Mind 3.0.
Discovers, extracts, indexes, and manages .skill bundles and skill directories.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Any

from .models import Skill, SkillMetadata, SkillReference


def _parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Parse YAML-like frontmatter enclosed in --- delimiters without external dependencies."""
    stripped = content.strip()
    if not stripped.startswith("---"):
        return {}, content

    parts = stripped.split("---", 2)
    if len(parts) < 3:
        return {}, content

    frontmatter_raw = parts[1].strip()
    body = parts[2].strip()

    metadata: dict[str, str] = {}
    current_key: str | None = None
    accumulated_value: list[str] = []

    for line in frontmatter_raw.splitlines():
        match = re.match(r"^([a-zA-Z0-9_-]+)\s*:\s*(.*)$", line)
        if match:
            if current_key is not None:
                metadata[current_key] = " ".join(accumulated_value).strip()
            current_key = match.group(1).strip()
            initial_val = match.group(2).strip()
            accumulated_value = [initial_val] if initial_val else []
        elif current_key is not None:
            accumulated_value.append(line.strip())

    if current_key is not None:
        metadata[current_key] = " ".join(accumulated_value).strip()

    return metadata, body


class SkillRegistry:
    """Central repository for loading, indexing, and querying agent skills."""

    def __init__(self, skills_dir: Path | str | None = None) -> None:
        self.skills: dict[str, Skill] = {}
        if skills_dir is not None:
            self.load_from_directory(Path(skills_dir))

    def load_from_directory(self, skills_dir: Path) -> int:
        """Scan a directory for .skill archives or unpacked skill folders."""
        skills_dir = skills_dir.resolve()
        if not skills_dir.exists() or not skills_dir.is_dir():
            return 0

        loaded_count = 0

        # 1. Look for .skill zip packages
        for archive_path in sorted(skills_dir.glob("*.skill")):
            skill = self.load_skill_archive(archive_path)
            if skill is not None:
                self.skills[skill.metadata.name] = skill
                loaded_count += 1

        # 2. Look for unpacked directories containing SKILL.md
        for item in sorted(skills_dir.iterdir()):
            if item.is_dir() and (item / "SKILL.md").exists():
                skill = self.load_skill_directory(item)
                if skill is not None:
                    self.skills[skill.metadata.name] = skill
                    loaded_count += 1

        return loaded_count

    def load_skill_archive(self, archive_path: Path) -> Skill | None:
        """Extract and parse a packaged .skill zip archive."""
        if not zipfile.is_zipfile(archive_path):
            return None

        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                file_list = zf.namelist()
                skill_md_path = next((f for f in file_list if f.endswith("SKILL.md")), None)
                if not skill_md_path:
                    return None

                prefix = skill_md_path[: -len("SKILL.md")]
                skill_md_content = zf.read(skill_md_path).decode("utf-8", errors="replace")
                meta_dict, instructions = _parse_frontmatter(skill_md_content)

                name = meta_dict.get("name") or archive_path.stem
                description = meta_dict.get("description") or f"Skill packaged in {archive_path.name}"
                metadata = SkillMetadata(name=name, description=description)

                references: dict[str, SkillReference] = {}
                scripts: dict[str, str] = {}
                assets: dict[str, bytes] = {}

                for fname in file_list:
                    if fname == skill_md_path or fname.endswith("/"):
                        continue

                    rel_name = fname[len(prefix):] if fname.startswith(prefix) else fname
                    if rel_name.startswith("references/") and rel_name.endswith(".md"):
                        ref_content = zf.read(fname).decode("utf-8", errors="replace")
                        first_para = next((p.strip() for p in ref_content.split("\n\n") if p.strip()), "")
                        references[rel_name] = SkillReference(
                            name=rel_name, content=ref_content, summary=first_para[:200]
                        )
                    elif rel_name.startswith("scripts/") or fname.endswith((".py", ".sh", ".bash")):
                        script_content = zf.read(fname).decode("utf-8", errors="replace")
                        scripts[rel_name] = script_content
                    else:
                        assets[rel_name] = zf.read(fname)

                return Skill(
                    metadata=metadata,
                    instructions=instructions,
                    references=references,
                    scripts=scripts,
                    assets=assets,
                    archive_path=archive_path.resolve(),
                )
        except Exception:
            return None

    def load_skill_directory(self, skill_dir: Path) -> Skill | None:
        """Parse an uncompressed directory containing SKILL.md and assets."""
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            return None

        try:
            content = skill_md.read_text(encoding="utf-8")
            meta_dict, instructions = _parse_frontmatter(content)
            name = meta_dict.get("name") or skill_dir.name
            description = meta_dict.get("description") or f"Skill in {skill_dir.name}"
            metadata = SkillMetadata(name=name, description=description)

            references: dict[str, SkillReference] = {}
            scripts: dict[str, str] = {}
            assets: dict[str, bytes] = {}

            ref_dir = skill_dir / "references"
            if ref_dir.is_dir():
                for ref_path in ref_dir.glob("*.md"):
                    ref_content = ref_path.read_text(encoding="utf-8")
                    rel_name = f"references/{ref_path.name}"
                    first_para = next((p.strip() for p in ref_content.split("\n\n") if p.strip()), "")
                    references[rel_name] = SkillReference(
                        name=rel_name, content=ref_content, summary=first_para[:200]
                    )

            scripts_dir = skill_dir / "scripts"
            if scripts_dir.is_dir():
                for script_path in scripts_dir.iterdir():
                    if script_path.is_file():
                        try:
                            scripts[f"scripts/{script_path.name}"] = script_path.read_text(encoding="utf-8")
                        except Exception:
                            continue

            return Skill(
                metadata=metadata,
                instructions=instructions,
                references=references,
                scripts=scripts,
                assets=assets,
                archive_path=None,
            )
        except Exception:
            return None

    def register(self, skill: Skill) -> None:
        """Directly insert a skill object into the registry."""
        self.skills[skill.metadata.name] = skill

    def get(self, name: str) -> Skill | None:
        """Retrieve a registered skill by exact name."""
        return self.skills.get(name)

    def list_skills(self) -> list[Skill]:
        """Return a sorted list of registered skill bundles."""
        return [self.skills[k] for k in sorted(self.skills.keys())]

    def __len__(self) -> int:
        return len(self.skills)
