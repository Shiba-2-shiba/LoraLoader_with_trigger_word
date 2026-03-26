"""ComfyUI node definitions for loading a LoRA and previewing trigger words."""

import folder_paths
from comfy_api.latest import io

from .constants import (
    DEFAULT_TRIGGER_WORD_SOURCE,
    ENABLE_REMOTE_METADATA_FALLBACK,
    MODEL_AND_CLIP_NODE_DISPLAY_NAME,
    MODEL_AND_CLIP_NODE_ID,
    MODEL_ONLY_NODE_DISPLAY_NAME,
    MODEL_ONLY_NODE_ID,
    NODE_CATEGORY,
)
from .services import lora_model_loader, trigger_word_resolver


def _resolve_trigger_words(lora_name):
    return trigger_word_resolver.resolve_output(
        lora_name=lora_name,
        trigger_word_source=DEFAULT_TRIGGER_WORD_SOURCE,
        enable_civitai_fallback=ENABLE_REMOTE_METADATA_FALLBACK,
    )


def _common_schema_kwargs(node_id, display_name, description, search_aliases, inputs, outputs):
    return dict(
        node_id=node_id,
        display_name=display_name,
        category=NODE_CATEGORY,
        description=description,
        search_aliases=search_aliases,
        inputs=inputs,
        outputs=outputs,
        not_idempotent=True,
    )


def _trigger_words_input():
    return io.String.Input(
        "loaded_trigger_words",
        multiline=True,
        default="",
        tooltip="Trigger Words / Browse タブの表示欄。実行時の出力値そのものではありません。",
    )


def _trigger_words_output():
    return io.String.Output(
        "trigger_words",
        display_name="TRIGGER_WORDS",
        tooltip="選択した取得モードで解決された文字列。失敗時は空文字を返します。",
    )


class LoraLoaderModelOnlyTriggerWordsNode(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            **_common_schema_kwargs(
                node_id=MODEL_ONLY_NODE_ID,
                display_name=MODEL_ONLY_NODE_DISPLAY_NAME,
                description=(
                    "LoRA を MODEL に適用し、自動判定した trigger words 文字列を"
                    " downstream に流します。"
                ),
                search_aliases=[
                    "lora trigger words",
                    "load lora model only",
                    "civitai trained words",
                    "auto trigger words",
                    "lora metadata",
                ],
                inputs=[
                    io.Model.Input(
                        "model",
                        tooltip="LoRA を適用する MODEL。",
                    ),
                    io.Combo.Input(
                        "lora_name",
                        options=sorted(folder_paths.get_filename_list("loras"), key=str.lower),
                        tooltip="適用する LoRA 名。",
                    ),
                    io.Float.Input(
                        "strength_model",
                        default=1.0,
                        min=-100.0,
                        max=100.0,
                        tooltip="MODEL に適用する LoRA 強度。負の値も指定可能です。",
                    ),
                    _trigger_words_input(),
                ],
                outputs=[
                    io.Model.Output(
                        "model",
                        display_name="MODEL",
                        tooltip="LoRA 適用後の MODEL。",
                    ),
                    _trigger_words_output(),
                ],
            )
        )

    @classmethod
    def execute(cls, model, lora_name, strength_model, loaded_trigger_words):
        model_lora = lora_model_loader.load_model_only(model, lora_name, strength_model)
        trigger_words = _resolve_trigger_words(lora_name)
        del loaded_trigger_words
        return io.NodeOutput(model_lora, trigger_words)


class LoraLoaderTriggerWordsNode(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            **_common_schema_kwargs(
                node_id=MODEL_AND_CLIP_NODE_ID,
                display_name=MODEL_AND_CLIP_NODE_DISPLAY_NAME,
                description=(
                    "LoRA を MODEL と CLIP に適用し、自動判定した trigger words "
                    "文字列を downstream に流します。"
                ),
                search_aliases=[
                    "lora trigger words",
                    "load lora",
                    "load lora clip",
                    "civitai trained words",
                    "auto trigger words",
                    "lora metadata",
                ],
                inputs=[
                    io.Model.Input(
                        "model",
                        tooltip="LoRA を適用する MODEL。",
                    ),
                    io.Clip.Input(
                        "clip",
                        tooltip="LoRA を適用する CLIP。",
                    ),
                    io.Combo.Input(
                        "lora_name",
                        options=sorted(folder_paths.get_filename_list("loras"), key=str.lower),
                        tooltip="適用する LoRA 名。",
                    ),
                    io.Float.Input(
                        "strength_model",
                        default=1.0,
                        min=-100.0,
                        max=100.0,
                        tooltip="MODEL に適用する LoRA 強度。負の値も指定可能です。",
                    ),
                    io.Float.Input(
                        "strength_clip",
                        default=1.0,
                        min=-100.0,
                        max=100.0,
                        tooltip="CLIP に適用する LoRA 強度。負の値も指定可能です。",
                    ),
                    _trigger_words_input(),
                ],
                outputs=[
                    io.Model.Output(
                        "model",
                        display_name="MODEL",
                        tooltip="LoRA 適用後の MODEL。",
                    ),
                    io.Clip.Output(
                        "clip",
                        display_name="CLIP",
                        tooltip="LoRA 適用後の CLIP。",
                    ),
                    _trigger_words_output(),
                ],
            )
        )

    @classmethod
    def execute(
        cls,
        model,
        clip,
        lora_name,
        strength_model,
        strength_clip,
        loaded_trigger_words,
    ):
        model_lora, clip_lora = lora_model_loader.load(
            model,
            clip,
            lora_name,
            strength_model,
            strength_clip,
        )
        trigger_words = _resolve_trigger_words(lora_name)
        del loaded_trigger_words
        return io.NodeOutput(model_lora, clip_lora, trigger_words)
