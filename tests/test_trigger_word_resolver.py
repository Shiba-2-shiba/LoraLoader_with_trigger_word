from __future__ import annotations

import json
import sys
import unittest
import importlib.util
from pathlib import Path
from unittest.mock import mock_open, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "trigger_word_resolver.py"
REPOSITORY_MODULE_PATH = REPO_ROOT / "trigger_word_repository.py"
PROVIDER_MODULE_PATH = REPO_ROOT / "remote_metadata" / "providers.py"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

spec = importlib.util.spec_from_file_location("trigger_word_resolver", MODULE_PATH)
trigger_word_resolver = importlib.util.module_from_spec(spec)
sys.modules.setdefault("trigger_word_resolver", trigger_word_resolver)
assert spec.loader is not None
spec.loader.exec_module(trigger_word_resolver)
TriggerWordResolver = trigger_word_resolver.TriggerWordResolver

repository_spec = importlib.util.spec_from_file_location(
    "trigger_word_repository",
    REPOSITORY_MODULE_PATH,
)
trigger_word_repository = importlib.util.module_from_spec(repository_spec)
sys.modules.setdefault("trigger_word_repository", trigger_word_repository)
assert repository_spec.loader is not None
repository_spec.loader.exec_module(trigger_word_repository)
TriggerWordMetadataRepository = trigger_word_repository.TriggerWordMetadataRepository

provider_spec = importlib.util.spec_from_file_location(
    "remote_metadata.providers",
    PROVIDER_MODULE_PATH,
)
remote_metadata_providers = importlib.util.module_from_spec(provider_spec)
sys.modules.setdefault("remote_metadata.providers", remote_metadata_providers)
assert provider_spec.loader is not None
provider_spec.loader.exec_module(remote_metadata_providers)
CivitaiMetadataProvider = remote_metadata_providers.CivitaiMetadataProvider
CivArchiveMetadataProvider = remote_metadata_providers.CivArchiveMetadataProvider


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

    def test_metadata_uses_civarchive_fallback_when_civitai_has_no_words(self):
        with (
            patch.object(
                self.resolver,
                "_load_embedded_metadata",
                return_value={"civitai": {"trainedWords": ["1girl"]}},
            ),
            patch.object(self.resolver, "_load_civitai_metadata_by_hash", return_value=None),
            patch.object(
                self.resolver,
                "_load_civarchive_metadata_by_hash",
                return_value={"civitai": {"trainedWords": ["archive_tag"]}},
            ),
        ):
            result = self.resolver.resolve_path(
                lora_path=r"C:\tmp\archive_tag_v1.safetensors",
                trigger_word_source="metadata",
                enable_civitai_fallback=True,
            )

        self.assertEqual(result, "archive_tag")

    def test_metadata_does_not_call_civarchive_when_civitai_fallback_is_sufficient(self):
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
            patch.object(self.resolver, "_load_civarchive_metadata_by_hash") as civarchive_loader,
        ):
            result = self.resolver.resolve_path(
                lora_path=r"C:\tmp\hero_tag_v1.safetensors",
                trigger_word_source="metadata",
                enable_civitai_fallback=True,
            )

        self.assertEqual(result, "hero_tag")
        civarchive_loader.assert_not_called()

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

    def test_json_sample_prompt_uses_civarchive_fallback_when_civitai_is_empty(self):
        with (
            patch.object(self.resolver, "_load_json_metadata", return_value=None),
            patch.object(self.resolver, "_load_embedded_metadata", return_value=None),
            patch.object(self.resolver, "_load_civitai_metadata_by_hash", return_value=None),
            patch.object(
                self.resolver,
                "_load_civarchive_metadata_by_hash",
                return_value={
                    "civitai": {
                        "images": [
                            {
                                "meta": {
                                    "prompt": "<lora:archive_tag:1>, archive_tag, dramatic light"
                                }
                            }
                        ]
                    }
                },
            ),
        ):
            result = self.resolver.resolve_path(
                lora_path=r"C:\tmp\archive_tag.safetensors",
                trigger_word_source="json_sample_prompt",
                enable_civitai_fallback=True,
            )

        self.assertEqual(result, "archive_tag, dramatic light")

    def test_metadata_uses_filename_fallback_when_embedded_metadata_is_missing(self):
        with patch.object(self.resolver, "_load_embedded_metadata", return_value=None):
            result = self.resolver.resolve_path(
                lora_path=r"C:\tmp\hero-tag_v1-step10.safetensors",
                trigger_word_source="metadata",
                enable_civitai_fallback=False,
            )

        self.assertEqual(result, "hero tag")

    def test_json_combined_reports_no_trigger_needed_for_style_model_with_empty_trained_words(self):
        metadata = {
            "civitai": {
                "trainedWords": [],
                "model": {
                    "name": "Watercolor Style",
                    "tags": ["style"],
                },
            }
        }

        with patch.object(
            self.resolver,
            "_get_metadata_with_optional_fallback",
            return_value=(metadata, "Civitai by-hash fallback"),
        ):
            result = self.resolver.resolve_path(
                lora_path=r"C:\tmp\watercolor_style.safetensors",
                trigger_word_source="json_combined",
                enable_civitai_fallback=True,
            )
            downstream = self.resolver.resolve_output_path(
                lora_path=r"C:\tmp\watercolor_style.safetensors",
                trigger_word_source="json_combined",
                enable_civitai_fallback=True,
            )

        self.assertIn("明示トリガーワード不要モデル", result)
        self.assertEqual(downstream, "")

    def test_metadata_reports_no_trigger_needed_for_style_placeholder(self):
        with patch.object(
            self.resolver,
            "_load_embedded_metadata",
            return_value={"civitai": {"trainedWords": [self.resolver.STYLE_PLACEHOLDER]}},
        ):
            result = self.resolver.resolve_path(
                lora_path=r"C:\tmp\stylistic_pack.safetensors",
                trigger_word_source="metadata",
                enable_civitai_fallback=False,
            )

        self.assertIn("明示トリガーワード不要モデル", result)
        self.assertNotIn(self.resolver.STYLE_PLACEHOLDER, result)

    def test_metadata_does_not_use_filename_fallback_for_empty_slider_metadata(self):
        with (
            patch.object(self.resolver, "_load_embedded_metadata", return_value=None),
            patch.object(
                self.resolver,
                "_load_civitai_metadata_by_hash",
                return_value={
                    "civitai": {
                        "trainedWords": [],
                        "model": {
                            "name": "Contrast Slider",
                            "tags": ["slider"],
                        },
                    }
                },
            ),
            patch.object(self.resolver, "_load_civarchive_metadata_by_hash", return_value=None),
        ):
            result = self.resolver.resolve_path(
                lora_path=r"C:\tmp\contrast-slider_v1.safetensors",
                trigger_word_source="metadata",
                enable_civitai_fallback=True,
            )

        self.assertIn("明示トリガーワード不要モデル", result)
        self.assertNotIn("contrast slider", result.lower())

    def test_json_combined_reports_no_trigger_needed_for_detail_model_with_name_derived_words(self):
        metadata = {
            "_embedded_raw_metadata": {
                "modelspec.description": "Available on Civitai - https://civitai.com/user/example",
            },
            "civitai": {
                "trainedWords": ["addmicrodetails"],
            },
            "model_name": "AddMicroDetails_Illustrious",
        }

        with patch.object(
            self.resolver,
            "_get_metadata_with_optional_fallback",
            return_value=(metadata, "embedded metadata"),
        ):
            result = self.resolver.resolve_path(
                lora_path=r"C:\tmp\AddMicroDetails_Illustrious_v5.safetensors",
                trigger_word_source="json_combined",
                enable_civitai_fallback=False,
            )
            downstream = self.resolver.resolve_output_path(
                lora_path=r"C:\tmp\AddMicroDetails_Illustrious_v5.safetensors",
                trigger_word_source="json_combined",
                enable_civitai_fallback=False,
        )

        self.assertIn("明示トリガーワード不要モデル", result)
        self.assertEqual(downstream, "")

    def test_metadata_uses_bundled_huggingface_reference_before_remote_fallback(self):
        with (
            patch.object(self.resolver, "_load_embedded_metadata", return_value=None),
            patch.object(
                self.resolver,
                "_load_huggingface_reference_metadata",
                return_value={"civitai": {"trainedWords": ["69,ass focus"]}},
            ),
            patch.object(self.resolver, "_load_civitai_metadata_by_hash") as civitai_loader,
            patch.object(self.resolver, "_load_civarchive_metadata_by_hash") as civarchive_loader,
        ):
            result = self.resolver.resolve_path(
                lora_path=r"C:\tmp\69_ass_focus_v1_Illustrious.safetensors",
                trigger_word_source="metadata",
                enable_civitai_fallback=True,
            )

        self.assertEqual(result, "69,ass focus")
        civitai_loader.assert_not_called()
        civarchive_loader.assert_not_called()

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
            result["primary_url"],
            "https://civitai.com/models/123?modelVersionId=456",
        )
        self.assertEqual(
            result["civitai_url"],
            "https://civitai.com/models/123?modelVersionId=456",
        )
        self.assertEqual(result["source_label"], "local metadata")
        self.assertEqual(result["card_data"]["model_id"], "123")

    def test_model_card_accepts_top_level_civitai_payload(self):
        with patch.object(
            self.resolver,
            "_load_json_metadata",
            return_value={
                "id": 456,
                "modelId": 123,
                "name": "v1.0",
                "model": {"name": "Hero LoRA"},
            },
        ):
            result = self.resolver.resolve_model_card_path(
                lora_path=r"C:\tmp\hero_tag.info",
                enable_civitai_fallback=False,
            )

        self.assertTrue(result["success"])
        self.assertEqual(
            result["primary_url"],
            "https://civitai.com/models/123?modelVersionId=456",
        )
        self.assertEqual(
            result["civitai_url"],
            "https://civitai.com/models/123?modelVersionId=456",
        )
        self.assertEqual(result["source_label"], "local metadata")
        self.assertEqual(result["card_data"]["version_name"], "v1.0")

    def test_model_card_prefers_civarchive_hash_when_local_metadata_has_no_ids(self):
        with (
            patch.object(self.resolver, "_load_json_metadata", return_value={"civitai": {}}),
            patch.object(
                self.resolver,
                "_load_civarchive_metadata_by_hash",
                return_value={
                    "civitai": {
                        "id": 789,
                        "modelId": 321,
                        "name": "archive-v2",
                        "model": {"name": "Fallback Hero"},
                        "meta": {
                            "canonical": "https://civarchive.com/models/321?modelVersionId=789"
                        },
                        "source": "civarchive",
                    }
                },
            ),
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
            result["primary_url"],
            "https://civarchive.com/models/321?modelVersionId=789",
        )
        self.assertEqual(
            result["civitai_url"],
            "https://civitai.com/models/321?modelVersionId=789",
        )
        self.assertEqual(
            result["civarchive_url"],
            "https://civarchive.com/models/321?modelVersionId=789",
        )
        self.assertEqual(
            result["alternate_urls"],
            {
                "civitai": "https://civitai.com/models/321?modelVersionId=789",
                "civarchive": "https://civarchive.com/models/321?modelVersionId=789",
            },
        )
        self.assertEqual(result["url_source"], "civarchive")
        self.assertEqual(result["source_label"], "CivArchive by-hash fallback/cache")

    def test_model_card_falls_back_to_civitai_hash_when_civarchive_has_no_ids(self):
        with (
            patch.object(self.resolver, "_load_json_metadata", return_value={"civitai": {}}),
            patch.object(self.resolver, "_load_civarchive_metadata_by_hash", return_value=None),
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
            result["primary_url"],
            "https://civitai.com/models/321?modelVersionId=789",
        )
        self.assertEqual(
            result["civitai_url"],
            "https://civitai.com/models/321?modelVersionId=789",
        )
        self.assertIsNone(result["civarchive_url"])
        self.assertEqual(
            result["alternate_urls"],
            {
                "civitai": "https://civitai.com/models/321?modelVersionId=789",
                "civarchive": None,
            },
        )
        self.assertEqual(result["url_source"], "civitai")
        self.assertEqual(result["source_label"], "Civitai by-hash fallback/cache")

    def test_model_card_failure_returns_provider_neutral_contract(self):
        with (
            patch.object(self.resolver, "_load_json_metadata", return_value=None),
            patch.object(self.resolver, "_load_huggingface_reference_metadata", return_value=None),
            patch.object(self.resolver, "_load_civarchive_metadata_by_hash", return_value=None),
            patch.object(self.resolver, "_load_civitai_metadata_by_hash", return_value=None),
        ):
            result = self.resolver.resolve_model_card_path(
                lora_path=r"C:\tmp\missing_card.safetensors",
                enable_civitai_fallback=True,
            )

        self.assertFalse(result["success"])
        self.assertIsNone(result["primary_url"])
        self.assertIsNone(result["civitai_url"])
        self.assertIsNone(result["civarchive_url"])
        self.assertIn("Model card URL を解決できませんでした。", result["display_text"])
        self.assertIn("Bundled Hugging Face reference metadata: not found", result["display_text"])
        self.assertIn("CivArchive by-hash fallback/cache: not found", result["display_text"])
        self.assertIn("Civitai by-hash fallback/cache: not found", result["display_text"])

    def test_model_card_failure_reports_huggingface_reference_trigger_words(self):
        with (
            patch.object(self.resolver, "_load_json_metadata", return_value=None),
            patch.object(
                self.resolver,
                "_load_huggingface_reference_metadata",
                return_value={
                    "civitai": {"trainedWords": ["69,ass focus"]},
                    "_huggingface_reference": {
                        "source": "https://huggingface.co/example",
                        "model_key": "69_ass_focus_v1_Illustrious",
                    },
                },
            ),
            patch.object(self.resolver, "_load_civarchive_metadata_by_hash", return_value=None),
            patch.object(self.resolver, "_load_civitai_metadata_by_hash", return_value=None),
        ):
            result = self.resolver.resolve_model_card_path(
                lora_path=r"C:\tmp\69_ass_focus_v1_Illustrious.safetensors",
                enable_civitai_fallback=True,
            )

        self.assertFalse(result["success"])
        self.assertIn("recognized bundled reference entry", result["display_text"])
        self.assertIn("69,ass focus", result["display_text"])


class TriggerWordMetadataRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.repository = TriggerWordMetadataRepository()

    def test_load_json_metadata_merges_metadata_json_and_info(self):
        lora_path = r"C:\tmp\hero_tag.safetensors"
        metadata_json_path = r"C:\tmp\hero_tag.metadata.json"
        info_path = r"C:\tmp\hero_tag.info"
        payloads = {
            metadata_json_path: json.dumps({"civitai": {"trainedWords": ["hero_tag"]}}),
            info_path: json.dumps(
                {
                    "id": 456,
                    "modelId": 123,
                    "name": "v1.0",
                    "model": {"name": "Hero LoRA"},
                }
            ),
        }

        def fake_exists(path):
            return path in payloads

        def fake_open(path, *args, **kwargs):
            if path not in payloads:
                raise FileNotFoundError(path)
            return mock_open(read_data=payloads[path])()

        with (
            patch.object(trigger_word_repository.os.path, "exists", side_effect=fake_exists),
            patch("builtins.open", side_effect=fake_open),
        ):
            result = self.repository.load_json_metadata(lora_path)

        self.assertEqual(result["civitai"]["trainedWords"], ["hero_tag"])
        self.assertEqual(result["modelId"], 123)
        card = self.repository.build_civitai_model_card(result)
        self.assertIsNotNone(card)
        self.assertEqual(
            card["civitai_url"],
            "https://civitai.com/models/123?modelVersionId=456",
        )

    def test_load_huggingface_reference_metadata_matches_embedded_title(self):
        with (
            patch.object(
                self.repository,
                "_read_safetensors_metadata",
                return_value={
                    "ss_output_name": "69_ass_focus_v1_Illustrious",
                    "modelspec.title": "69_ass_focus_v1_Illustrious",
                },
            ),
            patch.object(
                self.repository,
                "_load_huggingface_reference_catalog",
                return_value=[
                    {
                        "source": "https://huggingface.co/example",
                        "model_key": "69_ass_focus_v1_Illustrious",
                        "aliases": ["69_ass_focus_v1_Illustrious"],
                        "sd_version": "SDXL",
                        "activation_text": "69,ass focus",
                        "description": "sample",
                        "text_body": "sample text",
                    }
                ],
            ),
        ):
            result = self.repository.load_huggingface_reference_metadata(
                r"C:\tmp\renamed_model.safetensors"
            )

        self.assertEqual(result["civitai"]["trainedWords"], ["69,ass focus"])
        self.assertEqual(result["model_name"], "69_ass_focus_v1_Illustrious")
        self.assertEqual(
            result["_huggingface_reference"]["source"],
            "https://huggingface.co/example",
        )

    def test_load_embedded_metadata_ignores_reference_description_urls(self):
        with patch.object(
            self.repository,
            "_read_safetensors_metadata",
            return_value={
                "modelspec.description": "Available on Civitai - https://civitai.com/user/example",
                "ss_output_name": "AddMicroDetails_Illustrious",
                "ss_tag_frequency": json.dumps(
                    {
                        "4_addmicrodetails clothes": {
                            "addmicrodetails": 50,
                            "solo": 23,
                        }
                    }
                ),
                "ss_dataset_dirs": json.dumps(
                    {
                        "4_addmicrodetails clothes": {
                            "img_count": 50,
                        }
                    }
                ),
                "ss_num_train_images": "50",
            },
        ):
            result = self.repository.load_embedded_metadata(
                r"C:\tmp\AddMicroDetails_Illustrious_v5.safetensors"
            )

        self.assertEqual(result["civitai"]["trainedWords"], ["addmicrodetails"])

    def test_build_civitai_model_card_details_sanitizes_description_and_images(self):
        details = self.repository.build_civitai_model_card_details(
            {
                "civitai": {
                    "id": 456,
                    "modelId": 123,
                    "name": "v1.0",
                    "model": {"name": "Hero LoRA", "type": "LORA"},
                    "baseModel": "SDXL",
                    "trainedWords": ["hero_tag", "cinematic light"],
                    "description": "<p>Hello <strong>world</strong></p><ul><li>line one</li></ul>",
                    "stats": {"downloadCount": 10, "thumbsUpCount": 3},
                    "images": [
                        {
                            "url": "https://example.com/1.jpg",
                            "width": 1024,
                            "height": 1024,
                            "meta": {"prompt": "hero_tag, cinematic light"},
                        }
                    ],
                }
            }
        )

        self.assertIsNotNone(details)
        self.assertEqual(details["model_type"], "LORA")
        self.assertEqual(details["base_model"], "SDXL")
        self.assertEqual(details["trained_words"], ["hero_tag", "cinematic light"])
        self.assertIn("Hello world", details["description"])
        self.assertEqual(details["images"][0]["media_type"], "image")
        self.assertIsNone(details["images"][0]["poster_url"])
        self.assertEqual(details["images"][0]["prompt"], "hero_tag, cinematic light")

    def test_build_model_card_prefers_civarchive_canonical_url(self):
        card = self.repository.build_model_card(
            {
                "civitai": {
                    "id": 456,
                    "modelId": 123,
                    "name": "archive-v1",
                    "model": {"name": "Hero LoRA"},
                    "meta": {
                        "canonical": "https://civarchive.com/models/123?modelVersionId=456"
                    },
                    "source": "civarchive",
                }
            }
        )

        self.assertIsNotNone(card)
        self.assertEqual(
            card["primary_url"],
            "https://civarchive.com/models/123?modelVersionId=456",
        )
        self.assertEqual(
            card["civarchive_url"],
            "https://civarchive.com/models/123?modelVersionId=456",
        )
        self.assertEqual(
            card["civitai_url"],
            "https://civitai.com/models/123?modelVersionId=456",
        )
        self.assertEqual(card["url_source"], "civarchive")

    def test_build_model_card_details_preserves_video_preview_metadata(self):
        details = self.repository.build_model_card_details(
            {
                "civitai": {
                    "id": 2306421,
                    "modelId": 1741501,
                    "name": "Wan2.2 - I2V - HIGH 14B",
                    "model": {"name": "Example Video LoRA", "type": "LORA"},
                    "images": [
                        {
                            "url": "https://c.genur.art/809a852f-b514-4336-89ca-dfcefd274df6",
                            "video_url": "https://c.genur.art/809a852f-b514-4336-89ca-dfcefd274df6",
                            "image_url": "https://vid.genur.art/unsafe/450x0/example",
                            "type": "video",
                            "width": 480,
                            "height": 720,
                            "meta": {"prompt": "sample prompt"},
                        }
                    ],
                }
            }
        )

        self.assertIsNotNone(details)
        self.assertEqual(details["images"][0]["media_type"], "video")
        self.assertEqual(
            details["images"][0]["url"],
            "https://c.genur.art/809a852f-b514-4336-89ca-dfcefd274df6",
        )
        self.assertEqual(
            details["images"][0]["poster_url"],
            "https://vid.genur.art/unsafe/450x0/example",
        )

    def test_build_model_card_details_uses_genur_gallery_fallback_when_images_missing(self):
        repository = TriggerWordMetadataRepository(
            genur_client=DummyGenurGalleryClient(
                payload={
                    "results": [
                        {
                            "id": 120918894,
                            "type": "image",
                            "url": "https://img.genur.art/example-1.webp",
                            "prompt": "sample gallery prompt",
                            "width": 832,
                            "height": 1216,
                        },
                        {
                            "id": 120918895,
                            "type": "video",
                            "video_url": "https://c.genur.art/example-video",
                            "image_url": "https://vid.genur.art/example-poster.webp",
                            "prompt": "sample gallery video",
                        },
                    ]
                }
            )
        )

        details = repository.build_model_card_details(
            {
                "civitai": {
                    "id": 2685238,
                    "modelId": 2385403,
                    "civitai_model_id": 2385403,
                    "civitai_model_version_id": 2685238,
                    "name": "AnimaP_NP43iV2",
                    "model": {"name": "Example Gallery LoRA", "type": "LORA"},
                    "images": [],
                    "nsfwLevel": 31,
                }
            }
        )

        self.assertIsNotNone(details)
        self.assertEqual(details["civitai_version_id"], "2685238")
        self.assertEqual(details["images"][0]["url"], "https://img.genur.art/example-1.webp")
        self.assertEqual(details["images"][0]["prompt"], "sample gallery prompt")
        self.assertEqual(details["images"][1]["media_type"], "video")
        self.assertEqual(details["images"][1]["url"], "https://c.genur.art/example-video")
        self.assertEqual(
            details["images"][1]["poster_url"],
            "https://vid.genur.art/example-poster.webp",
        )
        self.assertEqual(
            repository._genur_client.calls,
            [
                {
                    "model_version_id": 2685238,
                    "is_nsfw": True,
                    "sort": "top",
                }
            ],
        )


class DummyCivitaiClient:
    def __init__(self, payload=None, warning_message=None):
        self.payload = payload
        self.warning_message = warning_message
        self.calls = []

    def fetch_model_version_by_hash(self, sha256_hash):
        self.calls.append(sha256_hash)
        return self.payload, self.warning_message


class DummyGenurGalleryClient:
    def __init__(self, payload=None, warning_message=None):
        self.payload = payload
        self.warning_message = warning_message
        self.calls = []

    def fetch_model_gallery(self, model_version_id, *, is_nsfw=None, sort="top"):
        self.calls.append(
            {
                "model_version_id": model_version_id,
                "is_nsfw": is_nsfw,
                "sort": sort,
            }
        )
        return self.payload, self.warning_message


class CivitaiMetadataProviderTests(unittest.TestCase):
    def test_load_metadata_by_hash_uses_cache_when_available(self):
        client = DummyCivitaiClient(payload={"trainedWords": ["hero_tag"]})
        provider = CivitaiMetadataProvider(
            client=client,
            cache_path=r"C:\tmp\civitai_model_info_cache.json",
        )

        with (
            patch.object(provider, "calculate_sha256", return_value="abc123"),
            patch.object(provider, "load_cache", return_value={"abc123": {"trainedWords": ["cached"]}}),
        ):
            result = provider.load_metadata_by_hash(r"C:\tmp\hero_tag.safetensors")

        self.assertEqual(result, {"trainedWords": ["cached"]})
        self.assertEqual(client.calls, [])

    def test_load_metadata_by_hash_fetches_and_persists_on_cache_miss(self):
        payload = {"trainedWords": ["hero_tag"]}
        client = DummyCivitaiClient(payload=payload)
        provider = CivitaiMetadataProvider(
            client=client,
            cache_path=r"C:\tmp\civitai_model_info_cache.json",
        )

        with (
            patch.object(provider, "calculate_sha256", return_value="deadbeef"),
            patch.object(provider, "load_cache", return_value={}),
            patch.object(provider, "save_cache") as save_cache,
        ):
            result = provider.load_metadata_by_hash(r"C:\tmp\hero_tag.safetensors")

        self.assertEqual(result, payload)
        self.assertEqual(client.calls, ["deadbeef"])
        save_cache.assert_called_once_with({"deadbeef": payload})




class DummyCivArchiveClient:
    def __init__(self, hash_payload=None, version_payload=None, warning_message=None):
        self.hash_payload = hash_payload
        self.version_payload = version_payload
        self.warning_message = warning_message
        self.hash_calls = []
        self.version_calls = []

    def fetch_model_version_by_hash(self, sha256_hash):
        self.hash_calls.append(sha256_hash)
        return self.hash_payload, self.warning_message

    def fetch_model_version(self, model_id, version_id=None):
        self.version_calls.append((model_id, version_id))
        return self.version_payload, self.warning_message


class CivArchiveMetadataProviderTests(unittest.TestCase):
    def test_load_metadata_by_hash_normalizes_civarchive_payload(self):
        payload = {
            "data": {
                "id": 1746460,
                "name": "Mixplin Style [Illustrious]",
                "type": "LORA",
                "description": "description",
                "is_nsfw": True,
                "nsfw_level": 31,
                "tags": ["art", "style"],
                "creator_username": "Ty_Lee",
                "creator_name": "Ty_Lee",
                "creator_url": "/users/Ty_Lee",
                "version": {
                    "id": 1976567,
                    "modelId": 1746460,
                    "name": "v1.0",
                    "baseModel": "Illustrious",
                    "downloadCount": 437,
                    "ratingCount": 0,
                    "rating": 0,
                    "nsfw_level": 31,
                    "trigger": ["mxpln"],
                    "files": [
                        {
                            "id": 1874043,
                            "name": "mxpln-illustrious-ty_lee.safetensors",
                            "type": "Model",
                            "sizeKB": 223124.37109375,
                            "downloadUrl": "https://civitai.com/api/download/models/1976567",
                            "sha256": "e2b7a280d6539556f23f380b3f71e4e22bc4524445c4c96526e117c6005c6ad3",
                            "mirrors": [
                                {
                                    "filename": "mxpln-illustrious-ty_lee.safetensors",
                                    "url": "https://civitai.com/api/download/models/1976567",
                                    "deletedAt": None,
                                }
                            ],
                        }
                    ],
                    "images": [
                        {
                            "id": 86403595,
                            "url": "https://img.genur.art/example.png",
                            "nsfwLevel": 1,
                        }
                    ],
                },
            }
        }
        client = DummyCivArchiveClient(hash_payload=payload)
        provider = CivArchiveMetadataProvider(
            client=client,
            cache_path=r"C:\tmp\civarchive_model_info_cache.json",
        )

        with (
            patch.object(provider, "calculate_sha256", return_value="abc123"),
            patch.object(provider, "load_cache", return_value={}),
            patch.object(provider, "save_cache"),
        ):
            result = provider.load_metadata_by_hash(r"C:\tmp\hero_tag.safetensors")

        self.assertEqual(result["id"], 1976567)
        self.assertEqual(result["trainedWords"], ["mxpln"])
        self.assertEqual(result["nsfwLevel"], 31)
        self.assertEqual(result["stats"], {"downloadCount": 437, "ratingCount": 0, "rating": 0})
        self.assertEqual(result["model"]["name"], "Mixplin Style [Illustrious]")
        self.assertEqual(result["creator"]["username"], "Ty_Lee")
        self.assertEqual(result["files"][0]["hashes"]["SHA256"], "E2B7A280D6539556F23F380B3F71E4E22BC4524445C4C96526E117C6005C6AD3")
        self.assertEqual(result["source"], "civarchive")
        self.assertEqual(client.hash_calls, ["abc123"])

    def test_load_metadata_by_hash_resolves_version_from_file_reference(self):
        file_only_payload = {
            "data": {
                "files": [
                    {
                        "model_id": 1746460,
                        "model_version_id": 1976567,
                    }
                ]
            }
        }
        version_payload = {
            "data": {
                "id": 1746460,
                "name": "Mixplin Style [Illustrious]",
                "type": "LORA",
                "version": {
                    "id": 1976567,
                    "modelId": 1746460,
                    "name": "v1.0",
                    "trigger": ["mxpln"],
                },
            }
        }
        client = DummyCivArchiveClient(
            hash_payload=file_only_payload,
            version_payload=version_payload,
        )
        provider = CivArchiveMetadataProvider(
            client=client,
            cache_path=r"C:\tmp\civarchive_model_info_cache.json",
        )

        with (
            patch.object(provider, "calculate_sha256", return_value="deadbeef"),
            patch.object(provider, "load_cache", return_value={}),
            patch.object(provider, "save_cache"),
        ):
            result = provider.load_metadata_by_hash(r"C:\tmp\hero_tag.safetensors")

        self.assertEqual(result["id"], 1976567)
        self.assertEqual(result["trainedWords"], ["mxpln"])
        self.assertEqual(client.hash_calls, ["deadbeef"])
        self.assertEqual(client.version_calls, [(1746460, 1976567)])
if __name__ == "__main__":
    unittest.main()
