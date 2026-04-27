from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    template: str


def load_prompt_template(path: Path) -> PromptTemplate:
    """
    Load the minimal YAML subset used by ATLAS prompt templates.

    Supported shape:
      name: prompt_name
      version: "1"
      template: |
        multiline template
    """
    content = path.read_text(encoding="utf-8")
    metadata: dict[str, str] = {}
    template_lines: list[str] = []
    in_template = False

    for raw_line in content.splitlines():
        if in_template:
            if raw_line.startswith("  "):
                template_lines.append(raw_line[2:])
            elif raw_line == "":
                template_lines.append("")
            else:
                raise ValueError(f"Unexpected non-indented template line in {path}: {raw_line}")
            continue

        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        key, separator, value = stripped.partition(":")
        if not separator:
            raise ValueError(f"Invalid YAML line in {path}: {raw_line}")

        key = key.strip()
        value = value.strip().strip('"')
        if key == "template" and value == "|":
            in_template = True
            continue

        metadata[key] = value

    name = metadata.get("name")
    version = metadata.get("version", "1")
    template = "\n".join(template_lines).strip()

    if not name:
        raise ValueError(f"Prompt template missing name: {path}")
    if not template:
        raise ValueError(f"Prompt template missing template block: {path}")

    return PromptTemplate(name=name, version=version, template=template)
