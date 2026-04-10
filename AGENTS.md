# AGENTS.md

Cross-tool instructions for AI assistants (Claude Code, Gemini CLI, etc.) working in this repo.

## Interactive Data Queries

When the user asks about their recent status (e.g. "我最近睡眠如何？", "這週心情怎麼樣？"), answer by reading the actual data.

### How to Query

1. Read `data/raw/snapshot_latest.json` → get the `file` field
2. Read `data/raw/<that file>` → access the `records` array
3. Filter records by `今天的日期` (DD/MM/YYYY format) for the requested date range
4. Parse the relevant fields and compute the answer (averages, trends, outliers)

### Snapshot Field Reference

| Field | Type | Notes |
|---|---|---|
| `Timestamp` | datetime string | Form submission time |
| `今天的日期` | DD/MM/YYYY | User-declared diary date (source of truth) |
| `昨晚實際入睡時間` | HHMM or HH:MM | Sleep bedtime |
| `今天實際起床時間` | HHMM or HH:MM | Wake time |
| `昨晚睡眠品質如何？` | 1-5 | Subjective sleep quality |
| `今日整體心情感受` | 1-5 | Mood rating |
| `今日整體精力水平如何？` | 1-5 | Energy rating |
| `今天想記點什麼？` | free text | Diary entry |
| `今天完成了哪些？` | free text | Activities list |
| `體重紀錄` | number | Weight (kg) |

### Time Parsing
- HHMM format: `"0712"` → 07:12
- HH:MM format: `"07:12"` → 07:12
- Bedtime hour < 3 typically means sleeping after midnight

### Data Sources
- Raw records: `data/raw/snapshot_latest.json` → points to full snapshot
- LLM insight packs: `data/insights/run-*.json` (sort by filename for latest) — contains dailySummaries, themes, reflectiveQuestion, anomalies, hiddenSignals, emotionalIndicators

### Response Language
Respond in the same language the user uses. Data labels are in Traditional Chinese.

### Auto-Recording
When chatting about diary data, save non-obvious observations the user confirms or finds surprising to a project-level memory or notes system. Do NOT save raw statistics — those can be recomputed.
