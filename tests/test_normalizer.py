from datetime import date

from src.config import Config
from src.normalizer import EntryNormalizer


def test_normalizer_basic():
    config = Config()
    normalizer = EntryNormalizer(config)
    records = [
        {config.TIMESTAMP_COLUMN: "2025-08-23T10:15:00", config.DIARY_COLUMN: "學習專注與計畫"},
        {config.TIMESTAMP_COLUMN: "2025-08-23T00:45:00", config.DIARY_COLUMN: "凌晨反思"},
        {config.TIMESTAMP_COLUMN: "bad-ts", config.DIARY_COLUMN: "無效"},  # malformed timestamp should be skipped
        {config.TIMESTAMP_COLUMN: "2025-08-22T22:00:00", config.DIARY_COLUMN: "放鬆休"},  # ensure length >= 3
    ]
    entries = normalizer.normalize(records)
    assert len(entries) == 3
    # Ensure ordering ascending
    assert entries[0].raw_timestamp == "2025-08-22T22:00:00"
    # Early morning adjustment
    early_entry = [e for e in entries if e.raw_timestamp == "2025-08-23T00:45:00"][0]
    assert early_entry.is_early_morning is True


def _single_entry(config: Config, record: dict):
    normalizer = EntryNormalizer(config)
    entries = normalizer.normalize([record])
    assert len(entries) == 1
    return entries[0]


def test_explicit_logical_date_beats_early_morning_rule_post_3am():
    """User fills out yesterday's diary at 04:26 (not early morning)."""
    config = Config()
    record = {
        config.TIMESTAMP_COLUMN: "2026-04-04T04:26:00",
        config.DIARY_COLUMN: "補寫昨天的日記",
        config.LOGICAL_DATE_COLUMN: "03/04/2026",
    }
    entry = _single_entry(config, record)
    assert entry.logical_date == date(2026, 4, 3)
    # hour=4 is NOT early morning
    assert entry.is_early_morning is False


def test_explicit_logical_date_with_early_morning_agreeing():
    """Explicit date matches what early-morning rule would produce, but is_early_morning flag still reflects timestamp."""
    config = Config()
    record = {
        config.TIMESTAMP_COLUMN: "2026-04-04T02:00:00",
        config.DIARY_COLUMN: "凌晨寫日記",
        config.LOGICAL_DATE_COLUMN: "03/04/2026",
    }
    entry = _single_entry(config, record)
    assert entry.logical_date == date(2026, 4, 3)
    # hour=2 IS early morning; flag is independent of logical_date source
    assert entry.is_early_morning is True


def test_explicit_logical_date_overrides_early_morning_rule():
    """Explicit date wins even when it disagrees with the early-morning rule."""
    config = Config()
    record = {
        config.TIMESTAMP_COLUMN: "2026-04-04T02:00:00",
        config.DIARY_COLUMN: "凌晨寫今天的日記",
        config.LOGICAL_DATE_COLUMN: "04/04/2026",
    }
    entry = _single_entry(config, record)
    # Explicit wins — rule would have said 04-03
    assert entry.logical_date == date(2026, 4, 4)
    assert entry.is_early_morning is True


def test_missing_logical_date_column_falls_back():
    """Record without 今天的日期 key should still work via timestamp rule."""
    config = Config()
    record = {
        config.TIMESTAMP_COLUMN: "2026-04-04T10:15:00",
        config.DIARY_COLUMN: "正常日記",
    }
    entry = _single_entry(config, record)
    # Post-3am, no early morning → logical_date is the timestamp date
    assert entry.logical_date == date(2026, 4, 4)
    assert entry.is_early_morning is False


def test_invalid_logical_date_falls_back():
    """Garbage in the logical date column should fall back without raising."""
    config = Config()
    record = {
        config.TIMESTAMP_COLUMN: "2026-04-04T10:15:00",
        config.DIARY_COLUMN: "正常日記",
        config.LOGICAL_DATE_COLUMN: "garbage",
    }
    entry = _single_entry(config, record)
    assert entry.logical_date == date(2026, 4, 4)
    assert entry.is_early_morning is False
