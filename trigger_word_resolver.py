"""Trigger word resolution logic for LoRA metadata and fallback APIs."""

from __future__ import annotations

import os
import random

try:
    import folder_paths
except ImportError:
    folder_paths = None

try:
    from .constants import PREVIEW_PREFIX
    from .trigger_word_analyzer import TriggerWordAnalyzer
    from .trigger_word_repository import (
        SAFETENSORS_AVAILABLE,
        TriggerWordMetadataRepository,
    )
except ImportError:
    from constants import PREVIEW_PREFIX
    from trigger_word_analyzer import TriggerWordAnalyzer
    from trigger_word_repository import (
        SAFETENSORS_AVAILABLE,
        TriggerWordMetadataRepository,
    )


class TriggerWordResolver:
    CACHE_FILENAME = TriggerWordMetadataRepository.CACHE_FILENAME
    STYLE_PLACEHOLDER = TriggerWordAnalyzer.STYLE_PLACEHOLDER
    FALLBACK_SCORE_THRESHOLD = TriggerWordAnalyzer.FALLBACK_SCORE_THRESHOLD
    MAX_DESCRIPTION_CANDIDATE_LENGTH = TriggerWordAnalyzer.MAX_DESCRIPTION_CANDIDATE_LENGTH
    GENERIC_TAGS = TriggerWordAnalyzer.GENERIC_TAGS

    def __init__(self, analyzer=None, metadata_repository=None):
        self._analyzer = analyzer or TriggerWordAnalyzer()
        self._metadata_repository = metadata_repository or TriggerWordMetadataRepository(
            analyzer=self._analyzer
        )

    def resolve(self, lora_name, trigger_word_source, enable_civitai_fallback):
        if folder_paths is None:
            raise RuntimeError("folder_paths is not available outside ComfyUI")

        lora_path = folder_paths.get_full_path_or_raise("loras", lora_name)
        return self.resolve_path(
            lora_path=lora_path,
            trigger_word_source=trigger_word_source,
            enable_civitai_fallback=enable_civitai_fallback,
        )

    def resolve_path(self, lora_path, trigger_word_source, enable_civitai_fallback):
        source_handlers = {
            "json_sample_prompt": self._get_sample_prompt_text,
            "json_random": self._get_trigger_words_random,
            "metadata": self._get_trigger_words_from_embedded,
            "json_combined": self._get_trigger_words_combined,
        }
        handler = source_handlers.get(trigger_word_source, self._get_trigger_words_combined)
        return handler(
            lora_path=str(lora_path),
            enable_civitai_fallback=enable_civitai_fallback,
        )

    def resolve_output(self, lora_name, trigger_word_source, enable_civitai_fallback):
        return self._coerce_downstream_text(
            self.resolve(
                lora_name=lora_name,
                trigger_word_source=trigger_word_source,
                enable_civitai_fallback=enable_civitai_fallback,
            )
        )

    def resolve_output_path(self, lora_path, trigger_word_source, enable_civitai_fallback):
        return self._coerce_downstream_text(
            self.resolve_path(
                lora_path=lora_path,
                trigger_word_source=trigger_word_source,
                enable_civitai_fallback=enable_civitai_fallback,
            )
        )

    def resolve_model_card(self, lora_name, enable_civitai_fallback):
        if folder_paths is None:
            raise RuntimeError("folder_paths is not available outside ComfyUI")

        lora_path = folder_paths.get_full_path_or_raise("loras", lora_name)
        return self.resolve_model_card_path(
            lora_path=lora_path,
            enable_civitai_fallback=enable_civitai_fallback,
        )

    def resolve_model_card_path(self, lora_path, enable_civitai_fallback):
        local_metadata = self._load_json_metadata(lora_path)
        local_card = self._build_model_card(local_metadata)
        if local_card:
            return self._format_model_card_result(local_card, "local metadata", local_metadata)

        fallback_results = []
        if enable_civitai_fallback:
            for fallback_label, fallback_loader in self._iter_model_card_fallback_loaders():
                fallback_metadata = fallback_loader(lora_path)
                fallback_results.append((fallback_label, fallback_metadata))
                fallback_card = self._build_model_card(fallback_metadata)
                if fallback_card:
                    return self._format_model_card_result(
                        fallback_card,
                        fallback_label,
                        fallback_metadata,
                    )

        lora_name = os.path.basename(str(lora_path))
        diagnostic_lines = [
            f"Local metadata: {self._describe_model_card_metadata(local_metadata)}",
        ]
        if enable_civitai_fallback:
            if fallback_results:
                diagnostic_lines.extend(
                    f"{label}: {self._describe_model_card_metadata(metadata)}"
                    for label, metadata in fallback_results
                )
            else:
                diagnostic_lines.append("Remote fallback: no providers configured")
        else:
            diagnostic_lines.append("Remote fallback: disabled")

        display_text = (
            f"[Browse] {lora_name}\n"
            "Model card URL を解決できませんでした。\n"
            + "\n".join(diagnostic_lines)
        )

        return {
            "success": False,
            "primary_url": None,
            "civitai_url": None,
            "civarchive_url": None,
            "model_id": None,
            "version_id": None,
            "model_name": None,
            "version_name": None,
            "source_label": None,
            "display_text": display_text,
        }

    def _get_trigger_words_combined(self, lora_path, enable_civitai_fallback):
        metadata, source_label = self._get_metadata_with_optional_fallback(
            lora_path=lora_path,
            enable_civitai_fallback=enable_civitai_fallback,
            require_images=False,
            prefer_embedded_only=False,
        )
        trained_words = self._extract_usable_trained_words(metadata)
        if not trained_words and self._indicates_trigger_words_optional(metadata, lora_path):
            return self._no_trigger_words_message(lora_path, metadata, source_label)
        if not trained_words:
            return self._failure_message(
                lora_path,
                "トリガーワードが見つかりません。trainedWords、埋め込みメタデータ"
                "（ss_tag_frequency、modelspec.trigger_phrase、modelspec.trigger_word、"
                "modelspec.usage_hint、modelspec.description）を確認しました。"
                + self._fallback_suffix(enable_civitai_fallback, source_label),
            )

        all_words = []
        for pattern in trained_words:
            cleaned_pattern = self._remove_lora_syntax(pattern)
            all_words.extend(word.strip() for word in cleaned_pattern.split(","))

        unique_words = []
        seen = set()
        for word in all_words:
            lowered = word.lower()
            if word and lowered not in seen:
                unique_words.append(word)
                seen.add(lowered)

        if not unique_words:
            return self._failure_message(
                lora_path,
                "候補は見つかりましたが、整形後に空になりました。",
            )
        return ", ".join(unique_words)

    def _get_trigger_words_random(self, lora_path, enable_civitai_fallback):
        metadata, source_label = self._get_metadata_with_optional_fallback(
            lora_path=lora_path,
            enable_civitai_fallback=enable_civitai_fallback,
            require_images=False,
            prefer_embedded_only=False,
        )
        trained_words = self._extract_usable_trained_words(metadata)
        if not trained_words and self._indicates_trigger_words_optional(metadata, lora_path):
            return self._no_trigger_words_message(lora_path, metadata, source_label)
        if not trained_words:
            return self._failure_message(
                lora_path,
                "ランダム選択できるトリガーワード候補が見つかりません。"
                + self._fallback_suffix(enable_civitai_fallback, source_label),
            )

        selected = self._remove_lora_syntax(random.choice(trained_words)).strip()
        if not selected:
            return self._failure_message(
                lora_path,
                "トリガーワード候補は見つかりましたが、整形後に空になりました。",
            )
        return selected

    def _get_sample_prompt_text(self, lora_path, enable_civitai_fallback):
        metadata, source_label = self._get_metadata_with_optional_fallback(
            lora_path=lora_path,
            enable_civitai_fallback=enable_civitai_fallback,
            require_images=True,
            prefer_embedded_only=False,
        )
        civitai_section = self._get_civitai_section(metadata)
        images = civitai_section.get("images", []) if civitai_section else []
        if not images:
            return self._failure_message(
                lora_path,
                "json_sample_prompt 用の sample images が見つかりません。"
                + self._fallback_suffix(enable_civitai_fallback, source_label),
            )

        valid_images = [image for image in images if image.get("meta")]
        if not valid_images:
            return self._failure_message(
                lora_path,
                "sample images は見つかりましたが、images.meta がすべて null か空です。"
                + self._fallback_suffix(enable_civitai_fallback, source_label),
            )

        selected_image = random.choice(valid_images)
        meta = selected_image["meta"]
        positive = self._cleanup_prompt_text(
            self._remove_lora_syntax(meta.get("prompt", ""))
        )
        if not positive:
            return self._failure_message(
                lora_path,
                "sample prompt は見つかりましたが、整形後の positive prompt が空です。",
            )
        return positive

    def _get_trigger_words_from_embedded(self, lora_path, enable_civitai_fallback):
        best_metadata = self._load_embedded_metadata(lora_path)
        source_label = "embedded metadata"

        if enable_civitai_fallback and self._should_attempt_fallback_for_metadata(
            best_metadata,
            lora_path,
            require_images=False,
        ):
            for fallback_label, fallback_loader in self._iter_remote_fallback_loaders():
                if not self._should_attempt_fallback_for_metadata(
                    best_metadata,
                    lora_path,
                    require_images=False,
                ):
                    break
                fallback = fallback_loader(lora_path)
                if self._metadata_satisfies_request(fallback, False, lora_path):
                    best_metadata, source_label = self._pick_better_metadata(
                        current_metadata=best_metadata,
                        current_label=source_label,
                        candidate_metadata=fallback,
                        candidate_label=fallback_label,
                        lora_path=lora_path,
                        require_images=False,
                    )
                    if (
                        best_metadata is fallback
                        and self._extract_usable_trained_words(fallback)
                    ):
                        break

        trained_words = self._extract_usable_trained_words(best_metadata)
        if not trained_words and self._indicates_trigger_words_optional(best_metadata, lora_path):
            return self._no_trigger_words_message(lora_path, best_metadata, source_label)

        if not trained_words and not self._indicates_trigger_words_optional(best_metadata, lora_path):
            filename_fallback = self._build_filename_fallback_metadata(lora_path)
            trained_words = self._extract_usable_trained_words(filename_fallback)
            if trained_words:
                source_label = "filename fallback"

        if not trained_words:
            return self._failure_message(
                lora_path,
                "埋め込みメタデータに使えるトリガーワードがありません。"
                " ss_tag_frequency、modelspec.trigger_phrase、modelspec.trigger_word、"
                "modelspec.usage_hint、modelspec.description を確認しました。"
                + self._fallback_suffix(enable_civitai_fallback, source_label),
            )

        return self._remove_lora_syntax(trained_words[0]).strip()

    def _get_metadata_with_optional_fallback(
        self,
        lora_path,
        enable_civitai_fallback,
        require_images,
        prefer_embedded_only,
    ):
        if prefer_embedded_only:
            metadata = self._load_embedded_metadata(lora_path)
            source_label = "embedded metadata"
        else:
            metadata = self._load_json_metadata(lora_path)
            source_label = "local metadata"

        if self._metadata_satisfies_request(metadata, require_images, lora_path):
            best_metadata = metadata
            best_label = source_label
        else:
            best_metadata = None
            best_label = source_label

        if not prefer_embedded_only:
            embedded = self._load_embedded_metadata(lora_path)
            if self._metadata_satisfies_request(embedded, require_images, lora_path):
                best_metadata, best_label = self._pick_better_metadata(
                    current_metadata=best_metadata,
                    current_label=best_label,
                    candidate_metadata=embedded,
                    candidate_label="embedded metadata",
                    lora_path=lora_path,
                    require_images=require_images,
                )

        if enable_civitai_fallback and self._should_attempt_fallback_for_metadata(
            best_metadata,
            lora_path,
            require_images,
        ):
            for fallback_label, fallback_loader in self._iter_remote_fallback_loaders():
                if not self._should_attempt_fallback_for_metadata(
                    best_metadata,
                    lora_path,
                    require_images,
                ):
                    break
                fallback = fallback_loader(lora_path)
                if self._metadata_satisfies_request(fallback, require_images, lora_path):
                    best_metadata, best_label = self._pick_better_metadata(
                        current_metadata=best_metadata,
                        current_label=best_label,
                        candidate_metadata=fallback,
                        candidate_label=fallback_label,
                        lora_path=lora_path,
                        require_images=require_images,
                    )
                    if best_metadata is fallback:
                        if require_images and self._score_image_metadata(fallback) > 0:
                            break
                        if (
                            not require_images
                            and self._extract_usable_trained_words(fallback)
                        ):
                            break

        if not self._indicates_trigger_words_optional(best_metadata, lora_path):
            filename_fallback = self._build_filename_fallback_metadata(lora_path)
            if self._metadata_satisfies_request(filename_fallback, require_images, lora_path):
                best_metadata, best_label = self._pick_better_metadata(
                    current_metadata=best_metadata,
                    current_label=best_label,
                    candidate_metadata=filename_fallback,
                    candidate_label="filename fallback",
                    lora_path=lora_path,
                    require_images=require_images,
                )

        if best_metadata is not None:
            return best_metadata, best_label

        return metadata, source_label

    def _metadata_satisfies_request(self, metadata, require_images, lora_path=None):
        return self._analyzer.metadata_satisfies_request(metadata, require_images, lora_path)

    def _load_json_metadata(self, lora_path):
        return self._metadata_repository.load_json_metadata(lora_path)

    def _load_embedded_metadata(self, lora_path):
        return self._metadata_repository.load_embedded_metadata(lora_path)

    def _extract_direct_trigger_words(self, raw_metadata):
        return self._analyzer.extract_direct_trigger_words(raw_metadata)

    def _extract_description_candidates(self, value):
        return self._analyzer.extract_description_candidates(value)

    def _extract_short_segments(self, text):
        return self._analyzer.extract_short_segments(text)

    def _looks_like_trigger_candidate(self, text):
        return self._analyzer.looks_like_trigger_candidate(text)

    def _parse_trigger_word_value(self, value):
        return self._analyzer.parse_trigger_word_value(value)

    def _extract_trigger_words_from_tag_frequency(self, raw_metadata):
        return self._analyzer.extract_trigger_words_from_tag_frequency(raw_metadata)

    def _extract_expected_count(
        self,
        dataset_name,
        dataset_dirs,
        total_image_count,
        dataset_count,
    ):
        return self._analyzer.extract_expected_count(
            dataset_name,
            dataset_dirs,
            total_image_count,
            dataset_count,
        )

    def _select_primary_tag_from_dataset(self, dataset_name, tags, expected_count, output_name):
        return self._analyzer.select_primary_tag_from_dataset(
            dataset_name,
            tags,
            expected_count,
            output_name,
        )

    def _score_trigger_candidate(
        self,
        candidate,
        count,
        dataset_name,
        expected_count,
        output_name,
    ):
        return self._analyzer.score_trigger_candidate(
            candidate,
            count,
            dataset_name,
            expected_count,
            output_name,
        )

    def _normalize_dataset_name(self, text):
        return self._analyzer.normalize_dataset_name(text)

    def _normalize_token(self, text):
        return self._analyzer.normalize_token(text)

    def _parse_json_dict(self, value):
        return self._analyzer.parse_json_dict(value)

    def _pick_better_metadata(
        self,
        current_metadata,
        current_label,
        candidate_metadata,
        candidate_label,
        lora_path,
        require_images,
    ):
        return self._analyzer.pick_better_metadata(
            current_metadata,
            current_label,
            candidate_metadata,
            candidate_label,
            lora_path,
            require_images,
        )

    def _should_prefer_fallback(self, local_words, fallback_words, lora_path):
        return self._analyzer.should_prefer_fallback(local_words, fallback_words, lora_path)

    def _should_attempt_fallback_for_metadata(self, metadata, lora_path, require_images):
        return self._analyzer.should_attempt_fallback_for_metadata(
            metadata,
            lora_path,
            require_images,
        )

    def _should_attempt_fallback_for_words(self, trained_words, lora_path):
        return self._analyzer.should_attempt_fallback_for_words(trained_words, lora_path)

    def _score_trained_word_set(self, trained_words, lora_path):
        return self._analyzer.score_trained_word_set(trained_words, lora_path)

    def _score_trigger_phrase_candidate(self, candidate, lora_path):
        return self._analyzer.score_trigger_phrase_candidate(candidate, lora_path)

    def _score_image_metadata(self, metadata):
        return self._analyzer.score_image_metadata(metadata)

    def _get_civitai_section(self, metadata):
        return self._analyzer.get_civitai_section(metadata)

    def _build_filename_fallback_metadata(self, lora_path):
        return self._metadata_repository.build_filename_fallback_metadata(lora_path)

    def _build_filename_fallback_candidates(self, lora_path):
        return self._metadata_repository.build_filename_fallback_candidates(lora_path)

    def _load_civitai_metadata_by_hash(self, lora_path):
        return self._metadata_repository.load_civitai_metadata_by_hash(lora_path)

    def _load_civarchive_metadata_by_hash(self, lora_path):
        return self._metadata_repository.load_civarchive_metadata_by_hash(lora_path)

    def _load_huggingface_reference_metadata(self, lora_path):
        return self._metadata_repository.load_huggingface_reference_metadata(lora_path)

    def _iter_remote_fallback_loaders(self):
        return [
            ("Bundled Hugging Face reference metadata", self._load_huggingface_reference_metadata),
            ("Civitai by-hash fallback", self._load_civitai_metadata_by_hash),
            ("CivArchive by-hash fallback", self._load_civarchive_metadata_by_hash),
        ]

    def _iter_model_card_fallback_loaders(self):
        return [
            ("CivArchive by-hash fallback/cache", self._load_civarchive_metadata_by_hash),
            ("Civitai by-hash fallback/cache", self._load_civitai_metadata_by_hash),
        ]

    def _extract_trained_words(self, metadata):
        return self._analyzer.extract_trained_words(metadata)

    def _extract_usable_trained_words(self, metadata):
        return self._analyzer.extract_usable_trained_words(metadata)

    def _indicates_trigger_words_optional(self, metadata, lora_path):
        return self._analyzer.indicates_trigger_words_optional(metadata, lora_path)

    def _describe_trigger_words_optional(self, metadata, lora_path):
        return self._analyzer.describe_trigger_words_optional(metadata, lora_path)

    def _normalize_civitai_payload(self, payload):
        return self._metadata_repository.normalize_civitai_payload(payload)

    def _build_model_card(self, metadata):
        return self._metadata_repository.build_model_card(metadata)

    def _build_model_card_details(self, metadata):
        return self._metadata_repository.build_model_card_details(metadata)

    def _build_civitai_model_card(self, metadata):
        return self._build_model_card(metadata)

    def _build_civitai_model_card_details(self, metadata):
        return self._build_model_card_details(metadata)

    def _calculate_sha256(self, file_path):
        return self._metadata_repository.calculate_sha256(file_path)

    def _load_civitai_cache(self):
        return self._metadata_repository.load_civitai_cache()

    def _save_civitai_cache(self, cache):
        return self._metadata_repository.save_civitai_cache(cache)

    def _get_cache_path(self):
        return self._metadata_repository.get_cache_path()

    def _failure_message(self, lora_path, reason):
        lora_name = os.path.basename(lora_path)
        message = f"{PREVIEW_PREFIX} {lora_name}: {reason}"
        print(message)
        return message

    def _no_trigger_words_message(self, lora_path, metadata, source_label):
        del source_label
        return self._failure_message(
            lora_path,
            self._describe_trigger_words_optional(metadata, lora_path),
        )

    def _fallback_suffix(self, enable_civitai_fallback, source_label):
        if enable_civitai_fallback:
            if source_label == "Bundled Hugging Face reference metadata":
                return " Bundled Hugging Face reference metadata を使用しました。"
            if source_label == "Civitai by-hash fallback":
                return " Civitai fallback を使用しました。"
            if source_label == "CivArchive by-hash fallback":
                return " CivArchive fallback を使用しました。"
            return " Remote fallback は有効でしたが、使えるデータを返しませんでした。"
        return " Civitai fallback は無効です。"

    def _coerce_downstream_text(self, text):
        cleaned = self._string_or_empty(text).strip()
        if cleaned.startswith(PREVIEW_PREFIX):
            return ""
        return cleaned

    def _format_model_card_result(self, card, source_label, metadata=None):
        model_name = self._string_or_empty(card.get("model_name"))
        version_name = self._string_or_empty(card.get("version_name"))
        title = model_name or "Unknown model"
        primary_url = self._string_or_empty(card.get("primary_url"))
        lines = [
            "[Browse]",
            title,
            f"Source: {source_label}",
            f"Model ID: {card.get('model_id') or '-'}",
            f"Version ID: {card.get('version_id') or '-'}",
        ]
        if version_name:
            lines.append(f"Version Name: {version_name}")
        lines.append(f"URL: {primary_url or '-'}")

        return {
            "success": True,
            "primary_url": primary_url or None,
            "civitai_url": card.get("civitai_url"),
            "civarchive_url": card.get("civarchive_url"),
            "alternate_urls": card.get("alternate_urls") or {},
            "model_id": card.get("model_id"),
            "version_id": card.get("version_id"),
            "model_name": card.get("model_name"),
            "version_name": card.get("version_name"),
            "url_source": card.get("url_source"),
            "source_label": source_label,
            "display_text": "\n".join(lines),
            "card_data": self._build_model_card_details(metadata) if metadata else None,
        }

    def _describe_model_card_metadata(self, metadata):
        if not metadata:
            return "not found"

        card = self._build_model_card(metadata)
        if card:
            version_id = card.get("version_id") or "-"
            url_source = card.get("url_source") or "unknown"
            return (
                f"resolved modelId={card.get('model_id')}, "
                f"versionId={version_id}, urlSource={url_source}"
            )

        civitai_section = self._get_civitai_section(metadata)
        if civitai_section:
            return "found, but modelId/versionId could not be derived"
        return "found, but no civitai-compatible fields were present"

    def _remove_lora_syntax(self, text):
        return self._analyzer.remove_lora_syntax(text)

    def _cleanup_prompt_text(self, text):
        return self._analyzer.cleanup_prompt_text(text)

    def _string_or_empty(self, value):
        return self._analyzer.string_or_empty(value)

    def _coerce_int(self, value):
        return self._analyzer.coerce_int(value)

    def _dedupe_preserve_order(self, values):
        return self._analyzer.dedupe_preserve_order(values)


__all__ = ["SAFETENSORS_AVAILABLE", "TriggerWordResolver"]

