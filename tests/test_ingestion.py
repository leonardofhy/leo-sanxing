"""Tests for deprecated-column filtering at the ingestion boundary."""

import pytest

from src.config import Config
from src.ingestion import SheetIngester


@pytest.mark.parametrize(
    "name, expected",
    [
        ("以下模塊廢棄", True),
        ("今天完成了哪些？", True),
        ("Email address", True),
        ("今晚預計幾點入睡？", True),
        ("Meta-Awareness Log 填寫反饋和修改建議", True),
        ("今日手機螢幕使用時間", True),
        ("今日使用最多的 App", True),
        ("Column 14", True),
        ("Column 14_2", True),
        ("Column 99", True),
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
            "今天完成了哪些？": "",
            "Column 14": "",
            "Column 14_2": "",
        },
    ]
    filtered = ingester._filter_deprecated_columns(records)
    assert len(filtered) == 1
    assert "Timestamp" in filtered[0]
    assert "今天想記點什麼？" in filtered[0]
    assert "今天的日期" in filtered[0]
    assert "昨晚實際入睡時間" in filtered[0]
    assert "以下模塊廢棄" not in filtered[0]
    assert "今天完成了哪些？" not in filtered[0]
    assert "Column 14" not in filtered[0]
    assert "Column 14_2" not in filtered[0]


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
            "今晚預計幾點入睡？": "",
            "Meta-Awareness Log 填寫反饋和修改建議": "",
            "今日手機螢幕使用時間": "",
            "今日使用最多的 App": "",
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
    assert "今晚預計幾點入睡？" not in out
    assert "Meta-Awareness Log 填寫反饋和修改建議" not in out
    assert "今日手機螢幕使用時間" not in out
    assert "今日使用最多的 App" not in out


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
