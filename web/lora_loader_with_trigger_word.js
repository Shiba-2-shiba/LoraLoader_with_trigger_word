import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const PREVIEW_ROUTE = "/lora_loader_with_trigger_word/preview";
const BROWSE_ROUTE = "/lora_loader_with_trigger_word/browse";

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

            const state = (this.__lltwtState ??= {
                activeTab: "trigger_words",
                lastTriggerWords: previewWidget.value ?? "",
                lastBrowseText: "[Browse] Load Model Card を押してください。",
                modelCardUrl: "",
            });

            const setPanelValue = (value) => {
                previewWidget.value = value ?? "";
                if (previewWidget.callback) {
                    previewWidget.callback(previewWidget.value);
                }
                this.setDirtyCanvas(true, true);
            };

            const renderActivePanel = () => {
                if (state.activeTab === "browse") {
                    setPanelValue(state.lastBrowseText || "[Browse] Load Model Card を押してください。");
                    return;
                }

                setPanelValue(
                    state.lastTriggerWords || "[LoRA Trigger Words] Load Trigger Words を押してください。"
                );
            };

            const setActiveTab = (tabName) => {
                state.activeTab = tabName;
                if (triggerTabButton) {
                    triggerTabButton.name =
                        tabName === "trigger_words" ? "[Trigger Words]" : "Trigger Words";
                }
                if (browseTabButton) {
                    browseTabButton.name = tabName === "browse" ? "[Browse]" : "Browse";
                }
                this.setDirtyCanvas(true, true);
                renderActivePanel();
            };

            const getRequestPayload = () => ({
                lora_name: loraWidget.value,
                trigger_word_source: sourceWidget.value,
                enable_civitai_fallback: Boolean(fallbackWidget.value),
            });

            const ensureLoraSelected = (tabName) => {
                if (loraWidget.value) {
                    return true;
                }

                if (tabName === "browse") {
                    state.lastBrowseText = "[Browse] LoRA が選択されていません。";
                } else {
                    state.lastTriggerWords = "[LoRA Trigger Words] LoRA が選択されていません。";
                }
                setActiveTab(tabName);
                return false;
            };

            const loadTriggerWords = async () => {
                if (!ensureLoraSelected("trigger_words")) {
                    return;
                }

                state.lastTriggerWords = "読み込み中...";
                setActiveTab("trigger_words");

                try {
                    const response = await api.fetchApi(PREVIEW_ROUTE, {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                        },
                        body: JSON.stringify(getRequestPayload()),
                    });
                    const data = await response.json();
                    state.lastTriggerWords =
                        data.trigger_words || "[LoRA Trigger Words] 応答が空です。";
                } catch (error) {
                    state.lastTriggerWords = `[LoRA Trigger Words] preview 取得エラー: ${error}`;
                }

                setActiveTab("trigger_words");
            };

            const loadModelCard = async () => {
                if (!ensureLoraSelected("browse")) {
                    return;
                }

                state.lastBrowseText = "[Browse] 読み込み中...";
                setActiveTab("browse");

                try {
                    const response = await api.fetchApi(BROWSE_ROUTE, {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                        },
                        body: JSON.stringify(getRequestPayload()),
                    });
                    const data = await response.json();
                    state.modelCardUrl = data.civitai_url || "";
                    state.lastBrowseText =
                        data.display_text || "[Browse] model card 情報が空です。";
                } catch (error) {
                    state.modelCardUrl = "";
                    state.lastBrowseText = `[Browse] model card 取得エラー: ${error}`;
                }

                setActiveTab("browse");
            };

            const openModelCard = () => {
                if (!state.modelCardUrl) {
                    state.lastBrowseText =
                        state.lastBrowseText || "[Browse] 開ける model card URL がありません。";
                    setActiveTab("browse");
                    return;
                }

                window.open(state.modelCardUrl, "_blank");
            };

            const triggerTabButton = this.addWidget(
                "button",
                "[Trigger Words]",
                "",
                () => setActiveTab("trigger_words"),
                { serialize: false }
            );

            const browseTabButton = this.addWidget(
                "button",
                "Browse",
                "",
                () => setActiveTab("browse"),
                { serialize: false }
            );

            this.addWidget(
                "button",
                "Load Trigger Words",
                "",
                loadTriggerWords,
                { serialize: false }
            );

            this.addWidget(
                "button",
                "Load Model Card",
                "",
                loadModelCard,
                { serialize: false }
            );

            this.addWidget(
                "button",
                "Open Model Card",
                "",
                openModelCard,
                { serialize: false }
            );

            renderActivePanel();
            this.computeSize();
            this.setDirtyCanvas(true, true);
            return result;
        };
    },
});
