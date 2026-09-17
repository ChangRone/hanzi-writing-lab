# AGENTS.md — Hanzi Writing Lab AI Entry Point

這份檔案是給後續 AI／自動化代理的**第一入口**。開始修改本 repository 前，先讀完本頁，再讀指定 canonical 文件。

## 1. 專案角色

`hanzi-writing-lab` 是正式 Quiz 上線前的**轉換、檢查、修正、QA 與實驗工具 repository**；不是兒童端正式 Quiz。

目前主要工具：

- 字形資料：`tools/d1-font-lab.html`
- 語音 A/B：`tools/azure-speech-ab.html`
- 語音產物邏輯：`tools/speech-lab/`
- 線上入口：`https://changrone.github.io/hanzi-writing-lab/`

下游正式使用者：

- 字形：`hanzi-quiz/char-data/{字}.json`
- 語音：未來核准後由 `hanzi-quiz` 使用 Lab 預產的 MP3；正式 Quiz 不應持有 Azure Speech key。

目前 Lab repository **沒有正式 `char-data/` / `char-data-overrides/` 目錄**；不要依舊 README 或頁面文字誤判。

### Speech Lab 邊界

使用者已決定：未來 Azure Speech 的 SSML／MP3 產生與 A/B 驗收邏輯可以放在 Lab repo。

目前策略：

```text
resolved tokens[].zhuyin
 → Lab 產 SSML
 → Azure zh-TW Speech
 → 預產 MP3 / content hash
 → A/B 人工實聽核准
 → Quiz 優先播放 MP3
 → MP3 不可用時 Web Speech fallback
```

正式導入 Quiz 前，先在 `tools/azure-speech-ab.html` 驗證 voice、partial/full phoneme 與自然度。語音工具規則見 `tools/speech-lab/README.md`。

## 2. 修改字形資料前必讀

### Canonical 資料轉換契約

**`docs/DATA_TRANSFORMATION_CONTRACT.md`**

這份文件定義：

- 新資料來源應如何做 Source Adapter
- Outline → `strokes`
- Track / centerline → `medians`
- radical metadata → `radStrokes`
- 共用座標 Normalize
- Track rematch / fallback median
- strict containment
- validation gates
- Needs Review / Approved 的流程語義
- 新來源接入 checklist
- 不可破壞的回歸基準

如果任務涉及「新字庫、教育部資料、D1、Hanzi Writer、SVG、outline、median、筆順、部首、字形匯入、字形轉換」，**先讀這份文件，不要直接改 HTML。**

## 3. 現行正式 runtime schema

```json
{
  "strokes": ["M ... Z"],
  "medians": [[[0, 0], [1, 1]]],
  "radStrokes": [0]
}
```

硬規則：

1. `strokes[i]` 是第 i 筆的封閉外框。
2. `medians[i]` 是同一筆的中心書寫路線。
3. median 點序代表書寫方向。
4. outline 與 median 必須套用同一 coordinate transform。
5. stroke index / array order 具有筆順語義，不可為了畫面好看重排。
6. `radStrokes` 沒有可靠來源時用 `[]`，不可猜。
7. source / debug / QA metadata 不屬於目前正式 runtime JSON。

## 4. 目前字形來源

- 主要 D1：`g0v/zh-stroke-data@master/utf8/{hex}.xml`
- 備援 D1：`zh-stroke-data@0.0.75/utf8/{hex}.xml`
- Hanzi Writer 官方資料：目前主要作參考／`radStrokes` 來源

D1 核心映射：

```text
Stroke / Outline → strokes[]
Stroke / Track   → medians[]
official radStrokes → radStrokes[]（相容時）
```

**Outline 不等於 median。**

## 5. 現行字形驗證基準

有效 containment 邏輯是：

**strict containment + draw sampling patch v2**

不要回退成只有 bbox containment。

Containment PASS 只表示 median 沒有大量離開 stroke fill，不代表：

- 筆順正確
- median 位於視覺中心
- 教育語義正確
- 已可直接部署

使用 fallback / rematch / 手工修 median 的字，應視為需要更高層 review 的 Candidate。

## 6. 新字形資料來源的正確接法

```text
Raw Source
 → Source Adapter
 → Normalize
 → Normalized Candidate
 → Validation
 → Needs Review / Approved
 → Exported char-data
```

不要把來源特例散落到共用 Normalize；先建立 Adapter，明確記錄：

- 來源格式
- stroke order
- outline
- centerline / track
- coordinate system
- radical metadata
- immutable version / commit（如果來源提供）

## 7. 不可直接做的事

- 不要把 glyph 整體 outline 假裝成逐筆 stroke。
- 不要把 outline vertices 當 median。
- 不要分別縮放 stroke 與 median。
- 不要只靠 AI 看圖猜筆順或 radical index。
- 不要把 fallback 當 Approved。
- 不要只改大型 HTML 前段的舊函式；檔尾可能有 effective patch 覆寫。
- 不要在沒有回歸驗證時重構 `tools/d1-font-lab.html`。
- 不要假設 Lab 已能自動 commit 字形資料到 Quiz；現況仍是下載後人工提交。
- 不要把 Azure Speech key / region 寫進公開 HTML、JSON 或正式 Quiz；只允許透過環境變數／GitHub Actions secrets 使用。
- 不要把 Speech Lab 的實驗音檔直接視為正式教材音檔；必須經 A/B 實聽與讀音 QA。

## 8. 文件優先序

發生描述衝突時，按以下順序判斷：

1. 使用者最新明確決策
2. 對應領域 canonical 文件：字形為 `docs/DATA_TRANSFORMATION_CONTRACT.md`；語音為 `tools/speech-lab/README.md`
3. `AGENTS.md`
4. 目前實際生效的工具程式
5. `README.md`
6. 歷史討論／舊盤點文件

若 canonical 文件與實際 runtime 不一致，先判斷是否為 regression，不要直接用程式現況覆寫正式設計決策。
