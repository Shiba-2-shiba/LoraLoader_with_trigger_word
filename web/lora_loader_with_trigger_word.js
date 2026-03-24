import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "LoraLoaderWithTriggerWord.UI",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "LoraLoaderModelOnlyTriggerWords") {
            return;
        }

        const onNodeCreated = nodeType.prototype.onNodeCreated;

        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;

            const loraWidget = this.widgets?.find((widget) => widget.name === "lora_name");
            const sourceWidget = this.widgets?.find((widget) => widget.name === "trigger_word_source");
            const fallbackWidget = this.widgets?.find((widget) => widget.name === "enable_civitai_fallback");
            const previewWidget = this.widgets?.find((widget) => widget.name === "loaded_trigger_words");

            if (!loraWidget || !sourceWidget || !fallbackWidget || !previewWidget) {
                return result;
            }

            const setPreviewValue = (value) => {
                previewWidget.value = value ?? "";
                if (previewWidget.callback) {
                    previewWidget.callback(previewWidget.value);
                }
                this.setDirtyCanvas(true, true);
            };

            this.addWidget(
                "button",
                "Load Trigger Words",
                "",
                async () => {
                    const loraName = loraWidget.value;
                    if (!loraName) {
                        setPreviewValue("[LoRA Trigger Words] LoRA が選択されていません。");
                        return;
                    }

                    setPreviewValue("読み込み中...");

                    try {
                        const response = await api.fetchApi("/lora_loader_with_trigger_word/preview", {
                            method: "POST",
                            headers: {
                                "Content-Type": "application/json",
                            },
                            body: JSON.stringify({
                                lora_name: loraName,
                                trigger_word_source: sourceWidget.value,
                                enable_civitai_fallback: Boolean(fallbackWidget.value),
                            }),
                        });

                        const data = await response.json();
                        setPreviewValue(data.trigger_words || "[LoRA Trigger Words] 応答が空です。");
                    } catch (error) {
                        setPreviewValue(`[LoRA Trigger Words] preview 取得エラー: ${error}`);
                    }
                },
                { serialize: false }
            );

            this.computeSize();
            this.setDirtyCanvas(true, true);
            return result;
        };
    },
});
