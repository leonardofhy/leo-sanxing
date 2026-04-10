# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

San-Xing (三省) is an automated meta-awareness & reflective coaching pipeline with dual architecture:

1. **Google Apps Script (GAS) Layer** - Event-driven daily & weekly reporting with scoring and email delivery
2. **Python Insight Engine** - Multi-day log analysis with LLM-powered insights and structured JSON output

The system transforms raw personal logs (behaviors, sleep, reflections) into structured metrics, trends and actionable reflective prompts using Traditional Chinese language coaching.

## Commands

### Python Environment
```bash
# Install dependencies
uv sync

# Run insight generation (last 30 days)
uv run python -m src.cli --config config.local.toml --days 30

# Run all tests
uv run pytest -q

# Code formatting
uv run black src/ tests/

# Linting
uv run flake8 src/ tests/

# Clean up Python cache
uv run pyclean .
```

### Key Python CLI Options
```bash
# Full analysis
uv run python -m src.cli --config config.local.toml --all

# Custom character budget and streaming
uv run python -m src.cli --days 14 --char-budget 10000 --stream

# Export HuggingFace dataset (local)
uv run python -m src.cli --days 7 --export-hf

# Upload to HuggingFace Hub as JSON (set hf_token in config.local.toml or HF_TOKEN env var)
uv run python -m src.cli --days 7 --upload-hf "username/san-xing-diary"

# Upload full raw dataset with all fields (sleep, weight, activities, etc.)
uv run python -m src.cli --upload-hf "username/san-xing-diary" --upload-raw

# Upload as Parquet format instead
uv run python -m src.cli --days 7 --upload-hf "username/san-xing-diary" --hf-format parquet

# Process data for visualization
uv run python -m src.cli --days 30 --process-data data/my-analysis

# Offline mode (reuse snapshot)
export OFFLINE_SNAPSHOT="data/raw/snapshot_latest.json"
export DRY_RUN=true
uv run python -m src.cli --days 7
```

## Architecture

### GAS Event Chain (Daily Reports)
```
REPORT_GENERATION_STARTED → DATA_READ_COMPLETED → SCORES_CALCULATED → 
PROMPT_READY → ANALYSIS_COMPLETED → REPORT_SAVED → REPORT_GENERATION_COMPLETED
```

### Python Processing Flow
```
ingestion → normalization → window selection → LLM analysis → persist artifacts
```

### Key GAS Services
- `ReportOrchestrator.js` - Workflow coordination using EventBus
- `EventBus.js` - Pub/sub messaging with history
- `SheetAdapter.js` - Cached Google Sheets IO with batch operations
- `SchemaService.js` - Versioned header management and field mapping
- `ScoreCalculatorFactory.js` - Pluggable behavior & sleep scoring versions
- `PromptBuilderService.js` - Centralized prompt templates (Traditional Chinese)
- `ApiService.js` - LLM provider abstraction (currently DeepSeek)

### Python Core Modules
- `ingestion.py` - Google Sheets data fetching with header validation
- `normalizer.py` - Entry filtering, timestamp parsing, anomaly detection
- `window.py` - Character-budget constrained context window building
- `analyzer.py` - Traditional Chinese prompt construction & LLM calls
- `persister.py` - JSON artifacts, CSV themes, snapshot management
- `data_processor.py` - Raw data processing for visualization and statistical analysis
- `hf_export.py` - HuggingFace dataset export (local and Hub upload)

## Important Patterns

### Early Morning Rule
Timestamps with hour < 3 belong to previous logical day. This rule is consistently applied across both GAS and Python layers for scoring, aggregation, and windowing.

### Schema Management
- NEVER hardcode sheet headers - always use `SchemaService`
- Add new fields: `SchemaService.addField('MetaLog', key, label, newVersion)`
- Update version: `SchemaService.setVersion('MetaLog', newVersion)`
- Version columns (`behaviorScoreVersion`, `sleepScoreVersion`, `analysisVersion`) preserve audit trail

### Versioning Strategy
- Bump `CONFIG.VERSIONS.*` in GAS when changing scoring formulas
- Bump Python insight pack `meta.version` when changing prompts or analysis logic
- Version IDs should never be reused

### Event-Driven Extensions
- Add new functionality by listening to existing completion events
- Emit new `*_COMPLETED` events after processing
- Avoid modifying core orchestrator unless absolutely necessary
- All failures must emit structured events with `{ phase, error, context }`

## Configuration Files

### Setup Requirements
1. `config.local.toml` - Copy from `config.example.toml` with actual credentials
2. `secrets/service_account.json` - Google service account for Sheets access
3. GAS Script Properties: `DEEPSEEK_API_KEY`, `RECIPIENT_EMAIL`

### Key Configuration Sections
- `CONFIG.VERSIONS` - Version tracking for scoring and analysis
- `CONFIG.BATCH_PROCESS` - Batch generation settings
- `CONFIG.OUTPUT.AUTO_CREATE_SHEETS` - Sheet auto-creation
- `CONFIG.ENABLE_DAILY_EMAIL` / `CONFIG.ENABLE_WEEKLY_EMAIL` - Email delivery

## Output Artifacts

### Python Outputs (`data/` directory)
- `data/raw/entries-<run_id>.json` - Normalized entries used for analysis
- `data/insights/run-<run_id>.json` - Structured insight packs with themes, summaries, reflective questions
- `data/insights/themes-latest.csv` - Rolling theme counts
- `data/raw/snapshot_*.json` - Raw pre-normalization snapshots
- `data/processed*.csv` - Structured data for visualization (mood, sleep, activities)
- `data/processed*-analysis.json` - Analysis-ready data with summary statistics
- `data/hf-dataset/` - HuggingFace dataset format (local export)

### GAS Outputs (Google Sheets)
- `DailyReport` - Daily scoring and LLM analysis
- `WeeklyReport` - Weekly aggregations
- `BehaviorScores` - Score mapping tables

## Exit Codes (Python CLI)

| Code | Meaning |
|------|---------|
| 0    | Success |
| 10   | Missing/invalid inputs or header validation failure |
| 12   | Config validation failure |
| 20   | No valid entries after filtering |
| 30   | Fallback mode (LLM error but artifact produced) |
| 1    | Runtime error |
| 130  | User interrupted (Ctrl+C) |

## Testing & Development

### Running Tests
```bash
# Run all tests
uv run pytest -q

# Specific test files
uv run pytest tests/test_analyzer_prompt.py -v
```

### Common Development Tasks

#### Adding New Score Calculator
```javascript
// 1. Register new version
ScoreCalculatorFactory.registerCalculator('behavior', 'v2', {
  calculate(data) { /* new logic */ },
  getMetadata() { return { version: 'v2' }; }
});

// 2. Activate and bump config version
ScoreCalculatorFactory.setActiveVersion('behavior', 'v2');
CONFIG.VERSIONS.BEHAVIOR_SCORE = 'v2';
```

#### Modifying Python Prompts
- Edit `analyzer.py` `_build_prompt()` method
- Bump `meta.version.prompt` in insight pack output
- Test with `uv run pytest tests/test_analyzer_prompt.py`

#### Adding Sheet Columns
- Use `SchemaService.addField()` with new version
- Update `CONFIG.SCHEMA_VERSIONS`
- Let `SheetAdapter` handle header synchronization

### Debugging Tools
```javascript
// GAS debugging
DevTools.viewEventHistory(30);        // Recent events
detectSchemaChanges();               // Header validation
testMicroservicesArchitecture();     // System health
backtestScores(startDate, endDate);  // Score validation
```

## Language & Internationalization

Current implementation uses Traditional Chinese for prompts and coaching outputs. Prompt templates are centralized in `PromptBuilderService.js` (GAS) and `analyzer.py` (Python) for future internationalization.

## Data Processing & Visualization

### Separate Processing Pipeline
The `DataProcessor` class provides structured data analysis separate from LLM processing:

```python
from src.data_processor import DataProcessor

# Process raw data for visualization
processor = DataProcessor(config)
processor.load_from_snapshot(Path("data/raw/snapshot_latest.json"))
df = processor.process_all()

# Get summary statistics
stats = processor.get_summary_stats()

# Export for visualization tools
processor.export_csv(Path("data/analysis.csv"))
processor.export_analysis_ready(Path("data/analysis.json"))
```

### Processed Data Fields
- **Mood & Energy**: Numeric mood levels, energy ratings
- **Sleep Patterns**: Bedtime, wake time, calculated sleep duration
- **Activities**: Parsed activity lists, positive/negative activity counts
- **Derived Metrics**: Activity balance scores, sleep quality indicators
- **Temporal Data**: Early morning detection, logical date mapping

### Time Format Handling
The data processor handles multiple time formats from Google Sheets:
- **HH:MM:SS format** (e.g., "04:40:00") - Standard time format
- **HHMM format** (e.g., "0420") - 4-digit compact format
- Both formats are validated and normalized to HH:MM for consistency
- Invalid times are filtered out (hours 0-23, minutes 0-59)

### Data Processing Critical Patterns
- **Chinese Column Mapping**: Raw Google Sheets use Chinese headers that are mapped to English field names:
  - `昨晚實際入睡時間` → `sleep_bedtime`
  - `今天實際起床時間` → `wake_time`
  - `昨晚睡眠品質如何？` → `sleep_quality`
- **Time Validation**: Sleep records must pass realistic duration checks (2-16 hours)
- **Cross-midnight Sleep**: Handles sleep that spans midnight correctly for duration calculation
- **Data Completeness**: Distinguishes between missing columns vs. empty values for accurate analytics

### HuggingFace Integration

**Setup:** Add HF token to your config file:
```toml
# In config.local.toml
hf_token = "hf_your_actual_token_here"
```

**Usage:**
```bash
# Local dataset export
uv run python -m src.cli --days 30 --export-hf data/my-dataset

# Upload to HuggingFace Hub (private by default)
uv run python -m src.cli --days 30 --upload-hf "username/diary-dataset"

# Public repository (add --hf-public flag)
uv run python -m src.cli --days 30 --upload-hf "username/diary-dataset" --hf-public
```

## Visualization Dashboard

The project includes an interactive Streamlit dashboard for data exploration and KPI monitoring:

### Dashboard Commands
```bash
# Launch dashboard (recommended)
uv run streamlit run visualization/dashboard.py --server.port 8509

# Alternative launcher
python visualization/launch_dashboard.py

# Run dashboard tests
uv run pytest visualization/tests/ -v
```

### Dashboard Architecture
- **`dashboard.py`** - Main bulletproof dashboard with fallback data loading
- **`analytics/`** - KPI calculations, sleep quality analysis, statistical utilities
- **`components/`** - Reusable UI components (KPI cards, visualizations, drill-down views)
- **`robust_data_loader.py`** - Handles real/synthetic data loading with graceful degradation

### Key Dashboard Features
- **Interactive Raw Data Explorer** - Filter by date range, columns, data quality with CSV export
- **KPI Overview** - Wellbeing Score, Balance Index, Trend Indicator, Sleep Quality (objective & subjective)
- **Statistical Analysis** - Correlation matrices with significance testing
- **Drill-down Views** - Sleep analysis, activity impact, pattern analysis
- **Robust Error Handling** - Always functional dashboard with clear data source indicators

### Dashboard Data Processing
The dashboard uses enhanced data processing that handles multiple time formats:
- **HH:MM:SS format** (e.g., "04:40:00") - Standard format
- **HHMM format** (e.g., "0420") - Compact format from Google Sheets
- **Chinese field mapping** - Automatically maps Chinese column names to English equivalents

### Sleep Quality Analysis
- **Objective Analysis** - Based on sleep timing patterns, duration, regularity, efficiency
- **Subjective Ratings** - User-reported sleep quality scores  
- **Component Scoring** - Duration (40%), Timing (30%), Regularity (20%), Efficiency (10%)
- **Validation** - Processes 100+ sleep records with proper time format handling

## Interactive Data Queries

When the user asks about their recent status (e.g. "我最近睡眠如何？", "這週心情怎麼樣？"), answer by reading the actual data — do NOT guess or rely on memory alone.

### How to Query

1. Read `data/raw/snapshot_latest.json` → get the `file` field (e.g. `snapshot_5396d1c53267248f.json`)
2. Read `data/raw/<that file>` → access the `records` array (list of dicts, one per diary entry)
3. Filter records by `今天的日期` (DD/MM/YYYY format) for the requested date range
4. Parse the relevant fields and compute the answer (averages, trends, outliers)

### Snapshot Field Reference

| Field (Chinese header) | Type | Notes |
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

### Time Parsing Rules
- HHMM format: `"0712"` → 07:12
- HH:MM format: `"07:12"` → 07:12
- Hour < 3 in bedtime typically means sleeping after midnight (early morning rule)

### Also Available
- Latest LLM insight pack: `data/insights/run-<latest>.json` — contains dailySummaries, themes, reflectiveQuestion, anomalies, hiddenSignals, emotionalIndicators
- Sort insight files by name (they embed timestamps) to find the most recent

### Auto-Recording During Conversations
When chatting about diary data, automatically save valuable observations to project memory if they meet these criteria:
- Non-obvious patterns the user confirms or finds surprising (e.g. "原來我週三都睡最差")
- User-stated goals or intentions about behavior change (e.g. "我想試試12點前睡")
- Corrections to how data should be interpreted (e.g. "那天的數據不準，我忘記填了")

Do NOT save raw statistics or ephemeral query results — those can always be recomputed from the snapshot.

## Security Notes

- Keep credentials in `secrets/` directory (git-ignored)
- Personal data is transmitted to third-party LLM providers
- Service account JSON and API keys must not be committed to version control
- Review provider data policies before deployment
- HuggingFace datasets are private by default; use `--hf-public` flag for public repos
- HF tokens should be added to config.local.toml (git-ignored)