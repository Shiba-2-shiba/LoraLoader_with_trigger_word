"""LoRA loading utilities used by the custom node."""

import comfy.sd
import comfy.utils
import folder_paths


class CachedLoraModelLoader:
    """Caches the last loaded LoRA payload to avoid repeated disk reads."""

    def __init__(self):
        self._loaded_lora = None

    def load_model_only(self, model, lora_name, strength_model):
        return self.load(model, None, lora_name, strength_model, 0)[0]

    def load(self, model, clip, lora_name, strength_model, strength_clip):
        if strength_model == 0 and strength_clip == 0:
            return model, clip

        lora_path = folder_paths.get_full_path_or_raise("loras", lora_name)
        lora = None

        if self._loaded_lora is not None:
            if self._loaded_lora[0] == lora_path:
                lora = self._loaded_lora[1]
            else:
                self._loaded_lora = None

        if lora is None:
            lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
            self._loaded_lora = (lora_path, lora)

        return comfy.sd.load_lora_for_models(
            model,
            clip,
            lora,
            strength_model,
            strength_clip,
        )
