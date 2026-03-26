"""
ComfyUI custom node package entrypoint.
"""

WEB_DIRECTORY = "./web"

try:
    from typing_extensions import override
    from comfy_api.latest import ComfyExtension

    from .lora_loader_trigger_words import LoraLoaderTriggerWordsNode
    from .lora_loader_model_only_trigger_words import LoraLoaderModelOnlyTriggerWordsNode
except ImportError:
    ComfyExtension = None
    LoraLoaderTriggerWordsNode = None
    LoraLoaderModelOnlyTriggerWordsNode = None

    async def comfy_entrypoint():
        raise RuntimeError("ComfyUI runtime dependencies are not available")

else:
    class LoraLoaderWithTriggerWordExtension(ComfyExtension):
        @override
        async def get_node_list(self) -> list[type]:
            return [
                LoraLoaderTriggerWordsNode,
                LoraLoaderModelOnlyTriggerWordsNode,
            ]


    async def comfy_entrypoint() -> LoraLoaderWithTriggerWordExtension:
        return LoraLoaderWithTriggerWordExtension()


__all__ = ["comfy_entrypoint", "WEB_DIRECTORY"]
