"""Tests for deprecated-column filtering at the ingestion boundary."""

from datetime import date

import pytest

from src.analyzer import EntryFormatter
from src.config import Config
from src.ingestion import SheetIngester
from src.normalizer import EntryNormalizer


@pytest.mark.parametrize(
    "name, expected",
    [
        # Genuinely deprecated (no downstream consumer)
        ("以下模塊廢棄", True),
        ("Email address", True),
        ("Meta-Awareness Log 填寫反饋和修改建議", True),
        # Auto-dedup artifact pattern
        ("Column 14", True),
        ("Column 14_2", True),
        ("Column 99", True),
        # Restored: consumed by data_processor.py for activity/screen-time KPIs
        ("今天完成了哪些？", False),
        ("今晚預計幾點入睡？", False),
        ("今日手機螢幕使用時間", False),
        ("今日使用最多的 App", False),
        # Core fields never deprecated
        ("Timestamp", False),
        ("今天想記點什麼？", False),
        ("今天的日期", False),
        ("昨晚實際入睡時間", False),
        ("Column", False),  # not a numbered artifact
        ("Column A", False),
    ],
)
def test_is_deprecated_column(name, expected):
    config = Config()
    assert config.is_deprecated_column(name) is expected


def test_filter_deprecated_columns_strips_known_and_artifact_keys():
    config = Config()
    ingester = SheetIngester(config)
    records = [
        {
            "Timestamp": "2026-04-04T10:00:00",
            "今天想記點什麼？": "test diary",
            "今天的日期": "04/04/2026",
            "昨晚實際入睡時間": "0420",
            "以下模塊廢棄": "",
            "Email address": "user@example.com",
            "Meta-Awareness Log 填寫反饋和修改建議": "",
            "今天完成了哪些？": "讀書",
            "今晚預計幾點入睡？": "2300",
            "今日手機螢幕使用時間": "5h",
            "今日使用最多的 App": "X",
            "Column 14": "",
            "Column 14_2": "",
        },
    ]
    filtered = ingester._filter_deprecated_columns(records)
    assert len(filtered) == 1
    out = filtered[0]
    # Core fields preserved
    assert "Timestamp" in out
    assert "今天想記點什麼？" in out
    assert "今天的日期" in out
    assert "昨晚實際入睡時間" in out
    # Genuinely-deprecated columns dropped
    assert "以下模塊廢棄" not in out
    assert "Email address" not in out
    assert "Meta-Awareness Log 填寫反饋和修改建議" not in out
    # Auto-dedup artifacts dropped
    assert "Column 14" not in out
    assert "Column 14_2" not in out
    # Restored columns MUST survive so data_processor can read them
    assert out["今天完成了哪些？"] == "讀書"
    assert out["今晚預計幾點入睡？"] == "2300"
    assert out["今日手機螢幕使用時間"] == "5h"
    assert out["今日使用最多的 App"] == "X"


def test_filter_deprecated_columns_preserves_structured_fields():
    config = Config()
    ingester = SheetIngester(config)
    records = [
        {
            config.TIMESTAMP_COLUMN: "2026-04-04T10:00:00",
            config.DIARY_COLUMN: "diary text",
            config.LOGICAL_DATE_COLUMN: "04/04/2026",
            config.SLEEP_BEDTIME_COLUMN: "0420",
            config.WAKE_TIME_COLUMN: "08:30:00",
            config.SLEEP_QUALITY_COLUMN: "7",
            config.MOOD_COLUMN: "6",
            config.ENERGY_COLUMN: "5",
            "Email address": "user@example.com",
            "Meta-Awareness Log 填寫反饋和修改建議": "",
        },
    ]
    filtered = ingester._filter_deprecated_columns(records)
    assert len(filtered) == 1
    out = filtered[0]
    # Required fields preserved
    assert out[config.TIMESTAMP_COLUMN] == "2026-04-04T10:00:00"
    assert out[config.DIARY_COLUMN] == "diary text"
    assert out[config.LOGICAL_DATE_COLUMN] == "04/04/2026"
    # Task 2 structured fields preserved
    assert out[config.SLEEP_BEDTIME_COLUMN] == "0420"
    assert out[config.WAKE_TIME_COLUMN] == "08:30:00"
    assert out[config.SLEEP_QUALITY_COLUMN] == "7"
    assert out[config.MOOD_COLUMN] == "6"
    assert out[config.ENERGY_COLUMN] == "5"
    # Deprecated fields dropped
    assert "Email address" not in out
    assert "Meta-Awareness Log 填寫反饋和修改建議" not in out


def test_filter_deprecated_columns_preserves_row_count():
    config = Config()
    ingester = SheetIngester(config)
    records = [
        {
            "Timestamp": f"2026-04-{i:02d}T10:00:00",
            "今天想記點什麼？": f"entry {i}",
            "以下模塊廢棄": "",
            "Column 14": "",
        }
        for i in range(1, 6)
    ]
    filtered = ingester._filter_deprecated_columns(records)
    assert len(filtered) == 5
    for i, out in enumerate(filtered, start=1):
        assert out["Timestamp"] == f"2026-04-{i:02d}T10:00:00"
        assert out["今天想記點什麼？"] == f"entry {i}"
        assert "以下模塊廢棄" not in out
        assert "Column 14" not in out


def test_filter_deprecated_columns_empty_input():
    config = Config()
    ingester = SheetIngester(config)
    assert ingester._filter_deprecated_columns([]) == []


def test_filter_deprecated_columns_no_deprecated_present_passthrough():
    config = Config()
    ingester = SheetIngester(config)
    records = [
        {
            "Timestamp": "2026-04-04T10:00:00",
            "今天想記點什麼？": "diary text",
            "今天的日期": "04/04/2026",
        },
    ]
    filtered = ingester._filter_deprecated_columns(records)
    # Behaviorally equivalent: same rows, same keys, same values
    assert filtered == records
    # Returns the same list object when nothing needs dropping
    assert filtered is records


def test_filter_deprecated_columns_regex_edge_cases():
    config = Config()
    ingester = SheetIngester(config)
    records = [
        {
            "Timestamp": "2026-04-04T10:00:00",
            "Column 1": "drop-me",
            "Column 99_3": "drop-me-too",
            "Column": "keep-me",
            "Column A": "keep-me-too",
            "ColumnFoo": "keep-me-three",
        },
    ]
    filtered = ingester._filter_deprecated_columns(records)
    assert len(filtered) == 1
    out = filtered[0]
    assert "Timestamp" in out
    assert "Column 1" not in out
    assert "Column 99_3" not in out
    assert out["Column"] == "keep-me"
    assert out["Column A"] == "keep-me-too"
    assert out["ColumnFoo"] == "keep-me-three"


def test_end_to_end_ingest_normalize_format_pipeline():
    """Cross-task integration: filter -> normalize -> format_entries.

    Covers all three refactor tasks simultaneously:
    - Task 1 (ingestion filter): drops only genuinely-deprecated columns and
      preserves the 4 columns that data_processor.py still consumes.
    - Task 2 (structured fields): normalizer parses bedtime / wake / quality /
      mood / energy and logical_date from the dedicated column.
    - Task 3 (formatter): metadata header line precedes the diary text when
      structured fields are populated.
    """
    config = Config()
    ingester = SheetIngester(config)
    normalizer = EntryNormalizer(config)

    diary_text = "今天去散步讀書，心情不錯。"  # comfortably above MIN_DIARY_LENGTH
    raw_record = {
        # Core required fields (DD/MM/YYYY matches TIMESTAMP_PATTERNS)
        "Timestamp": "04/04/2026 04:26:38",
        "今天想記點什麼？": diary_text,
        # Disagrees with the timestamp's date intentionally: the user-filled
        # logical date column is the source of truth.
        "今天的日期": "03/04/2026",
        # Task 2 structured fields (all populated)
        "昨晚實際入睡時間": "0648",
        "今天實際起床時間": "1254",
        "昨晚睡眠品質如何？": "4",
        "今日整體心情感受": "5",
        "今日整體精力水平如何？": "3",
        # Genuinely-deprecated columns (empty)
        "以下模塊廢棄": "",
        "Email address": "",
        "Meta-Awareness Log 填寫反饋和修改建議": "",
        # Auto-dedup artifact
        "Column 14": "",
        # Restored columns (must survive filter for data_processor)
        "今天完成了哪些？": "讀書,運動",
        "今晚預計幾點入睡？": "2300",
        "今日手機螢幕使用時間": "5h",
        "今日使用最多的 App": "X",
    }

    # 1. Filter
    filtered = ingester._filter_deprecated_columns([raw_record])
    assert len(filtered) == 1
    out = filtered[0]

    # Dropped
    assert "以下模塊廢棄" not in out
    assert "Email address" not in out
    assert "Meta-Awareness Log 填寫反饋和修改建議" not in out
    assert "Column 14" not in out

    # Preserved: 4 restored columns (so data_processor can still read them)
    assert out["今天完成了哪些？"] == "讀書,運動"
    assert out["今晚預計幾點入睡？"] == "2300"
    assert out["今日手機螢幕使用時間"] == "5h"
    assert out["今日使用最多的 App"] == "X"

    # 2. Normalize
    entries = normalizer.normalize(filtered)
    assert len(entries) == 1
    entry = entries[0]

    # logical_date comes from 今天的日期 (03/04), not the timestamp (04/04)
    assert entry.logical_date == date(2026, 4, 3)
    # is_early_morning is an objective fact about the timestamp hour (4 >= 3)
    assert entry.is_early_morning is False
    # Structured fields parsed
    assert entry.sleep_bedtime == "06:48"
    assert entry.wake_time == "12:54"
    assert entry.sleep_quality == 4
    assert entry.mood == 5
    assert entry.energy == 3
    assert entry.diary_text == diary_text

    # 3. Format
    formatted = EntryFormatter.format_entries(entries)
    assert "睡眠 06:48→12:54｜睡眠品質 4/5｜心情 5/5｜精力 3/5" in formatted
    assert diary_text in formatted
