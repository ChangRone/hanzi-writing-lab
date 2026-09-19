# Production Speech Decision

Accepted from the 26-case A/B listening review:

- Voice: `zh-TW-HsiaoChenNeural`
- Pronunciation strategy: verified partial phoneme
- Prosody rate: `-12%`
- Client behavior: pre-generated Azure MP3 first, browser Web Speech fallback
- Source of pronunciation context: Hanzi Quiz `tokens[].zhuyin`
- Forced phoneme scope: only character+Zhuyin pairs explicitly validated in the A/B corpus

Why partial instead of full:

- The listening review selected A (partial) for all 26 cases.
- Full phoneme can sound less natural because it suppresses contextual pronunciation behavior such as tone sandhi.
- The production dataset can contain stale or imperfect resolved Zhuyin; a conservative verified-force list prevents a bad source value from being amplified into forced wrong audio.

The A/B corpus remains the regression set. New forced readings should first be added to the Lab and listened to before entering the production force set.
