# Azure Speech A/B Lab

這個目錄是 `hanzi-writing-lab` 的語音實驗區，目標是驗證 **zh-TW 指定注音發音**，並逐步建立可供 `hanzi-quiz` 使用的預產 MP3 流程。

## 入口

- A/B 實聽頁：`../azure-speech-ab.html`
- 測試資料：`cases.json`
- MP3 builder：`build_azure_speech.py`
- 產物：`generated/`

正式 Quiz 暫時不依賴本目錄；通過實聽驗收後才會導入「預產 MP3 → Quiz 優先播放 → Web Speech fallback」。

## Prototype 範圍

目前固定：

- 26 個短句
- 3 個 Azure zh-TW Neural voice
  - `zh-TW-HsiaoChenNeural`
  - `zh-TW-HsiaoYuNeural`
  - `zh-TW-YunJheNeural`
- 2 種指定讀音策略
  - `partial`：只對 `force=true` 的多音字／關鍵字加入 `<phoneme alphabet="sapi">`
  - `full`：整句依 `tokens[].zhuyin` 強制 phoneme
- 共 156 個 Azure MP3 版本
- A/B 頁另提供 Web Speech 基準，不額外產 Azure plain 版本

測試集除了多音字，也刻意加入「一、不」等連讀／變調案例，用來觀察「整句強制 phoneme」是否因為詞典型注音而變得不自然。這也是 full 與 partial 必須實聽比較的原因。

## GitHub Actions 設定

Repository secrets：

- `AZURE_SPEECH_KEY`
- `AZURE_SPEECH_REGION`

工作流：`.github/workflows/build-azure-speech-ab.yml`

只要 `cases.json`、builder 或 workflow 變動，就會執行。也可以從 GitHub Actions 手動 `workflow_dispatch`。

沒有 secrets 時，workflow 只執行 dry-run 並更新 manifest 狀態；不會嘗試呼叫 Azure。

## 產物與快取策略

MP3 使用內容雜湊命名。digest 包含：

- 句子文字
- 每字 resolved zhuyin
- voice
- partial/full 模式
- prosody rate
- output format

因此只要任何會影響聲音的輸入變更，就會得到新 MP3 檔名；未改變的音檔可直接重用。

目前輸出格式：

`audio-24khz-48kbitrate-mono-mp3`

## 本機執行

```bash
export AZURE_SPEECH_KEY='...'
export AZURE_SPEECH_REGION='eastasia'   # 依你的 Azure resource 為準
python3 tools/speech-lab/build_azure_speech.py
```

只檢查資料與 SSML、不呼叫 Azure：

```bash
python3 tools/speech-lab/build_azure_speech.py --dry-run
```

## A/B 驗收方式

建議分兩輪：

1. 固定同一 voice，比較 `partial` vs `full`。
2. 固定勝出的策略，再比較三個 voice。

每句至少判斷：

- 指定讀音是否正確
- 句子是否自然
- 是否適合兒童教材
- 哪個版本較好

A/B 頁的勾選與文字評語儲存在瀏覽器 `localStorage`，也可匯出 JSON 留存。

## 後續導入 Quiz 的門檻

在至少 20 句完成實聽、確認 voice 與策略後，才修改 `hanzi-quiz`：

1. 題目增加 audio asset metadata。
2. 進題時 preload 當題與下一題 MP3。
3. `聽整句` 優先播放預產 MP3。
4. MP3 不存在／載入失敗才 fallback 到 Web Speech。
5. Azure key 永遠不進兒童端網頁。
