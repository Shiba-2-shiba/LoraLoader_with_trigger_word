"""Trigger word extraction, scoring, and text normalization helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path


class TriggerWordAnalyzer:
    STYLE_PLACEHOLDER = "@style_name"
    FALLBACK_SCORE_THRESHOLD = 20
    MAX_DESCRIPTION_CANDIDATE_LENGTH = 80
    TRIGGER_WORD_OPTIONAL_TAGS = {
        "slider",
        "sliders",
        "style",
        "styles",
    }
    TRIGGER_WORD_OPTIONAL_NAME_HINTS = {
        "slider",
        "sliders",
        "style",
        "styles",
        "detail",
        "details",
        "microdetail",
        "microdetails",
        "enhancer",
        "enhancers",
    }
    GENERIC_TAGS = {
        "1girl",
        "1 boy",
        "1boy",
        "animal ears",
        "blush",
        "breasts",
        "closed eyes",
        "day",
        "gloves",
        "indoors",
        "jacket",
        "large breasts",
        "long hair",
        "multiple girls",
        "night",
        "no humans",
        "open mouth",
        "outdoors",
        "school uniform",
        "shirt",
        "short hair",
        "skirt",
        "smile",
        "solo",
        "weapon",
        "white shirt",
    }

    def metadata_satisfies_request(self, metadata, require_images, lora_path=None):
        if not metadata:
            return False
        if require_images:
            civitai_section = self.get_civitai_section(metadata)
            images = civitai_section.get("images", []) if civitai_section else []
            return any(image.get("meta") for image in images)
        if self.extract_usable_trained_words(metadata):
            return True
        return self.indicates_trigger_words_optional(metadata, lora_path)

    def extract_direct_trigger_words(self, raw_metadata):
        trained_words = []

        for key in ("trained_words", "ss_trained_words"):
            trained_words.extend(self.parse_trigger_word_value(raw_metadata.get(key)))

        for key in (
            "modelspec.trigger_phrase",
            "modelspec.trigger_word",
            "modelspec.usage_hint",
        ):
            value = self.string_or_empty(raw_metadata.get(key, ""))
            if value:
                trained_words.append(value)

        trained_words.extend(
            self.extract_description_candidates(raw_metadata.get("modelspec.description", ""))
        )

        return self.dedupe_preserve_order(trained_words)

    def extract_description_candidates(self, value):
        text = self.string_or_empty(value)
        if not text:
            return []

        if len(text) <= self.MAX_DESCRIPTION_CANDIDATE_LENGTH and "\n" not in text:
            return [text] if self.looks_like_trigger_candidate(text) else []

        candidates = []
        trigger_like_patterns = [
            r"(?:trigger word|trigger phrase|use tag|activation tag|prompt)\s*[:：]\s*([^\n\r]+)",
            r"(?:use with|use)\s*[:：]\s*([^\n\r]+)",
        ]
        for pattern in trigger_like_patterns:
            matches = re.findall(pattern, text, flags=re.IGNORECASE)
            for match in matches:
                candidates.extend(self.extract_short_segments(match))

        candidates.extend(self.extract_short_segments(text))
        return self.dedupe_preserve_order(candidates)

    def extract_short_segments(self, text):
        text = self.string_or_empty(text)
        if not text:
            return []

        raw_segments = re.split(r"[\n\r。！？;；]+", text)
        candidates = []
        for raw_segment in raw_segments:
            segment = self.string_or_empty(raw_segment)
            if not segment:
                continue

            comma_parts = [part.strip() for part in segment.split(",") if part.strip()]
            if len(comma_parts) >= 2:
                compact = ", ".join(comma_parts)
                if self.looks_like_trigger_candidate(compact):
                    candidates.append(compact)
                for part in comma_parts:
                    if self.looks_like_trigger_candidate(part):
                        candidates.append(part)
                continue

            if self.looks_like_trigger_candidate(segment):
                candidates.append(segment)

        return candidates

    def looks_like_trigger_candidate(self, text):
        normalized = self.normalize_token(text)
        if not normalized:
            return False
        if len(text) > self.MAX_DESCRIPTION_CANDIDATE_LENGTH:
            return False
        if len(normalized.split()) > 8:
            return False
        if self.looks_like_reference_text(text):
            return False
        if normalized in self.GENERIC_TAGS:
            return False
        return (
            text.startswith("@")
            or "," in text
            or "_" in text
            or "-" in text
            or 1 <= len(normalized.split()) <= 4
        )

    def looks_like_reference_text(self, text):
        normalized = self.normalize_token(text)
        if not normalized:
            return False
        if "http://" in text or "https://" in text:
            return True
        return normalized.startswith(("available on civitai", "available on civarchive"))

    def parse_trigger_word_value(self, value):
        if value is None:
            return []

        if isinstance(value, (list, tuple)):
            return [self.string_or_empty(item) for item in value if self.string_or_empty(item)]

        text = self.string_or_empty(value)
        if not text:
            return []

        if text.startswith("[") or text.startswith("{"):
            try:
                decoded = json.loads(text)
            except Exception:
                decoded = None
            if isinstance(decoded, list):
                return [self.string_or_empty(item) for item in decoded if self.string_or_empty(item)]
            if isinstance(decoded, str):
                text = decoded

        if "," in text:
            parts = [part.strip() for part in text.split(",")]
            compact_parts = [part for part in parts if part]
            if compact_parts:
                return compact_parts

        return [text]

    def extract_trigger_words_from_tag_frequency(self, raw_metadata):
        raw_tag_frequency = raw_metadata.get("ss_tag_frequency")
        if not raw_tag_frequency:
            return []

        try:
            tag_frequency = json.loads(raw_tag_frequency)
        except Exception:
            return []

        if not isinstance(tag_frequency, dict):
            return []

        dataset_dirs = self.parse_json_dict(raw_metadata.get("ss_dataset_dirs"))
        output_name = self.string_or_empty(raw_metadata.get("ss_output_name", ""))
        total_image_count = self.coerce_int(raw_metadata.get("ss_num_train_images"))

        primary_tags = []
        at_tags = []
        for dataset_name, tags in tag_frequency.items():
            if not isinstance(tags, dict) or not tags:
                continue

            expected_count = self.extract_expected_count(
                dataset_name=dataset_name,
                dataset_dirs=dataset_dirs,
                total_image_count=total_image_count,
                dataset_count=len(tag_frequency),
            )
            best_tag = self.select_primary_tag_from_dataset(
                dataset_name=dataset_name,
                tags=tags,
                expected_count=expected_count,
                output_name=output_name,
            )
            if best_tag:
                primary_tags.append(best_tag)
                if best_tag.startswith("@"):
                    at_tags.append(best_tag)

        primary_tags = self.dedupe_preserve_order(primary_tags)
        if len(primary_tags) >= 4 and len(at_tags) >= 4:
            return [self.STYLE_PLACEHOLDER]

        return primary_tags

    def extract_expected_count(
        self,
        dataset_name,
        dataset_dirs,
        total_image_count,
        dataset_count,
    ):
        dataset_info = dataset_dirs.get(dataset_name, {})
        if isinstance(dataset_info, dict):
            image_count = self.coerce_int(dataset_info.get("img_count"))
            if image_count is not None:
                return image_count

        if dataset_count == 1:
            return total_image_count

        return None

    def select_primary_tag_from_dataset(self, dataset_name, tags, expected_count, output_name):
        best_tag = ""
        best_score = None

        for raw_tag, raw_count in tags.items():
            tag = self.string_or_empty(raw_tag)
            count = self.coerce_int(raw_count)
            if not tag or count is None:
                continue

            score = self.score_trigger_candidate(
                candidate=tag,
                count=count,
                dataset_name=dataset_name,
                expected_count=expected_count,
                output_name=output_name,
            )
            rank = (score, count, len(tag))
            if best_score is None or rank > best_score:
                best_tag = tag
                best_score = rank

        return best_tag

    def score_trigger_candidate(
        self,
        candidate,
        count,
        dataset_name,
        expected_count,
        output_name,
    ):
        normalized_candidate = self.normalize_token(candidate)
        normalized_dataset = self.normalize_dataset_name(dataset_name)
        normalized_output = self.normalize_token(output_name)

        score = int(count)

        if candidate.startswith("@"):
            score += 100000
        if expected_count is not None and count == expected_count:
            score += 50000
        if normalized_dataset and normalized_candidate:
            if normalized_candidate in normalized_dataset:
                score += 30000
            if normalized_dataset in normalized_candidate:
                score += 20000
        if normalized_output and normalized_candidate and normalized_candidate in normalized_output:
            score += 10000
        if normalized_candidate in self.GENERIC_TAGS:
            score -= 20000
        if candidate.startswith("|||"):
            score -= 10000

        return score

    def normalize_dataset_name(self, text):
        text = re.sub(r"^\d+[_\-\s]*", "", self.string_or_empty(text))
        return self.normalize_token(text)

    def normalize_token(self, text):
        text = self.string_or_empty(text).lower().replace("_", " ").replace("-", " ")
        text = re.sub(r"[^0-9a-z@ ]+", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def parse_json_dict(self, value):
        if value is None:
            return {}

        if isinstance(value, dict):
            return value

        text = self.string_or_empty(value)
        if not text:
            return {}

        try:
            decoded = json.loads(text)
        except Exception:
            return {}

        return decoded if isinstance(decoded, dict) else {}

    def pick_better_metadata(
        self,
        current_metadata,
        current_label,
        candidate_metadata,
        candidate_label,
        lora_path,
        require_images,
    ):
        if candidate_metadata is None:
            return current_metadata, current_label
        if current_metadata is None:
            return candidate_metadata, candidate_label

        if require_images:
            current_score = self.score_image_metadata(current_metadata)
            candidate_score = self.score_image_metadata(candidate_metadata)
        else:
            current_score = self.score_metadata_candidate(
                current_metadata,
                lora_path,
                require_images=False,
            )
            candidate_score = self.score_metadata_candidate(
                candidate_metadata,
                lora_path,
                require_images=False,
            )

        if candidate_score > current_score:
            return candidate_metadata, candidate_label
        return current_metadata, current_label

    def should_prefer_fallback(self, local_words, fallback_words, lora_path):
        local_score = self.score_trained_word_set(local_words, lora_path)
        fallback_score = self.score_trained_word_set(fallback_words, lora_path)
        return fallback_score > local_score

    def should_attempt_fallback_for_metadata(self, metadata, lora_path, require_images):
        if metadata is None:
            return True
        if require_images:
            return self.score_image_metadata(metadata) <= 0
        return self.score_metadata_candidate(metadata, lora_path, require_images) < (
            self.FALLBACK_SCORE_THRESHOLD
        )

    def should_attempt_fallback_for_words(self, trained_words, lora_path):
        score = self.score_trained_word_set(trained_words, lora_path)
        return score < self.FALLBACK_SCORE_THRESHOLD

    def score_metadata_candidate(self, metadata, lora_path, require_images):
        if require_images:
            return self.score_image_metadata(metadata)

        trained_words = self.extract_trained_words(metadata)
        score = self.score_trained_word_set(trained_words, lora_path)
        if trained_words:
            return score
        if self.indicates_trigger_words_optional(metadata, lora_path):
            return 0
        return -1

    def score_trained_word_set(self, trained_words, lora_path):
        if not trained_words:
            return -1

        usable_candidates = [
            candidate
            for candidate in trained_words
            if self.string_or_empty(candidate) and candidate != self.STYLE_PLACEHOLDER
        ]
        if usable_candidates:
            return max(
                self.score_trigger_phrase_candidate(candidate, lora_path)
                for candidate in usable_candidates
            )
        if self.STYLE_PLACEHOLDER in trained_words:
            return 0
        return -1

    def score_trigger_phrase_candidate(self, candidate, lora_path):
        text = self.string_or_empty(candidate)
        if not text:
            return -1

        score = len(text)
        normalized_candidate = self.normalize_token(text)
        filename_hint = self.normalize_token(Path(lora_path).stem)

        parts = [part.strip() for part in text.split(",") if part.strip()]
        score += len(parts) * 50
        if text.startswith("@"):
            score += 250
        if text == self.STYLE_PLACEHOLDER:
            score += 500
        if filename_hint and normalized_candidate == filename_hint:
            score -= 200
        elif filename_hint and normalized_candidate and normalized_candidate in filename_hint:
            score -= 75
        if normalized_candidate in self.GENERIC_TAGS:
            score -= 150
        if re.search(r"[A-Z].*[a-z]|[a-z].*[A-Z]", text):
            score -= 25

        return score

    def score_image_metadata(self, metadata):
        civitai_section = self.get_civitai_section(metadata)
        images = civitai_section.get("images", []) if civitai_section else []
        valid_images = [image for image in images if image.get("meta")]
        if not valid_images:
            return -1

        prompts = 0
        for image in valid_images:
            prompt = self.string_or_empty(image.get("meta", {}).get("prompt", ""))
            if prompt:
                prompts += 1
        return prompts

    def get_civitai_section(self, metadata):
        if not isinstance(metadata, dict):
            return {}

        civitai_section = metadata.get("civitai")
        if isinstance(civitai_section, dict):
            return civitai_section

        return metadata

    def extract_trained_words(self, metadata):
        if not metadata:
            return []

        civitai_section = self.get_civitai_section(metadata)
        trained_words = civitai_section.get("trainedWords", []) if civitai_section else []
        if not trained_words:
            return []

        output = []
        for item in trained_words:
            cleaned = self.string_or_empty(item)
            if cleaned:
                output.append(cleaned)
        return self.dedupe_preserve_order(output)

    def extract_usable_trained_words(self, metadata):
        return [
            word for word in self.extract_trained_words(metadata) if word != self.STYLE_PLACEHOLDER
        ]

    def has_explicit_trained_words(self, metadata):
        civitai_section = self.get_civitai_section(metadata)
        if not isinstance(civitai_section, dict):
            return False

        raw_metadata = metadata.get("_embedded_raw_metadata") if isinstance(metadata, dict) else None
        if isinstance(raw_metadata, dict):
            for key in ("trained_words", "ss_trained_words"):
                if self.parse_trigger_word_value(raw_metadata.get(key)):
                    return True
            for key in (
                "modelspec.trigger_phrase",
                "modelspec.trigger_word",
                "modelspec.usage_hint",
            ):
                if self.string_or_empty(raw_metadata.get(key)):
                    return True
            return False

        return "trainedWords" in civitai_section

    def extract_metadata_tags(self, metadata):
        civitai_section = self.get_civitai_section(metadata)
        candidates = [
            civitai_section.get("tags") if isinstance(civitai_section, dict) else None,
            ((civitai_section.get("model") or {}).get("tags"))
            if isinstance(civitai_section, dict)
            else None,
            metadata.get("tags") if isinstance(metadata, dict) else None,
            ((metadata.get("model") or {}).get("tags")) if isinstance(metadata, dict) else None,
        ]

        tags = []
        for candidate in candidates:
            if isinstance(candidate, str):
                candidate = [candidate]
            if not isinstance(candidate, (list, tuple, set)):
                continue
            for item in candidate:
                normalized = self.normalize_token(item)
                if normalized:
                    tags.append(normalized)
        return self.dedupe_preserve_order(tags)

    def extract_metadata_names(self, metadata, lora_path):
        civitai_section = self.get_civitai_section(metadata)
        candidates = [
            ((civitai_section.get("model") or {}).get("name"))
            if isinstance(civitai_section, dict)
            else None,
            civitai_section.get("name") if isinstance(civitai_section, dict) else None,
            metadata.get("model_name") if isinstance(metadata, dict) else None,
            metadata.get("name") if isinstance(metadata, dict) else None,
            ((metadata.get("model") or {}).get("name")) if isinstance(metadata, dict) else None,
            Path(lora_path).stem if lora_path else None,
        ]

        normalized_names = []
        for candidate in candidates:
            normalized = self.normalize_token(candidate)
            if normalized:
                normalized_names.append(normalized)
        return self.dedupe_preserve_order(normalized_names)

    def indicates_trigger_words_optional(self, metadata, lora_path):
        if not metadata:
            return False

        trained_words = self.extract_trained_words(metadata)
        explicit_trained_words = self.has_explicit_trained_words(metadata)
        if self.STYLE_PLACEHOLDER in trained_words:
            return True
        if trained_words:
            if explicit_trained_words:
                return False
            return self.inferred_trained_words_are_name_derived(metadata, lora_path)

        tags = set(self.extract_metadata_tags(metadata))
        if tags & self.TRIGGER_WORD_OPTIONAL_TAGS:
            return True

        optional_name_hints = self.extract_optional_name_hints(metadata, lora_path)
        if not optional_name_hints:
            return False
        if not trained_words:
            return True
        return self.inferred_trained_words_are_name_derived(metadata, lora_path)

    def describe_trigger_words_optional(self, metadata, lora_path):
        trained_words = self.extract_trained_words(metadata)
        if self.STYLE_PLACEHOLDER in trained_words:
            return (
                "ss_tag_frequency がスタイル系 LoRA を示しているため、"
                "明示トリガーワード不要モデルと判定しました。"
            )

        if trained_words and self.inferred_trained_words_are_name_derived(metadata, lora_path):
            optional_name_hints = self.extract_optional_name_hints(metadata, lora_path)
            if optional_name_hints:
                matched = ", ".join(sorted(optional_name_hints))
                return (
                    "埋め込み metadata 由来の候補がモデル名由来のみで、モデル名またはファイル名に "
                    f"{matched} が含まれるため、明示トリガーワード不要モデルと判定しました。"
                )
            return "埋め込み metadata 由来の候補がモデル名またはファイル名由来のみのため、明示トリガーワード不要モデルと判定しました。"

        tags = set(self.extract_metadata_tags(metadata))
        if tags & self.TRIGGER_WORD_OPTIONAL_TAGS:
            matched = ", ".join(sorted(tags & self.TRIGGER_WORD_OPTIONAL_TAGS))
            return (
                "trainedWords が空で、tags に "
                f"{matched} が含まれるため、明示トリガーワード不要モデルと判定しました。"
            )

        optional_name_hints = self.extract_optional_name_hints(metadata, lora_path)
        if optional_name_hints:
            matched = ", ".join(sorted(optional_name_hints))
            return (
                "埋め込み metadata 由来の候補がモデル名由来のみで、モデル名またはファイル名に "
                f"{matched} が含まれるため、明示トリガーワード不要モデルと判定しました。"
            )

        return "明示トリガーワード不要モデルと判定しました。"

    def extract_optional_name_hints(self, metadata, lora_path):
        matched = set()
        for name in self.extract_metadata_names(metadata, lora_path):
            for hint in self.TRIGGER_WORD_OPTIONAL_NAME_HINTS:
                if hint in name:
                    matched.add(hint)
        return matched

    def inferred_trained_words_are_name_derived(self, metadata, lora_path):
        if self.has_explicit_trained_words(metadata):
            return False

        names = self.extract_metadata_names(metadata, lora_path)
        if not names:
            return False

        trained_words = self.extract_usable_trained_words(metadata)
        if not trained_words:
            return False

        for candidate in trained_words:
            normalized_candidate = self.normalize_token(candidate)
            if not normalized_candidate:
                return False
            if not any(
                normalized_candidate == name or normalized_candidate in name
                for name in names
            ):
                return False
        return True

    def remove_lora_syntax(self, text):
        return re.sub(r"<lora:[^>]+>", "", text)

    def cleanup_prompt_text(self, text):
        text = re.sub(r"\s*,\s*,+\s*", ", ", text)
        text = re.sub(r"^\s*,\s*|\s*,\s*$", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def string_or_empty(self, value):
        if value is None:
            return ""
        return str(value).strip()

    def coerce_int(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def dedupe_preserve_order(self, values):
        output = []
        seen = set()
        for value in values:
            key = value.lower()
            if key not in seen:
                output.append(value)
                seen.add(key)
        return output
