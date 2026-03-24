"""ComfyUI node definition for loading a LoRA and previewing trigger words."""

import folder_paths
from comfy_api.latest import io

from .constants import (
    NODE_CATEGORY,
    NODE_DISPLAY_NAME,
    NODE_ID,
    TRIGGER_WORD_SOURCES,
)
from .services import lora_model_loader


class LoraLoaderModelOnlyTriggerWordsNode(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id=NODE_ID,
            display_name=NODE_DISPLAY_NAME,
            category=NODE_CATEGORY,
            description=(
                "LoRA を MODEL に適用し、sidecar JSON、埋め込み safetensors metadata、"
                "必要に応じて Civitai by-hash fallback からトリガーワード文字列を返します。"
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
                io.Combo.Input(
                    "trigger_word_source",
                    options=list(TRIGGER_WORD_SOURCES),
                    default="json_combined",
                    tooltip="トリガーワードの取得モード。",
                ),
                io.Boolean.Input(
                    "enable_civitai_fallback",
                    default=True,
                    advanced=True,
                    tooltip="ローカル metadata で不足した場合に SHA256 から Civitai by-hash API を参照します。",
                ),
                io.String.Input(
                    "loaded_trigger_words",
                    multiline=True,
                    default="",
                    tooltip="Load Trigger Words ボタンで取得した内容の表示欄。実行時の MODEL 適用には影響しません。",
                ),
            ],
            outputs=[
                io.Model.Output(
                    display_name="MODEL",
                    tooltip="LoRA 適用後の MODEL。",
                ),
            ],
        )

    @classmethod
    def execute(
        cls,
        model,
        lora_name,
        strength_model,
        trigger_word_source,
        enable_civitai_fallback,
        loaded_trigger_words,
    ):
        del trigger_word_source, enable_civitai_fallback, loaded_trigger_words
        model_lora = lora_model_loader.load_model_only(model, lora_name, strength_model)
        return io.NodeOutput(model_lora)
