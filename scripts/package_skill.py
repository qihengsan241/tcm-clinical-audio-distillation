#!/usr/bin/env python3
"""Build a deterministic Hosted Skill ZIP from the repository."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


SKILL_NAME = "tcm-clinical-audio-distillation"
INCLUDED = [
    "SKILL.md",
    "CLOUD.md",
    "requirements-cloud.txt",
    "agents/openai.yaml",
    "references/output-template.md",
    "references/quality-and-safety.md",
    "references/schema.md",
    "scripts/cloud_transcribe.py",
]


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="打包 OpenAI Hosted Skill ZIP。")
    parser.add_argument(
        "--out",
        type=Path,
        default=root / "dist" / f"{SKILL_NAME}.zip",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    missing = [relative for relative in INCLUDED if not (root / relative).is_file()]
    if missing:
        raise FileNotFoundError(f"打包缺少文件：{missing}")

    manifest = (root / "SKILL.md").read_text(encoding="utf-8")
    if not manifest.startswith("---\n") or "name: tcm-clinical-audio-distillation" not in manifest:
        raise ValueError("SKILL.md front matter 无效")

    output = args.out.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in sorted(INCLUDED):
            source = root / relative
            archive.write(source, f"{SKILL_NAME}/{relative}")

    with zipfile.ZipFile(output) as archive:
        manifests = [name for name in archive.namelist() if name.lower().endswith("/skill.md")]
        if manifests != [f"{SKILL_NAME}/SKILL.md"]:
            raise ValueError(f"压缩包必须且只能包含一个 SKILL.md：{manifests}")

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

