# Hanzi Writing Lab｜D1 字庫工坊

`hanzi-writing-lab` 是給字形資料維護者使用的**字形轉換、檢查、修正與 QA 工具**。目前主要把 `zh-stroke-data` D1 XML 轉成 Hanzi Writer 相容 JSON，並提供 median 修正、containment 檢查、動畫／書寫測試與下載。

## 快速入口

- 線上工具：<https://changrone.github.io/hanzi-writing-lab/>
- 工具程式：`tools/d1-font-lab.html`
- **AI／自動化代理先讀：`AGENTS.md`**
- **資料來源轉換正式規格：`docs/DATA_TRANSFORMATION_CONTRACT.md`**

## 正式輸出模型

```json
{
  "strokes": ["M ... Z"],
  "medians": [[[0, 0], [1, 1]]],
  "radStrokes": [0]
}
```

核心對應：

```text
來源筆畫外框 / Outline → strokes[]
來源書寫中心線 / Track → medians[]
可靠的部首筆畫索引      → radStrokes[]
```

新增任何字形資料來源時，不要直接在共用轉換邏輯中加入來源特例；先依 `docs/DATA_TRANSFORMATION_CONTRACT.md` 建立／設計 Source Adapter，再進共同 Normalize、Validation 與 Review 流程。

## Repository 現況

```text
hanzi-writing-lab/
├─ README.md
├─ AGENTS.md
├─ index.html
├─ docs/
│  └─ DATA_TRANSFORMATION_CONTRACT.md
└─ tools/
   └─ d1-font-lab.html
```

**注意：**目前本 repository 並沒有正式 `char-data/` 或 `char-data-overrides/` 目錄。Lab 產出的核可 JSON 現階段仍由人工下載後，提交到下游 `hanzi-quiz/char-data/{字}.json`。不要把頁面上的下載建議路徑誤認為本 repo 已存在的資料目錄。

## 現行重要行為

- 主要 D1：`g0v/zh-stroke-data@master`
- 備援 D1：`zh-stroke-data@0.0.75`
- Hanzi Writer 官方資料：參考／`radStrokes` 用途
- Outline 與 median 必須使用同一 coordinate transform
- median 點序代表書寫方向
- 有效幾何檢查基準：**strict containment + draw sampling patch v2**
- containment PASS 不等於筆順／教育語義已核可
- fallback、Track rematch、手繪修正後仍應視情況進人工 review

詳細規則、來源接入步驟、fail-closed 原則與回歸基準，統一以 `docs/DATA_TRANSFORMATION_CONTRACT.md` 為準。
