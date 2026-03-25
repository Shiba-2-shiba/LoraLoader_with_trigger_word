"""ComfyUI node definition for loading a LoRA and previewing trigger words."""

import folder_paths
from comfy_api.latest import io

from .constants import (
    DEFAULT_TRIGGER_WORD_SOURCE,
    ENABLE_REMOTE_METADATA_FALLBACK,
    NODE_CATEGORY,
    NODE_DISPLAY_NAME,
    NODE_ID,
)
from .services import lora_model_loader, trigger_word_resolver


class LoraLoaderModelOnlyTriggerWordsNode(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id=NODE_ID,
            display_name=NODE_DISPLAY_NAME,
            category=NODE_CATEGORY,
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
                io.String.Input(
                    "loaded_trigger_words",
                    multiline=True,
                    default="",
                    tooltip="Trigger Words / Browse タブの表示欄。実行時の出力値そのものではありません。",
                ),
            ],
            outputs=[
                io.Model.Output(
                    "model",
                    display_name="MODEL",
                    tooltip="LoRA 適用後の MODEL。",
                ),
                io.String.Output(
                    "trigger_words",
                    display_name="TRIGGER_WORDS",
                    tooltip="選択した取得モードで解決された文字列。失敗時は空文字を返します。",
                ),
            ],
            not_idempotent=True,
        )

    @classmethod
    def execute(
        cls,
        model,
        lora_name,
        strength_model,
        loaded_trigger_words,
    ):
        model_lora = lora_model_loader.load_model_only(model, lora_name, strength_model)
        trigger_words = trigger_word_resolver.resolve_output(
            lora_name=lora_name,
            trigger_word_source=DEFAULT_TRIGGER_WORD_SOURCE,
            enable_civitai_fallback=ENABLE_REMOTE_METADATA_FALLBACK,
        )
        del loaded_trigger_words
        return io.NodeOutput(model_lora, trigger_words)
