# Hanzi Quiz 正式 Azure 語音：產生、保存與重現流程

## 1. 正式決策

2026-09-19 完成 26 句 A/B 實聽驗收。

正式規格：

- Azure voice：`zh-TW-HsiaoChenNeural`
- pronunciation strategy：`verified-partial`
- prosody rate：`-12%`
- output：每一題一個 MP3
- Quiz runtime：只播放正式 MP3；正式資產缺失時顯示錯誤，不再自動切回舊 Web Speech
- 保存位置：
  - Lab：`production-audio/v1/audio/<questionId>.mp3`
  - Quiz：`assets/audio/v1/<questionId>.mp3`

A/B 驗收的 A 版本是 HsiaoChen + partial phoneme。26 題全部選 A。
partial 的原則不是強制全部注音，而是只有經 A/B 驗證的「字＋注音」組合使用 SAPI phoneme；
其他字由 Azure 根據完整句子判讀，保留自然的連讀、變調與語氣。

## 2. Source of Truth

正式句子與題目 ID：

- Repo：`ChangRone/hanzi-quiz`
- Catalog：`quiz-catalog-v2.json`
- 題目：Catalog 內 `dataUrl` 指向的 `packs/*.json`
- 文字：`questions[].readText`
- 注音 context：`questions[].tokens[].zhuyin`

正式強制 phoneme 白名單來源：

- `tools/speech-lab/cases.json`
- 只有 token 第三欄 `true` 的字音組合才可進 production force set。

不要把正式題庫中所有 `tokens[].zhuyin` 全部強制給 Azure。
題庫可能存在待修正的舊 resolved reading；full phoneme 也已在實聽中被確認較不自然。

## 3. 主要程式與 CI

- A/B builder：`tools/speech-lab/build_azure_speech.py`
- 正式 builder：`tools/speech-lab/build_quiz_production_audio.py`
- A/B workflow：`.github/workflows/build-azure-speech-ab.yml`
- 正式 workflow：`.github/workflows/build-quiz-production-audio.yml`
- 正式決策：`production-audio/DECISION.md`
- 本文件：`production-audio/REPRODUCIBILITY.md`

需要的 GitHub Actions Secrets：

- `AZURE_SPEECH_KEY`
- `AZURE_SPEECH_REGION`

Azure key 永遠不可放入 Quiz 前端、題庫 JSON、manifest 或公開文件。

## 4. 正式生成流程

Workflow 會：

1. checkout `hanzi-writing-lab`
2. clone 最新 `ChangRone/hanzi-quiz` 到 `.cache/hanzi-quiz`
3. 安裝 `ffmpeg`
4. dry-run preflight：
   - 讀 Catalog v2
   - 只處理 Catalog 正式 included packs
   - 驗證 question id 唯一
   - 驗證 `tokens[].char` 串接結果等於 `readText`
5. 使用 Azure Speech 產 PCM：
   - voice：HsiaoChen
   - mode：verified partial
   - rate：-12%
6. 為降低 Azure transaction 次數，以多句一批合成：
   - 預設 batch size：20
   - 句間插入長 SSML break
7. 以長靜音切回每一題 PCM
8. 使用 ffmpeg 轉成每題 MP3
9. 驗證每一個 manifest item：
   - `ready=true`
   - 實體檔存在
   - size > 500 bytes
10. commit：
   - `production-audio/v1/manifest.json`
   - `production-audio/v1/audio/*.mp3`

2026-09-19 正式資料量：

- 207 課
- 2070 句
- 2070 個 MP3
- batch size 20
- 約 104 次 Azure request

## 5. 本機重現

前提：

```bash
export AZURE_SPEECH_KEY='...'
export AZURE_SPEECH_REGION='...'
```

準備最新 Quiz：

```bash
rm -rf .cache/hanzi-quiz
git clone --depth 1 https://github.com/ChangRone/hanzi-quiz.git .cache/hanzi-quiz
```

只驗證、不呼叫 Azure：

```bash
python3 tools/speech-lab/build_quiz_production_audio.py --dry-run
```

正式產生：

```bash
python3 tools/speech-lab/build_quiz_production_audio.py
```

指定 batch size：

```bash
AZURE_TTS_BATCH_SIZE=20 python3 tools/speech-lab/build_quiz_production_audio.py
```

必要工具：

- Python 3
- ffmpeg
- git
- 可連線 Azure Speech endpoint

## 6. MP3 命名與可重建性

正式 MP3 路徑固定以 question ID 命名：

```text
production-audio/v1/audio/<questionId>.mp3
```

manifest 的 digest 會考慮：

- question id
- readText
- tokens
- 實際被 force 的字音
- voice
- mode
- rate
- output format

因此輸入或正式語音參數改變時，可以判斷既有 MP3 是否可重用。

## 7. Quiz 同步規則

Lab 是「生成與驗證來源」，Quiz 是「正式執行資產」。

完成 Lab generation 後，由 Quiz repo 自己的 GitHub Action：

1. 讀 Lab 的 `production-audio/v1/manifest.json`
2. 逐一下載 Lab repo 中的正式 MP3
3. 放到 Quiz：
   `assets/audio/v1/<questionId>.mp3`
4. 保存一份 manifest / source metadata
5. 驗證 Quiz Catalog 中所有正式 question ID 都有 MP3
6. commit 到 Quiz main
7. GitHub Pages 部署後，Quiz runtime 使用同源相對路徑，不跨 repo 取音檔。

兩個 repo 都必須保存相同正式版本的 MP3。

## 8. Quiz runtime 規則

正式環境目標：

```text
題目 questionId
    ↓
assets/audio/v1/<questionId>.mp3
    ↓
preload 當題 + 下一題
    ↓
HTMLAudioElement.play()
```

不再把 Web Speech 當 production fallback。

若正式 MP3 缺失或讀取失敗：

- 顯示「語音檔載入失敗」
- 保持作答可用
- 不偷偷播放系統舊語音

如此才能讓語音錯誤被看見，而不是被 fallback 掩蓋。

## 9. 2026-09-19 事故紀錄

第一次正式 generation 曾出現：

```text
PRODUCTION_AUDIO_VALIDATE=PASS questions=2070
No production audio changes.
```

根因：

Workflow 用：

```bash
git diff --quiet -- production-audio/v1
```

判斷是否有變更。

但第一次生成的 MP3 與 manifest 都是 **untracked files**，
一般 `git diff` 不會列出 untracked files，因此被誤判成沒有差異。
Runner 結束後，2070 個已產生且驗證通過的 MP3 全部消失，也沒有進 GitHub Pages。

正確做法：

```bash
git add production-audio/v1
git diff --cached --quiet -- production-audio/v1
```

必須先 stage，再檢查 staged diff。

這個事故也說明：不能只用「Azure generation step success」判斷正式語音已上線。
正式完成條件應同時包含：

1. Lab MP3 已 tracked / committed
2. Lab manifest 可從 repo 讀到
3. Quiz MP3 已同步 committed
4. Quiz Pages 可讀取同源 MP3
5. Browser smoke 確認實際播放來源為 MP3，而非 speechSynthesis

## 10. 修改正式語音前的流程

若未來要改 voice、rate 或 forced reading：

1. 先在 A/B Lab 建測試案例
2. 人工實聽
3. 記錄接受結果
4. 更新 `cases.json` / decision
5. regenerate production assets
6. 驗證 Lab
7. sync Quiz
8. browser smoke
9. 才視為正式完成

不要直接在 Quiz runtime 即時呼叫 Azure，也不要把 Azure key 下放到瀏覽器。
