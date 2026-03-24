from __future__ import annotations

import sys
import unittest
import importlib.util
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "trigger_word_resolver.py"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

spec = importlib.util.spec_from_file_location("trigger_word_resolver", MODULE_PATH)
trigger_word_resolver = importlib.util.module_from_spec(spec)
sys.modules.setdefault("trigger_word_resolver", trigger_word_resolver)
assert spec.loader is not None
spec.loader.exec_module(trigger_word_resolver)
TriggerWordResolver = trigger_word_resolver.TriggerWordResolver


class TriggerWordResolverTests(unittest.TestCase):
    def setUp(self):
        self.resolver = TriggerWordResolver()

    def test_json_combined_dedupes_and_cleans_lora_syntax(self):
        metadata = {
            "civitai": {
                "trainedWords": [
                    "hero_tag, cinematic light",
                    "<lora:hero_tag:1>, Hero_Tag",
                    "cinematic light",
                ]
            }
        }

        with patch.object(
            self.resolver,
            "_get_metadata_with_optional_fallback",
            return_value=(metadata, "local metadata"),
        ):
            result = self.resolver.resolve_path(
                lora_path=r"C:\tmp\hero_tag.safetensors",
                trigger_word_source="json_combined",
                enable_civitai_fallback=False,
            )

        self.assertEqual(result, "hero_tag, cinematic light")

    def test_metadata_prefers_civitai_fallback_when_local_words_are_generic(self):
        with (
            patch.object(
                self.resolver,
                "_load_embedded_metadata",
                return_value={"civitai": {"trainedWords": ["1girl"]}},
            ),
            patch.object(
                self.resolver,
                "_load_civitai_metadata_by_hash",
                return_value={"civitai": {"trainedWords": ["hero_tag"]}},
            ),
        ):
            result = self.resolver.resolve_path(
                lora_path=r"C:\tmp\hero_tag_v1.safetensors",
                trigger_word_source="metadata",
                enable_civitai_fallback=True,
            )

        self.assertEqual(result, "hero_tag")

    def test_json_sample_prompt_returns_cleaned_prompt_text(self):
        metadata = {
            "civitai": {
                "images": [
                    {
                        "meta": {
                            "prompt": "<lora:hero_tag:0.8>, hero_tag, dramatic light"
                        }
                    }
                ]
            }
        }

        with patch.object(
            self.resolver,
            "_get_metadata_with_optional_fallback",
            return_value=(metadata, "local metadata"),
        ):
            result = self.resolver.resolve_path(
                lora_path=r"C:\tmp\hero_tag.safetensors",
                trigger_word_source="json_sample_prompt",
                enable_civitai_fallback=False,
            )

        self.assertEqual(result, "hero_tag, dramatic light")

    def test_json_sample_prompt_reports_missing_meta(self):
        metadata = {"civitai": {"images": [{"meta": None}]}}

        with patch.object(
            self.resolver,
            "_get_metadata_with_optional_fallback",
            return_value=(metadata, "local metadata"),
        ):
            result = self.resolver.resolve_path(
                lora_path=r"C:\tmp\hero_tag.safetensors",
                trigger_word_source="json_sample_prompt",
                enable_civitai_fallback=False,
            )

        self.assertIn("images.meta", result)

    def test_metadata_uses_filename_fallback_when_embedded_metadata_is_missing(self):
        with patch.object(self.resolver, "_load_embedded_metadata", return_value=None):
            result = self.resolver.resolve_path(
                lora_path=r"C:\tmp\hero-tag_v1-step10.safetensors",
                trigger_word_source="metadata",
                enable_civitai_fallback=False,
            )

        self.assertEqual(result, "hero tag")

    def test_resolve_output_path_returns_empty_string_for_failure_message(self):
        with patch.object(
            self.resolver,
            "resolve_path",
            return_value="[LoRA Trigger Words] hero_tag.safetensors: not found",
        ):
            result = self.resolver.resolve_output_path(
                lora_path=r"C:\tmp\hero_tag.safetensors",
                trigger_word_source="metadata",
                enable_civitai_fallback=False,
            )

        self.assertEqual(result, "")

    def test_model_card_prefers_local_metadata(self):
        with patch.object(
            self.resolver,
            "_load_json_metadata",
            return_value={
                "civitai": {
                    "id": 456,
                    "modelId": 123,
                    "name": "v1.0",
                    "model": {"name": "Hero LoRA"},
                }
            },
        ):
            result = self.resolver.resolve_model_card_path(
                lora_path=r"C:\tmp\hero_tag.safetensors",
                enable_civitai_fallback=True,
            )

        self.assertTrue(result["success"])
        self.assertEqual(
            result["civitai_url"],
            "https://civitai.com/models/123?modelVersionId=456",
        )
        self.assertEqual(result["source_label"], "local metadata")

    def test_model_card_falls_back_to_civitai_hash_when_local_metadata_has_no_ids(self):
        with (
            patch.object(self.resolver, "_load_json_metadata", return_value={"civitai": {}}),
            patch.object(
                self.resolver,
                "_load_civitai_metadata_by_hash",
                return_value={
                    "civitai": {
                        "id": 789,
                        "modelId": 321,
                        "name": "v2",
                        "model": {"name": "Fallback Hero"},
                    }
                },
            ),
        ):
            result = self.resolver.resolve_model_card_path(
                lora_path=r"C:\tmp\hero_tag.safetensors",
                enable_civitai_fallback=True,
            )

        self.assertTrue(result["success"])
        self.assertEqual(
            result["civitai_url"],
            "https://civitai.com/models/321?modelVersionId=789",
        )
        self.assertEqual(result["source_label"], "Civitai by-hash fallback/cache")


if __name__ == "__main__":
    unittest.main()
