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


def test_normalizer_parses_hhmm_format():
    """4-digit compact HHMM format should be normalized to HH:MM."""
    config = Config()
    record = {
        config.TIMESTAMP_COLUMN: "2026-04-04T10:15:00",
        config.DIARY_COLUMN: "睡眠測試",
        config.SLEEP_BEDTIME_COLUMN: "0420",
    }
    entry = _single_entry(config, record)
    assert entry.sleep_bedtime == "04:20"


def test_normalizer_parses_hhmmss_format():
    """HH:MM:SS format should be normalized to HH:MM."""
    config = Config()
    record = {
        config.TIMESTAMP_COLUMN: "2026-04-04T10:15:00",
        config.DIARY_COLUMN: "起床測試",
        config.WAKE_TIME_COLUMN: "04:40:00",
    }
    entry = _single_entry(config, record)
    assert entry.wake_time == "04:40"


def test_normalizer_rejects_invalid_time():
    """Out-of-range time value should result in None."""
    config = Config()
    record = {
        config.TIMESTAMP_COLUMN: "2026-04-04T10:15:00",
        config.DIARY_COLUMN: "無效時間",
        config.SLEEP_BEDTIME_COLUMN: "25:99",
    }
    entry = _single_entry(config, record)
    assert entry.sleep_bedtime is None


def test_normalizer_parses_rating_fields():
    """Mood, energy, and sleep quality should parse as integers in 1-5."""
    config = Config()
    record = {
        config.TIMESTAMP_COLUMN: "2026-04-04T10:15:00",
        config.DIARY_COLUMN: "評分測試",
        config.SLEEP_QUALITY_COLUMN: "4",
        config.MOOD_COLUMN: "5",
        config.ENERGY_COLUMN: "3",
    }
    entry = _single_entry(config, record)
    assert entry.sleep_quality == 4
    assert entry.mood == 5
    assert entry.energy == 3


def test_normalizer_rejects_out_of_range_rating():
    """Rating outside 1-5 range should become None."""
    config = Config()
    record = {
        config.TIMESTAMP_COLUMN: "2026-04-04T10:15:00",
        config.DIARY_COLUMN: "越界評分",
        config.MOOD_COLUMN: "7",
    }
    entry = _single_entry(config, record)
    assert entry.mood is None


def test_normalizer_structured_fields_default_none_when_absent():
    """Records without structured columns yield None for those fields."""
    config = Config()
    record = {
        config.TIMESTAMP_COLUMN: "2026-04-04T10:15:00",
        config.DIARY_COLUMN: "無結構化資料",
    }
    entry = _single_entry(config, record)
    assert entry.sleep_bedtime is None
    assert entry.wake_time is None
    assert entry.sleep_quality is None
    assert entry.mood is None
    assert entry.energy is None
