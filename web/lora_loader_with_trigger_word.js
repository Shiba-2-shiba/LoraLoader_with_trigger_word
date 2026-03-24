import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const PREVIEW_ROUTE = "/lora_loader_with_trigger_word/preview";
const BROWSE_ROUTE = "/lora_loader_with_trigger_word/browse";
const VIEWER_ID = "lltwt-model-card-viewer";
const VIEWER_STYLE_ID = "lltwt-model-card-viewer-style";

function injectViewerCss() {
    if (document.getElementById(VIEWER_STYLE_ID)) {
        return;
    }

    const style = document.createElement("style");
    style.id = VIEWER_STYLE_ID;
    style.textContent = `
#${VIEWER_ID} {
    position: fixed;
    inset: 0;
    z-index: 100100;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: "Segoe UI", sans-serif;
}

#${VIEWER_ID}.hidden {
    display: none;
}

#${VIEWER_ID} .lltwt-backdrop {
    position: absolute;
    inset: 0;
    background: rgba(7, 9, 14, 0.82);
    backdrop-filter: blur(10px);
}

#${VIEWER_ID} .lltwt-window {
    position: relative;
    z-index: 1;
    width: min(1100px, 94vw);
    height: min(900px, 92vh);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    border-radius: 18px;
    border: 1px solid #263143;
    background:
        radial-gradient(circle at top right, rgba(75, 102, 158, 0.18), transparent 28%),
        linear-gradient(180deg, #0f1623 0%, #0a0f17 100%);
    box-shadow: 0 40px 120px rgba(0, 0, 0, 0.52);
    color: #edf2ff;
}

#${VIEWER_ID} .lltwt-header {
    display: flex;
    align-items: flex-start;
    gap: 16px;
    padding: 18px 22px 16px;
    border-bottom: 1px solid #1c2534;
}

#${VIEWER_ID} .lltwt-header-copy {
    display: flex;
    flex-direction: column;
    gap: 5px;
    min-width: 0;
}

#${VIEWER_ID} .lltwt-eyebrow {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #8fa6da;
}

#${VIEWER_ID} .lltwt-title {
    margin: 0;
    font-size: 23px;
    line-height: 1.2;
    color: #f6f8ff;
}

#${VIEWER_ID} .lltwt-subtitle {
    margin: 0;
    font-size: 12px;
    color: #9daacc;
}

#${VIEWER_ID} .lltwt-header-actions {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 8px;
}

#${VIEWER_ID} .lltwt-btn,
#${VIEWER_ID} .lltwt-close {
    min-height: 34px;
    padding: 0 12px;
    border-radius: 10px;
    border: 1px solid #314360;
    background: #151d2c;
    color: #d9e5ff;
    cursor: pointer;
    font-size: 11px;
    font-weight: 600;
}

#${VIEWER_ID} .lltwt-btn:hover,
#${VIEWER_ID} .lltwt-close:hover {
    background: #1d2940;
    border-color: #496493;
    color: #ffffff;
}

#${VIEWER_ID} .lltwt-close {
    min-width: 40px;
    padding: 0;
    font-size: 16px;
}

#${VIEWER_ID} .lltwt-body {
    flex: 1;
    overflow: auto;
    padding: 18px 22px 22px;
    display: grid;
    gap: 16px;
    grid-template-columns: minmax(300px, 380px) minmax(0, 1fr);
}

#${VIEWER_ID} .lltwt-panel {
    border: 1px solid #202b3d;
    border-radius: 16px;
    background: rgba(10, 15, 24, 0.92);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

#${VIEWER_ID} .lltwt-sidebar {
    display: flex;
    flex-direction: column;
    gap: 16px;
}

#${VIEWER_ID} .lltwt-section {
    padding: 16px;
}

#${VIEWER_ID} .lltwt-section h3 {
    margin: 0 0 12px;
    font-size: 12px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #9bb1e2;
}

#${VIEWER_ID} .lltwt-metrics {
    display: grid;
    gap: 10px;
}

#${VIEWER_ID} .lltwt-metric {
    padding: 10px 12px;
    border-radius: 12px;
    border: 1px solid #233149;
    background: #121927;
}

#${VIEWER_ID} .lltwt-metric-label {
    display: block;
    margin-bottom: 4px;
    font-size: 10px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #7f93bf;
}

#${VIEWER_ID} .lltwt-metric-value {
    display: block;
    font-size: 12px;
    line-height: 1.45;
    color: #edf2ff;
    word-break: break-word;
}

#${VIEWER_ID} .lltwt-description {
    white-space: pre-wrap;
    font-size: 12px;
    line-height: 1.7;
    color: #d0daf0;
}

#${VIEWER_ID} .lltwt-chip-list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}

#${VIEWER_ID} .lltwt-chip {
    padding: 6px 10px;
    border-radius: 999px;
    border: 1px solid #314360;
    background: #111a28;
    color: #dce6ff;
    font-size: 11px;
    line-height: 1.3;
}

#${VIEWER_ID} .lltwt-empty {
    font-size: 12px;
    line-height: 1.6;
    color: #8596ba;
}

#${VIEWER_ID} .lltwt-gallery {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
    gap: 12px;
}

#${VIEWER_ID} .lltwt-card {
    overflow: hidden;
    border-radius: 14px;
    border: 1px solid #223047;
    background: #0f1623;
}

#${VIEWER_ID} .lltwt-card img {
    width: 100%;
    aspect-ratio: 1;
    object-fit: cover;
    display: block;
    background: #090d14;
}

#${VIEWER_ID} .lltwt-card-copy {
    padding: 10px 11px 12px;
    display: grid;
    gap: 7px;
}

#${VIEWER_ID} .lltwt-card-meta {
    font-size: 10px;
    color: #89a0d0;
}

#${VIEWER_ID} .lltwt-card-prompt {
    font-size: 11px;
    line-height: 1.5;
    color: #dce5fb;
    display: -webkit-box;
    -webkit-line-clamp: 4;
    -webkit-box-orient: vertical;
    overflow: hidden;
}

body.lltwt-modal-open {
    overflow: hidden;
}

@media (max-width: 900px) {
    #${VIEWER_ID} .lltwt-window {
        width: 96vw;
        height: 94vh;
    }

    #${VIEWER_ID} .lltwt-header {
        flex-direction: column;
    }

    #${VIEWER_ID} .lltwt-header-actions {
        margin-left: 0;
        width: 100%;
        justify-content: flex-end;
    }

    #${VIEWER_ID} .lltwt-body {
        grid-template-columns: 1fr;
    }
}
`;
    document.head.appendChild(style);
}

function ensureViewer() {
    injectViewerCss();

    let root = document.getElementById(VIEWER_ID);
    if (!root) {
        root = document.createElement("div");
        root.id = VIEWER_ID;
        root.className = "hidden";
        root.innerHTML = `
            <div class="lltwt-backdrop"></div>
            <div class="lltwt-window">
                <div class="lltwt-header">
                    <div class="lltwt-header-copy">
                        <span class="lltwt-eyebrow">LoRA Model Card Viewer</span>
                        <h2 class="lltwt-title">Model Card</h2>
                        <p class="lltwt-subtitle">ComfyUI 内で Civitai metadata を閲覧します。</p>
                    </div>
                    <div class="lltwt-header-actions">
                        <button class="lltwt-btn" data-action="copy-url" type="button">Copy URL</button>
                        <button class="lltwt-close" data-action="close" type="button" aria-label="Close">x</button>
                    </div>
                </div>
                <div class="lltwt-body">
                    <div class="lltwt-sidebar">
                        <section class="lltwt-panel lltwt-section">
                            <h3>Overview</h3>
                            <div class="lltwt-metrics" data-slot="metrics"></div>
                        </section>
                        <section class="lltwt-panel lltwt-section">
                            <h3>Trigger Words</h3>
                            <div class="lltwt-chip-list" data-slot="trained-words"></div>
                            <div class="lltwt-empty hidden" data-slot="trained-words-empty">trainedWords は見つかりませんでした。</div>
                        </section>
                    </div>
                    <div class="lltwt-main">
                        <section class="lltwt-panel lltwt-section">
                            <h3>Description</h3>
                            <div class="lltwt-description" data-slot="description"></div>
                            <div class="lltwt-empty hidden" data-slot="description-empty">説明文はありません。</div>
                        </section>
                        <section class="lltwt-panel lltwt-section">
                            <h3>Preview Images</h3>
                            <div class="lltwt-gallery" data-slot="images"></div>
                            <div class="lltwt-empty hidden" data-slot="images-empty">プレビュー画像はありません。</div>
                        </section>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(root);
    }

    if (!root.__lltwtBound) {
        const close = () => closeViewer();
        root.querySelector(".lltwt-backdrop")?.addEventListener("click", close);
        root.querySelector('[data-action="close"]')?.addEventListener("click", close);
        root.querySelector('[data-action="copy-url"]')?.addEventListener("click", async () => {
            const url = root.__lltwtCurrentCard?.civitai_url || "";
            if (!url || !navigator.clipboard?.writeText) {
                return;
            }
            try {
                await navigator.clipboard.writeText(url);
            } catch {
                // Ignore clipboard failures in embedded browsers.
            }
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && !root.classList.contains("hidden")) {
                closeViewer();
            }
        });
        root.__lltwtBound = true;
    }

    return root;
}

function closeViewer() {
    const root = document.getElementById(VIEWER_ID);
    if (!root) {
        return;
    }
    root.classList.add("hidden");
    document.body.classList.remove("lltwt-modal-open");
}

function setSectionEmptyState(container, emptyNode, isEmpty) {
    if (container) {
        container.classList.toggle("hidden", isEmpty);
    }
    if (emptyNode) {
        emptyNode.classList.toggle("hidden", !isEmpty);
    }
}

function createMetric(label, value) {
    const item = document.createElement("div");
    item.className = "lltwt-metric";
    const labelEl = document.createElement("span");
    labelEl.className = "lltwt-metric-label";
    labelEl.textContent = label;
    const valueEl = document.createElement("span");
    valueEl.className = "lltwt-metric-value";
    valueEl.textContent = value || "-";
    item.append(labelEl, valueEl);
    return item;
}

function openViewer(cardData) {
    if (!cardData) {
        return;
    }

    const root = ensureViewer();
    root.__lltwtCurrentCard = cardData;

    const title = root.querySelector(".lltwt-title");
    const subtitle = root.querySelector(".lltwt-subtitle");
    const metrics = root.querySelector('[data-slot="metrics"]');
    const trainedWords = root.querySelector('[data-slot="trained-words"]');
    const trainedWordsEmpty = root.querySelector('[data-slot="trained-words-empty"]');
    const description = root.querySelector('[data-slot="description"]');
    const descriptionEmpty = root.querySelector('[data-slot="description-empty"]');
    const images = root.querySelector('[data-slot="images"]');
    const imagesEmpty = root.querySelector('[data-slot="images-empty"]');

    if (title) {
        title.textContent = cardData.model_name || "Unknown model";
    }
    if (subtitle) {
        subtitle.textContent = [
            cardData.version_name || "Version name unavailable",
            cardData.source_label ? `Source: ${cardData.source_label}` : null,
        ].filter(Boolean).join(" | ");
    }

    if (metrics) {
        metrics.replaceChildren(
            createMetric("Model ID", cardData.model_id),
            createMetric("Version ID", cardData.version_id),
            createMetric("Model Type", cardData.model_type),
            createMetric("Base Model", cardData.base_model),
            createMetric(
                "Stats",
                [
                    Number.isInteger(cardData.download_count) ? `Downloads ${cardData.download_count}` : null,
                    Number.isInteger(cardData.thumbs_up_count) ? `Likes ${cardData.thumbs_up_count}` : null,
                ].filter(Boolean).join(" | ")
            ),
            createMetric("URL", cardData.civitai_url)
        );
    }

    if (trainedWords) {
        trainedWords.replaceChildren();
        const wordList = Array.isArray(cardData.trained_words) ? cardData.trained_words : [];
        for (const word of wordList) {
            const chip = document.createElement("span");
            chip.className = "lltwt-chip";
            chip.textContent = word;
            trainedWords.appendChild(chip);
        }
        setSectionEmptyState(trainedWords, trainedWordsEmpty, wordList.length === 0);
    }

    if (description) {
        const descriptionText = String(cardData.description || "").trim();
        description.textContent = descriptionText;
        setSectionEmptyState(description, descriptionEmpty, !descriptionText);
    }

    if (images) {
        images.replaceChildren();
        const imageList = Array.isArray(cardData.images) ? cardData.images : [];
        for (const image of imageList) {
            const card = document.createElement("article");
            card.className = "lltwt-card";

            const img = document.createElement("img");
            img.loading = "lazy";
            img.src = image.url;
            img.alt = cardData.model_name || "LoRA preview";

            const copy = document.createElement("div");
            copy.className = "lltwt-card-copy";

            const meta = document.createElement("div");
            meta.className = "lltwt-card-meta";
            meta.textContent = [image.width, image.height].every(Number.isFinite)
                ? `${image.width} x ${image.height}`
                : "Preview image";

            copy.appendChild(meta);
            if (image.prompt) {
                const prompt = document.createElement("div");
                prompt.className = "lltwt-card-prompt";
                prompt.textContent = image.prompt;
                copy.appendChild(prompt);
            }

            card.append(img, copy);
            images.appendChild(card);
        }
        setSectionEmptyState(images, imagesEmpty, imageList.length === 0);
    }

    root.classList.remove("hidden");
    document.body.classList.add("lltwt-modal-open");
}

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
                lastPanelText:
                    previewWidget.value ??
                    "[LoRA Trigger Words] Load Trigger Words を押して内容を確認してください。",
                modelCardUrl: "",
                modelCardData: null,
            });

            let browseModelCardButton;

            const setPanelValue = (value) => {
                previewWidget.value = value ?? "";
                if (previewWidget.callback) {
                    previewWidget.callback(previewWidget.value);
                }
                this.setDirtyCanvas(true, true);
            };

            const syncButtonLabels = () => {
                if (browseModelCardButton) {
                    browseModelCardButton.name = state.modelCardData
                        ? "Browse Model Card"
                        : "Browse Model Card (Load First)";
                }
            };

            const renderPanel = (text) => {
                state.lastPanelText = text || state.lastPanelText;
                syncButtonLabels();
                setPanelValue(
                    state.lastPanelText ||
                        "[LoRA Trigger Words] Load Trigger Words を押して内容を確認してください。"
                );
            };

            const getRequestPayload = () => ({
                lora_name: loraWidget.value,
                trigger_word_source: sourceWidget.value,
                enable_civitai_fallback: Boolean(fallbackWidget.value),
            });

            const ensureLoraSelected = (prefix) => {
                if (loraWidget.value) {
                    return true;
                }

                renderPanel(`${prefix} LoRA が選択されていません。`);
                return false;
            };

            const readJsonResponse = async (response) => {
                try {
                    return await response.json();
                } catch {
                    return {};
                }
            };

            const loadTriggerWords = async () => {
                if (!ensureLoraSelected("[LoRA Trigger Words]")) {
                    return;
                }

                renderPanel("[LoRA Trigger Words] 読み込み中...");

                try {
                    const response = await api.fetchApi(PREVIEW_ROUTE, {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                        },
                        body: JSON.stringify(getRequestPayload()),
                    });
                    const data = await readJsonResponse(response);
                    renderPanel(
                        data.trigger_words ||
                        `[LoRA Trigger Words] preview API 応答が空です。HTTP ${response.status}`
                    );
                } catch (error) {
                    renderPanel(`[LoRA Trigger Words] preview 取得エラー: ${error}`);
                }
            };

            const loadModelCard = async ({ openViewerAfterLoad = false } = {}) => {
                if (!ensureLoraSelected("[Browse]")) {
                    return false;
                }

                renderPanel("[Browse] 読み込み中...");

                try {
                    const response = await api.fetchApi(BROWSE_ROUTE, {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                        },
                        body: JSON.stringify(getRequestPayload()),
                    });
                    const data = await readJsonResponse(response);
                    state.modelCardUrl = data.civitai_url || "";
                    state.modelCardData = data.card_data
                        ? {
                            ...data.card_data,
                            source_label: data.source_label || data.card_data.source_label || null,
                        }
                        : null;
                    renderPanel(
                        data.display_text ||
                        `[Browse] model card 情報が空です。HTTP ${response.status}`
                    );
                } catch (error) {
                    state.modelCardUrl = "";
                    state.modelCardData = null;
                    renderPanel(`[Browse] model card 取得エラー: ${error}`);
                }

                if (openViewerAfterLoad && state.modelCardData) {
                    openViewer(state.modelCardData);
                    return true;
                }
                return Boolean(state.modelCardData);
            };

            const browseModelCard = async () => {
                if (!ensureLoraSelected("[Browse]")) {
                    return;
                }

                if (state.modelCardData) {
                    openViewer(state.modelCardData);
                    return;
                }

                const loaded = await loadModelCard({ openViewerAfterLoad: true });
                if (!loaded) {
                    renderPanel(
                        `${state.lastPanelText}\n` +
                        "Viewer を開くには model card 情報を解決できる必要があります。"
                    );
                }
            };

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
                () => loadModelCard(),
                { serialize: false }
            );

            browseModelCardButton = this.addWidget(
                "button",
                "Browse Model Card (Load First)",
                "",
                browseModelCard,
                { serialize: false }
            );

            syncButtonLabels();
            renderPanel(state.lastPanelText);
            this.computeSize();
            this.setDirtyCanvas(true, true);
            return result;
        };
    },
});
