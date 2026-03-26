"""Build a bundled Hugging Face LoRA reference catalog from downloaded .json/.txt sidecars."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build a bundled trigger-word reference catalog from Hugging Face sidecars.",
    )
    parser.add_argument(
        "source_dir",
        type=Path,
        help="Directory containing the downloaded Hugging Face repository .json/.txt files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "reference_metadata"
        / "huggingface_lora_catalog.json",
        help="Output catalog JSON path.",
    )
    return parser.parse_args()


def normalize_text(value):
    if value is None:
        return ""
    return str(value).strip()


def build_entry(json_path: Path, source_root: Path):
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Skip {json_path}: failed to parse JSON ({exc})")
        return None

    if not isinstance(payload, dict) or "activation text" not in payload:
        return None

    txt_path = json_path.with_suffix(".txt")
    text_body = ""
    if txt_path.exists():
        text_body = normalize_text(txt_path.read_text(encoding="utf-8"))

    relative_path = json_path.relative_to(source_root).as_posix()
    path_parts = relative_path.split("/")
    family = path_parts[0] if path_parts else ""
    subgroup = path_parts[1] if len(path_parts) > 2 else ""
    model_key = json_path.stem

    return {
        "source": f"https://huggingface.co/nashikone/iroiroLoRA/blob/main/{relative_path}",
        "relative_path": relative_path,
        "family": family,
        "subgroup": subgroup,
        "model_key": model_key,
        "aliases": [model_key],
        "sd_version": normalize_text(payload.get("sd version")),
        "activation_text": normalize_text(payload.get("activation text")),
        "preferred_weight": payload.get("preferred weight", 0),
        "negative_text": normalize_text(payload.get("negative text")),
        "notes": normalize_text(payload.get("notes")),
        "description": normalize_text(payload.get("description")),
        "text_body": text_body,
    }


def main():
    args = parse_args()
    source_dir = args.source_dir.resolve()
    output_path = args.output.resolve()

    entries = []
    for json_path in sorted(source_dir.rglob("*.json")):
        entry = build_entry(json_path, source_dir)
        if entry is not None:
            entries.append(entry)

    catalog = {
        "catalog_version": 1,
        "generated_from": str(source_dir),
        "entry_count": len(entries),
        "entries": entries,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(entries)} entries to {output_path}")


if __name__ == "__main__":
    main()
