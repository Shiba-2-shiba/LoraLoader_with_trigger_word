"""Validate extracted trigger words against local reference files."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def main():
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from trigger_word_resolver import TriggerWordResolver

    args = parse_args()
    resolver = TriggerWordResolver()
    expected_map = load_expected_map(args.reference_dir / args.expected_file)

    if not expected_map:
        raise SystemExit("No expected trigger words were found in the reference txt file.")

    results = []
    for model_path in sorted(args.reference_dir.glob("*.safetensors")):
        expected = expected_map.get(model_path.name, "")
        metadata_result = resolver.resolve_path(
            lora_path=str(model_path),
            trigger_word_source="metadata",
            enable_civitai_fallback=False,
        )
        combined_result = resolver.resolve_path(
            lora_path=str(model_path),
            trigger_word_source="json_combined",
            enable_civitai_fallback=False,
        )
        result = {
            "name": model_path.name,
            "expected": expected,
            "metadata": metadata_result,
            "combined": combined_result,
            "metadata_status": compare_trigger_words(expected, metadata_result),
            "combined_status": compare_trigger_words(expected, combined_result),
            "prompt_preview": build_prompt_preview(model_path.name, args.strength, metadata_result),
        }
        if args.enable_civitai_fallback:
            metadata_fallback_result = resolver.resolve_path(
                lora_path=str(model_path),
                trigger_word_source="metadata",
                enable_civitai_fallback=True,
            )
            combined_fallback_result = resolver.resolve_path(
                lora_path=str(model_path),
                trigger_word_source="json_combined",
                enable_civitai_fallback=True,
            )
            result.update(
                {
                    "metadata_fallback": metadata_fallback_result,
                    "combined_fallback": combined_fallback_result,
                    "metadata_fallback_status": compare_trigger_words(expected, metadata_fallback_result),
                    "combined_fallback_status": compare_trigger_words(expected, combined_fallback_result),
                    "prompt_preview_fallback": build_prompt_preview(
                        model_path.name,
                        args.strength,
                        metadata_fallback_result,
                    ),
                }
            )
        results.append(result)

    print_report(results)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reference-dir",
        type=Path,
        default=Path(r"C:\Users\inott\Downloads\test\Loraモデル参考"),
    )
    parser.add_argument(
        "--expected-file",
        default="トリガーワード.txt",
    )
    parser.add_argument(
        "--strength",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--enable-civitai-fallback",
        action="store_true",
    )
    return parser.parse_args()


def load_expected_map(path: Path):
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    expected_map = {}
    current_name = ""
    for line in lines:
        if not line:
            continue
        if line.endswith(".safetensors"):
            current_name = re.sub(r"^[^A-Za-z0-9@_-]+", "", line)
            continue
        if current_name:
            expected_map[current_name] = line
            current_name = ""
    return expected_map


def compare_trigger_words(expected: str, actual: str):
    expected_norm = normalize_text(expected)
    actual_norm = normalize_text(actual)

    if not expected_norm:
        return "no-expected"
    if actual_norm.startswith(normalize_text("[LoRA Trigger Words]")):
        return "error"
    if expected_norm == actual_norm:
        return "exact"
    if expected_norm and expected_norm in actual_norm:
        return "contains"
    expected_tokens = [token for token in expected_norm.split() if token]
    if expected_tokens and all(token in actual_norm for token in expected_tokens):
        return "token-match"
    return "mismatch"


def build_prompt_preview(model_name: str, strength: float, trigger_words: str):
    lora_name = Path(model_name).with_suffix("").as_posix()
    strength_text = format(strength, "g")
    if normalize_text(trigger_words).startswith(normalize_text("[LoRA Trigger Words]")):
        return trigger_words
    if trigger_words:
        return f"<lora:{lora_name}:{strength_text}>, {trigger_words}"
    return f"<lora:{lora_name}:{strength_text}>"


def normalize_text(text: str):
    text = str(text or "").lower().replace("_", " ").replace("-", " ")
    text = re.sub(r"[^\w@ ]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def print_report(results):
    metadata_ok = sum(result["metadata_status"] in {"exact", "contains", "token-match"} for result in results)
    combined_ok = sum(result["combined_status"] in {"exact", "contains", "token-match"} for result in results)

    print(f"Reference models: {len(results)}")
    print(f"Metadata source matches: {metadata_ok}/{len(results)}")
    print(f"Combined source matches: {combined_ok}/{len(results)}")
    if results and "metadata_fallback_status" in results[0]:
        metadata_fallback_ok = sum(
            result["metadata_fallback_status"] in {"exact", "contains", "token-match"}
            for result in results
        )
        combined_fallback_ok = sum(
            result["combined_fallback_status"] in {"exact", "contains", "token-match"}
            for result in results
        )
        print(f"Metadata+fallback matches: {metadata_fallback_ok}/{len(results)}")
        print(f"Combined+fallback matches: {combined_fallback_ok}/{len(results)}")
    print()

    for result in results:
        print(f"[{result['metadata_status']}] {result['name']}")
        print(f"  expected : {result['expected']}")
        print(f"  metadata : {result['metadata']}")
        print(f"  combined : {result['combined']}")
        print(f"  preview  : {result['prompt_preview']}")
        if "metadata_fallback_status" in result:
            print(f"  metadata+fallback : {result['metadata_fallback']}")
            print(f"  combined+fallback : {result['combined_fallback']}")
            print(f"  preview+fallback  : {result['prompt_preview_fallback']}")
        print()


if __name__ == "__main__":
    main()
