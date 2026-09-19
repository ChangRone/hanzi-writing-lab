# Azure Speech A/B 實聽驗收紀錄 — 2026-09-19

## 結論

26 個測試句完成 A/B 實聽後：

- 26 / 26 選擇 A
- A = `zh-TW-HsiaoChenNeural` + `partial`
- B = `zh-TW-HsiaoChenNeural` + `full`
- A 的實聽評價：正確、自然、可用
- q02 備註：B 語速太快
- q18：B 的讀音正確性被判為 false
- 正式 production 最終再依實聽意見降速為 `rate="-12%"`

因此正式規格採：

```text
voice = zh-TW-HsiaoChenNeural
mode  = verified-partial
rate  = -12%
```

## partial 的定義

A 版本不是完全不指定讀音。

只有 A/B corpus 中明確標成 `force=true`、並通過人工實聽的「字＋注音」組合，
才使用 Azure SAPI phoneme 強制發音；其餘文字維持普通中文字，讓 Azure 依完整句子做自然語音推論。

這樣可以同時達到：

1. 多音字需要時能被指定。
2. 不會像 full phoneme 一樣把整句每個音節全部鎖死。
3. 保留一、不等連讀／變調與自然語氣。
4. 避免正式題庫中尚未人工驗證的舊注音資料被直接強制成錯誤語音。

## 與 production pipeline 的關係

這份 A/B 驗收是 production force set 的準入依據。

若未來新增某個需要強制讀音的字詞：

1. 先加進 `tools/speech-lab/cases.json`
2. 產生 A/B
3. 人工實聽
4. 確認 partial 表現
5. 才允許把相同「字＋注音」組合用於正式 production MP3

不要直接因為 `tokens[].zhuyin` 有值，就把它全部轉成 phoneme。

## 原始評分

原始匯出時間：

`2026-09-19T01:28:23.414Z`

此次驗收的原始 JSON 由 A/B Lab 匯出；本文件保存決策性摘要。
