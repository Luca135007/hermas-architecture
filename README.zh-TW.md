**繁體中文** | [English](README.md)

# Hermas — 單張 16 GB GPU 上的多模型 AI 調度

**架構案例研究**：一個 Discord bot 如何在一張消費級 GPU（RTX 5070 Ti，16 GB VRAM）上，
同時提供圖像生成、對話 AI、提示詞工程與有狀態的文字 RPG——而其中兩個最大的工作負載
在物理上根本無法同時塞進這張卡。

本 repo 記錄的是一個真實運行系統的架構。重點不在任何單一功能，而在**資源仲裁**：
它讓互斥的工作負載得以共存於一張直覺上「不夠用」的硬體上。

## 核心限制

| 工作負載 | 後端 | VRAM | 駐留策略 |
|---|---|---|---|
| 圖像生成（Z-Image Turbo，2026-08 起 NVFP4 權重） | ComfyUI | 約 7.2 GB | 隨需載入 |
| 本機 LLM（qwen3.5:9b，16k context）——聊天、兩套 RPG、提示詞擴寫 | Ollama | 5.8 GB（2026-10-02 實測） | 常駐 30 分鐘 |

原本的 bf16 權重讓圖像生成峰值達 15.7 GB——距離整張卡的容量不到 2%，渲染時任何 LLM 都不能留在卡上。
2026-08 起改用 NVFP4 權重，只需約 7.2 GB，聊天模型可以同時常駐；但共用顯示卡時實測渲染 15.5 秒，
獨占時 8.8 秒，因此正式環境仍開啟禮讓（ADR-0001）。使用者期待聊天即時回應（不能每則訊息重載模型 30 秒）、
以 LLM 強化圖像提示詞，也期待渲染夠快；在這些需求間取得平衡正是本設計的核心。自 2026-10-02 起，所有本機 LLM 工作負載統一使用同一個 Ollama 模型（ADR-0006）；雲端備援不變。

## 關鍵設計決策

每個決策都以 ADR（架構決策紀錄）形式保存，包含當時評估過的替代方案與接受的取捨：

- [ADR-0001 — 雙向 VRAM 禮讓](docs/adr/0001-bidirectional-vram-yielding.md)：
  每個 GPU 使用者在執行前先驅逐對方，而不是靜態切分、CPU offload 或加購第二張卡。
- [ADR-0002 — 差異化 keep-alive 策略](docs/adr/0002-differentiated-keep-alive.md)：
  聊天模型常駐 30 分鐘；擴寫模型原本每次用完立即卸載（已被 ADR-0006 部分取代，
  擴寫改採與聊天相同的策略）。
- [ADR-0003 — 五層提示詞擴寫降級鏈](docs/adr/0003-prompt-expansion-fallback-chain.md)：
  本地模型優先，三個免費雲端模型居次，小型本地特化模型墊底——
  按品質排序的優雅降級，而非單點故障。
- [ADR-0004 — 管線呼叫一律關閉模型「思考」模式](docs/adr/0004-disable-model-thinking.md)：
  推理模式的輸出默默吃掉 token 額度、截斷回覆；在 API 層關閉它是可靠性修復，
  不是效能調校。
- [ADR-0005 — 少樣本提示詞一律用佔位符](docs/adr/0005-placeholder-ids-in-few-shot-prompts.md)：
  範例回目被一字不差照抄，範例裡寫死的角色也一再被拉回劇情；小型本地模型會把範例的具體內容當成
  可複製的內容，不只是格式示範。
- [ADR-0006 — 所有本機 LLM 工作負載共用單一常駐 Ollama 模型](docs/adr/0006-single-resident-local-llm.md)：
  聊天、兩套 RPG 與提示詞擴寫全部使用 `qwen3.5:9b`，`keep_alive` 與 `num_ctx` 一致；已移除 14B 模型。

## 架構

C4 風格的 context／container／component 視圖，含仲裁路徑的序列圖：
**[docs/architecture.md](docs/architecture.md)**（圖與正文為英文）

一覽：

```
Discord 使用者 ──> bot.py（asyncio、discord.py）
                    ├─ ComfyUI（HTTP＋WebSocket）     ── 圖像生成／改圖
                    ├─ Ollama（原生 API）             ── 聊天／擴寫／RPG 敘事
                    ├─ OpenRouter＋LM Studio          ── 擴寫降級層
                    ├─ Claude API（tarot_lib）        ── 塔羅解讀，無金鑰時退化為本地規則式
                    ├─ MemPalace（ChromaDB）          ── 長期對話記憶
                    └─ SQLite                         ── RPG 遊戲狀態，每頻道一列
```

## 功能

文生圖與圖生圖（含 LLM 提示詞強化）、多輪聊天（短期記憶存於行程內、長期記憶存於向量庫）、
LLM 擔任 GM 的持久化文字 RPG（SQLite 存檔）——另有一套限定於年齡限制頻道、獨立把關的
成人向變體，內容安全（成年白名單、親密門檻、圖片提示詞過濾）由程式而非提示詞把關——
語言學習測驗與每日單字推播、角色扮演對話練習與講評，以及塔羅占卜功能（單張指引／三張牌陣），其解讀優先呼叫 Claude API、
無 API 金鑰時自動退化為本地規則式解讀——這是一個不佔用 VRAM 的雲端工作負載，因此完全不參與
ComfyUI／Ollama 的資源仲裁。

## 維運

Runbook、故障模式、Prometheus／Grafana 監控設計，以及誠實列出的已知限制
（包括基於慣例的並發模型與其單一社群規模假設）：
**[docs/operations.md](docs/operations.md)**

監控是**已實作**而非僅止規劃——exporter 模組、抓取設定與自動佈建的儀表板都在
**[monitoring/](monitoring/)**。每個儀表板面板都對應回它所驗證的 ADR 不變量。

## 技術棧

Python 3.11 · discord.py 2.7 · ComfyUI（Z-Image Turbo）· Ollama（qwen3.5:9b）·
MemPalace/ChromaDB · SQLite · Windows 11、RTX 5070 Ti 16 GB

---

*文件優先的 repo：這裡保存的是一個私有系統的架構紀錄。設定全數由環境變數驅動；
此處與系統原始碼中皆不含任何憑證、ID 或個人資料。*
