# Hanzi Writing Lab｜資料來源轉換契約

> **Canonical / AI handoff 文件**  
> 更新日期：2026-09-15  
> 適用 repository：`ChangRone/hanzi-writing-lab`  
> 實作基準：`main` 的 `tools/d1-font-lab.html`  
> 目的：讓後續 AI／維護者能在**不破壞既有 Lab 行為**的前提下，把新的字形資料來源正確轉換成 Lab 可預覽、檢查、修正與輸出的元素。

---

## 1. 先記住 Lab 的角色

`hanzi-writing-lab` 是**字形資料產生與 QA 工具**，不是兒童端正式作答產品。

目前正式流程是：

```text
外部字形來源
  → Source Adapter（只處理來源差異）
  → Normalize（共同座標、筆畫、median 規則）
  → Lab Candidate
  → 自動驗證 Gate
  → 必要時人工修正
  → Approved / Export JSON
  → hanzi-quiz/char-data/{字}.json
  → Quiz 書寫判定
```

目前 Lab 本身沒有資料庫、審核資料表或 GitHub 自動提交；`Approved` 是流程語義，不是現有 runtime 中已持久化的欄位。現階段仍是由使用者下載 JSON，再提交到下游 repository。

**重要：**不要把「Lab 能輸出 JSON」誤認為「該字已經核可」。自動 fallback、containment PASS、動畫可顯示，都不等於教育上的筆順／運筆已被確認。

---

## 2. Lab 真正的 runtime 字形模型

Lab 與 Hanzi Writer 最終使用的正式輸出只保留三個欄位：

```json
{
  "strokes": ["M ... Z"],
  "medians": [
    [[100, 200], [120, 210], [140, 230]]
  ],
  "radStrokes": [0]
}
```

### 2.1 `strokes[]` — 筆畫外框

- 每一項代表一筆。
- 值為**封閉 SVG path**。
- 用途：Hanzi Writer 顯示字形、Lab 原始 SVG 預覽、containment 幾何判斷。
- 這是「筆畫的面積／外框」，**不是書寫路徑**。

### 2.2 `medians[][][]` — 書寫中心線

- `medians[i]` 必須對應 `strokes[i]`。
- 每一筆至少 2 個 `[x, y]` 點。
- 點的先後順序代表該筆的**書寫方向**。
- 用途：Hanzi Writer 書寫判定、Lab median 線／方向箭頭、方向檢查。

### 2.3 `radStrokes[]` — 部首筆畫索引

- 內容是 0-based stroke index。
- 主要影響部首高亮。
- 不決定 stroke 外框，也不決定書寫 median。
- 沒有可靠資料時可以是 `[]`；**不可憑外觀猜部首筆畫索引**。

### 2.4 Lab 畫面上的其他元素不是 runtime schema

以下都是由三個正式欄位或 QA 狀態衍生出的顯示／診斷，不應塞進正式 `{字}.json`：

- 目前選取筆畫
- median 起點／終點標記
- 方向箭頭
- containment 異常標記
- source URL
- fallback / rematch 記錄
- validation 訊息
- 手繪中的暫存路徑
- debug / report metadata

若需要保存來源與 QA 記錄，應放在 report／sidecar／未來的 metadata 檔，而不是擴充目前正式 runtime JSON 後直接丟給 Quiz。

---

## 3. 新資料來源必須先經過 Source Adapter

新來源不要直接改 Lab 的共用 Normalize 邏輯來「配合來源」。正確做法是：

```text
來源特有格式
   ↓
Source Adapter
   ↓
共同可理解的筆畫資料
   ↓
Normalize / Validation
```

Source Adapter 至少要回答下列問題：

| 問題 | 必須知道的內容 |
| --- | --- |
| 一個字怎麼定位？ | Unicode code point、字串、檔名或 API key |
| 一筆怎麼表示？ | Stroke 節點、path、polygon、command list… |
| 外框在哪裡？ | Outline / filled path / polygon |
| 中心線在哪裡？ | Track / median / centerline；若來源沒有要明確標示 |
| 筆畫順序在哪裡？ | array 順序、index、order 欄位 |
| 座標原點在哪裡？ | 左上、左下、其他 |
| Y 軸方向？ | 向下增加或向上增加 |
| 單位與 viewBox？ | 原始座標範圍 |
| 是否有 radical 資訊？ | 明確索引、部首標記，或完全沒有 |
| 來源版本？ | tag / commit / release / URL；可重現時應保存 |

### 3.1 建議的 Adapter 中介概念

以下是**文件層的 canonical 概念**，不是要求目前 JS 已經存在同名 object：

```json
{
  "character": "永",
  "source": {
    "id": "example-source",
    "version": "immutable-version-or-commit",
    "url": "..."
  },
  "coordinateSystem": {
    "yDirection": "up",
    "viewBox": [0, 0, 1024, 1024]
  },
  "strokes": [
    {
      "outline": "source-specific outline or parsed commands",
      "track": [[100, 100], [120, 140]],
      "radical": false
    }
  ]
}
```

Adapter 的責任是**忠實解讀來源**，不要在 Adapter 階段偷偷：

- 重排筆順
- 猜 median
- 猜部首
- 個別縮放每一筆
- 修正「看起來不順眼」的字形

這些行為若需要，必須進入後續 Normalize／Repair／Review，並留下可辨識的紀錄。

---

## 4. 目前 D1 Adapter 的確定映射

目前 Lab 主要來源是 `zh-stroke-data` 的 D1 XML：

```text
主要：
https://cdn.jsdelivr.net/gh/g0v/zh-stroke-data@master/utf8/{hex}.xml

備援：
https://cdn.jsdelivr.net/npm/zh-stroke-data@0.0.75/utf8/{hex}.xml
```

目前工具也可載入 Hanzi Writer 官方 JSON 作參考：

```text
https://cdn.jsdelivr.net/npm/hanzi-writer-data@latest/{charEncoded}.json
```

D1 → Lab 對應如下：

| D1 / 來源元素 | Lab 中的用途 | 最終欄位 |
| --- | --- | --- |
| `Stroke` | 一筆的容器／筆順 | 決定 index |
| `Outline` | 筆畫填色外框 | `strokes[i]` |
| `MoveTo` / `LineTo` / `QuadTo` / `CubicTo` / `Close` | 組成 SVG path | `strokes[i]` |
| `Track` 座標點 | 書寫中心線候選 | `medians[i]` |
| Hanzi Writer 官方 `radStrokes` | 部首索引參考 | `radStrokes` |
| source URL / rematch / fallback | 稽核資訊 | report；不進正式 JSON |

**不可把 `Outline` 點直接當 median。** Outline 描述的是筆畫邊界；Track／median 描述的是筆尖書寫中心路線，兩者語義不同。

---

## 5. Normalize：所有來源共用的核心轉換

### 5.1 Outline → `strokes[]`

來源 outline 要先轉成可被瀏覽器 SVG 與 Hanzi Writer 使用的 path。

目前 D1 已支援：

- MoveTo
- LineTo
- QuadTo
- CubicTo
- Close / ClosePath

新來源若已直接提供合法 SVG path，可以保留其幾何語義，但仍須進共同座標轉換與驗證。

### 5.2 Outline 與 median 必須共用同一套座標轉換

**這是硬規則。**

不能把 stroke 外框和 median 各自「縮到看起來剛好」。兩者如果不是共用同一 transformation，median 與 stroke 的幾何關係會被破壞。

目前預設目標設定：

| 設定 | 預設值 |
| --- | ---: |
| target x1 | 60 |
| target x2 | 980 |
| target y1 | -60 |
| target y2 | 855 |
| padding ratio | 0.94 |
| Y 軸 | 預設翻轉到 Hanzi Writer 座標 |

共同 Normalize 原則：

1. 收集該字所有 outline + track／median 的原始座標。
2. 計算整體 bounding box。
3. 根據來源 coordinate system 判斷是否需要 Y flip。
4. 等比例縮放；不可 X/Y 不同比例拉伸。
5. 在目標範圍置中。
6. 對 outline 與 median 套用完全相同 transform。
7. 現行實作最後轉成整數座標。

### 5.3 Y flip 不應靠猜

目前 UI 保留「翻轉／不翻轉」選項，方便人工處理來源差異。

新增正式 Adapter 時，應明確在來源規格中記錄 Y 軸方向；不要讓 AI 單純因為「畫面上下顛倒」才在程式中散落特例。

---

## 6. Median：配對、方向與 fallback

### 6.1 正常路徑

若來源本身有 centerline / Track：

```text
來源 Track
 → 套用同一座標 transform
 → 與對應 stroke 配對
 → medians[i]
```

### 6.2 目前 D1 配對策略

現行 `transformRaw` 的有效邏輯概念：

1. 優先使用相同 index 的 Track。
2. 先檢查該 Track bbox 是否位於放寬後的 stroke bbox。
3. 若不合理，從尚未使用的 Track 中找較合理候選重新配對。
4. 仍找不到合理 Track 時，才建立簡化 fallback median。
5. rematch / fallback 都必須被視為「需要特別注意的來源紀錄」。

這裡的 bbox 只是第一階段幾何篩選，**不能取代 strict containment**。

### 6.3 Fallback median

目前 fallback 可依 stroke / outline bbox 產生簡化 median；自動修正也可能使用約 7 點的簡化路線。

fallback 的目的：

> 讓 Candidate 可以被 Lab 顯示與進一步檢查，而不是宣布該筆已正確。

因此新 Adapter 若沒有真正 median：

- 可以建立 Candidate fallback；
- 必須標示為 fallback / review required；
- 不應直接把整批 fallback 結果當 Approved；
- 彎曲、折轉、鉤等筆畫尤其需要人工或更高階重建。

### 6.4 Median 點順序就是書寫方向

方向修正只應改 `medians[i]` 的點序列，不應改 `strokes[i]`。

目前 Lab 會用起終點的 `dx / dy` 做「疑似反向」警告，但這只是幾何 heuristic，不懂漢字筆順語義。

因此：

- warning 可以自動產生；
- **不要只因 warning 就自動認定正確方向**；
- 人工「反轉目前筆 median」是合理的修正操作；
- 若新來源本身有可靠方向資訊，應由 Adapter 保留來源順序。

### 6.5 手繪 median

Lab 目前可人工沿 stroke 中心重畫 median；有效版本會：

1. 收集手繪軌跡；
2. 用 Ramer–Douglas–Peucker 簡化；
3. 依距離重新取樣；
4. 寫回 `medians[index]`；
5. 立即做 strict containment。

目前預設：

- 簡化容差：3 px
- 重取樣間距：14 px

手繪是人工修正工具，不應成為新來源 Adapter 的預設自動行為。

---

## 7. `radStrokes` 的來源優先序

建議規則：

1. **來源若明確提供 radical stroke index，優先用來源資料。**
2. 若使用 Hanzi Writer 官方參考，必須先確認筆畫數與 index 語義相容。
3. 不相容或無可靠資料時使用 `[]`。
4. 不可因為部件位置或字形外觀由 AI 猜 index。

目前 D1 工具的 `official` 模式會參考 Hanzi Writer 官方 `radStrokes`；取得失敗不會讓 D1 字形轉換整體失敗，因為它不影響 stroke／median 本體。

---

## 8. Validation Gate：Candidate 何時才可視為可用

後續新來源接入時，至少依下列 Gate 思考。當前單頁工具並未把所有 Gate 持久化成狀態機，因此文件規則比目前 UI 更嚴格；這是未來自動化時要遵守的 contract。

### Gate A — Parse / Structure

必須成立：

- 至少有 1 stroke。
- `strokes.length === medians.length`。
- 每個 stroke 是非空 SVG path 字串。
- 每個 median 至少 2 點。
- 每個 median point 都是有限數字座標。
- `radStrokes` 若非空，必須是合法、不重複、未超出範圍的整數 index。

目前工具已實作其中大部分基本檢查；新增 Adapter 時不要降低條件。

### Gate B — Geometry / Strict containment

目前有效版本是 **strict containment + draw sampling patch v2**，不要回退成只看 bbox 的舊判斷。

概念：

1. 把 `strokes[i]` 放入瀏覽器 SVG。
2. 沿 `medians[i]` 的每一段補取樣點。
3. 用 `isPointInFill` 判斷點是否在 stroke fill 內。
4. 外部點再估算到 path 邊界距離。
5. 超過允許距離的比例過高 → 異常。

目前預設：

| 設定 | 預設值 |
| --- | ---: |
| 允許離開 stroke 距離 | 10 px |
| 允許異常比例 | 0.03 |
| 每段檢查步距 | 12 px |

Containment PASS 只表示 median 幾何上沒有大量跑出 stroke，**不代表路徑位於視覺中心，也不代表筆順正確**。

### Gate C — Direction / Stroke semantics

- 顯示方向 warning。
- 必要時比較來源筆順、官方參考或人工判讀。
- 不以幾何 warning 直接取代語義確認。

### Gate D — Hanzi Writer Preview / Writing Test

至少要能：

- 正常建立 Hanzi Writer instance。
- 動畫依正確筆數播放。
- Lab 原始 SVG 與 Hanzi Writer 字形位置大致一致。
- 書寫測試不出現明顯錯筆配對。

目前 Lab 測試設定與 Quiz 並不完全相同，因此 Lab PASS 不能當成 Quiz E2E 已驗收。

### Gate E — Human Review

以下情況原則上應進人工確認：

- Track 被重新配對。
- 使用 fallback median。
- median 被自動重建或手繪修改。
- 筆畫數與參考來源不一致。
- 來源之間對筆順／外框／方向有衝突。
- containment 邊界非常接近閾值。
- 實際練習回報該字有異常。

---

## 9. Fail-closed 與 fallback 原則

新來源整合時使用以下原則：

| 異常 | 正確處理 |
| --- | --- |
| 來源抓不到 | 可嘗試明確設定的備援來源；保留來源身分 |
| XML/JSON 無法解析 | FAIL；不可產生假的空字形 |
| 沒有 outline / stroke geometry | FAIL，除非另有明確 Adapter 能提供等價外框 |
| 有 outline、沒有 median | 建立 Candidate fallback + review required，不直接核可 |
| Track 對錯 stroke | rematch → strict containment → review |
| radical 資料缺失 | `radStrokes: []`，不要猜 |
| 來源 A/B 不一致 | 保留成不同 candidate 或明確選源；不要偷偷混成一份 |
| strict containment FAIL | 自動修正只能產生新 Candidate；不得直接視為 Approved |

**禁止 silent correction。** 任何會改變來源筆畫語義的修正都要能被後續維護者知道。

---

## 10. 新資料來源接入標準流程

後續 AI 若被要求「把某新字庫接到 Lab」，請依序做：

### Step 1 — 先研究來源，不改 runtime

整理：

- 格式與欄位
- 字元定位方式
- stroke order
- outline representation
- centerline / median 是否存在
- coordinate system
- radical metadata
- 版本／commit／license／可重現 URL

### Step 2 — 寫 Source Mapping

至少列出：

```text
source.<field> → Lab meaning
```

尤其必須明確回答：

```text
哪個欄位 → strokes
哪個欄位 → medians
哪個欄位 → radStrokes
哪些只是 metadata，不可進 runtime JSON
```

### Step 3 — 只新增 Adapter，不複製一套 Normalize

共用：

- coordinate transform
- stroke/median 對齊原則
- containment
- direction diagnostics
- preview
- export schema

來源差異應盡量留在 Adapter。

### Step 4 — 小樣本驗證

至少選：

- 簡單字
- 多筆畫字
- 彎／鉤較多字
- 已知 Lab 曾有 median 問題的字族
- 有／無 radical metadata 的字

先確認 mapping，再全量跑；不要一開始就把新來源全量寫入正式字庫。

### Step 5 — 比對三個層次

```text
來源原始資料
↕
Normalize 後的 stroke / median
↕
Lab SVG + Hanzi Writer 實際呈現
```

任何一層不一致都先修 Adapter／Normalize，不要用最終畫面上的手工 offset 掩蓋來源問題。

### Step 6 — Gate + Review

Gate 全過且必要人工確認完成後，才視為 Approved candidate。

### Step 7 — Export

正式下游仍維持：

```text
hanzi-quiz/char-data/{字}.json
```

直到專案正式改變部署架構之前，不要假設 `hanzi-writing-lab` repository 內存在正式 `char-data/`。

---

## 11. Lab 顯示元素與資料欄位對照

這張表是後續 AI 最常需要查的速查表：

| Lab 畫面／功能 | 真正資料來源 | 可以從哪裡轉換 |
| --- | --- | --- |
| 黑色／選取的筆畫外框 | `strokes[i]` | source outline / SVG path |
| 紅色／灰色 median 線 | `medians[i]` | source track / centerline / reviewed fallback |
| median 起點／終點 | `medians[i][0]` / 最後一點 | 不需額外來源 |
| 方向箭頭 | median 點序 | 不需額外來源 |
| 部首高亮 | `radStrokes` | source radical index / 相容的官方 reference |
| stroke list 筆數 | `strokes.length` | source stroke order |
| containment badge | stroke + median 的幾何檢查結果 | 衍生資料，不進正式 JSON |
| Hanzi Writer 動畫 | `strokes` + `medians` + `radStrokes` | Normalize 後正式 candidate |
| 書寫判定 | 主要依 median / stroke 幾何 | Normalize 後正式 candidate |
| debug/report | source + transformation + diagnostics | sidecar / 報告，不進正式 JSON |

---

## 12. 後續 AI 絕對不要做的事

1. **不要把 outline 當 median。**
2. **不要把 stroke 與 median 分開縮放或置中。**
3. **不要為了畫面好看重排 strokes。** stroke index 就是筆順語義的一部分。
4. **不要只因 containment PASS 就宣告資料正確。**
5. **不要只依方向 heuristic 自動反轉所有 warning。**
6. **不要用 AI 外觀判斷猜 `radStrokes`。**
7. **不要把 fallback median 當正式來源 median。**
8. **不要把 source/debug/QA metadata 塞進現行正式 `{字}.json` 而不做 schema migration。**
9. **不要修改前段舊函式後就以為生效。** 現有大型 HTML 尾端有 patch 覆寫；先確認實際最後 binding／effective implementation。
10. **不要破壞 strict containment + draw sampling patch v2。** 若要重構，先做等價回歸。
11. **不要假設 Lab repo 已有 `char-data/`。** 現況正式字形資料在 Quiz 下游。
12. **不要讓新來源特例散落在共用轉換邏輯。** 先做 Adapter。

---

## 13. 現有功能的回歸基準

任何新 Adapter／Normalize 重構完成後，至少不能破壞：

1. `/tools/d1-font-lab.html` 可直接開啟。
2. 單字可由主要 D1 與備援 D1 產生。
3. Outline → `strokes`、Track → `medians`。
4. Y flip、target range、padding 調整後可重產。
5. 可載入官方參考與本機既有 JSON。
6. 選取一筆後可反轉、重建、手繪 median，並 undo。
7. 手繪後仍做簡化、重取樣與 strict containment。
8. 基本結構檢查與 containment 能指出問題筆畫。
9. Hanzi Writer 動畫與書寫測試仍讀目前 Candidate。
10. Debug／部署／覆寫／報告下載仍可用。
11. 批次字表仍可去重並輸出 ZIP／報告。
12. 正式輸出 schema 仍是 `strokes` / `medians` / `radStrokes` 三欄。

---

## 14. 資料狀態的統一用語

後續討論與文件建議固定使用：

```text
Raw Source
  → Normalized Candidate
  → Validated Candidate
  → Needs Review / Approved
  → Exported char-data
```

含義：

- **Raw Source**：原始來源；不可直接當 Lab 正式資料。
- **Normalized Candidate**：已轉成 Lab 座標與 schema，但還沒證明正確。
- **Validated Candidate**：自動 gate 已通過。
- **Needs Review**：存在 fallback、rematch、方向／來源衝突等需人工判斷事項。
- **Approved**：可作為下游正式字形的候選版本。
- **Exported char-data**：已輸出成 Hanzi Writer 相容的三欄 JSON。

現行工具沒有持久化這些狀態；若未來做 Corpus Review Dashboard／Gitea 或 GitHub 審核流程，應沿用這組語義，而不是另造互相衝突的名稱。

---

## 15. 一句話判斷新來源能不能接

只要新來源能可靠回答：

> **「每一筆的外框是什麼、中心書寫路線是什麼（或明確沒有）、筆順是什麼、座標系統是什麼？」**

就能透過 Adapter 進入 Lab。

如果只能提供「整個字的字型輪廓」，卻無法拆成逐筆 stroke，更無可靠 stroke order／median，就**不能直接轉成等價的 Lab / Hanzi Writer 書寫資料**；必須先增加筆畫分解／median 重建流程，並把產物視為 Candidate 進行驗證與人工核可。

---

## 16. 維護規則

當以下任一事項改變時，要同步更新本文件：

- 正式 output schema
- coordinate transform
- Track / median matching
- fallback / reconstruction
- strict containment
- approval / deployment flow
- 新增或移除主要資料來源
- Quiz 的 char-data 接口

如果程式行為與本文件衝突：

1. 先確認是否是程式 regression；
2. 不要默默把文件改成迎合錯誤行為；
3. 若確定是新的正式設計，再一起更新程式、測試與本文件。
