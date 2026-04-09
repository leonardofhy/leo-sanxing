from datetime import datetime

from src.analyzer import AnalysisPromptTemplate, EntryFormatter
from src.models import DiaryEntry


def make_entry(ts: str, text: str, **structured):
    dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")
    return DiaryEntry.from_raw(ts, text, dt, **structured)


def test_formatter_shows_diary_text_and_logical_date():
    entries = [
        make_entry("2025-08-21T10:00:00", "學習進步"),
        make_entry("2025-08-22T11:30:00", "保持專注"),
    ]
    out = EntryFormatter.format_entries(entries)
    assert "2025-08-21" in out
    assert "2025-08-22" in out
    assert "學習進步" in out
    assert "保持專注" in out


def test_formatter_includes_structured_fields_when_present():
    entry = make_entry(
        "2025-08-21T10:00:00",
        "睡眠與心情紀錄",
        sleep_bedtime="06:48",
        wake_time="14:07",
        sleep_quality=4,
        mood=5,
        energy=3,
    )
    out = EntryFormatter.format_entries([entry])
    # Exact metadata header line (pins separator, ordering, full-width chars)
    assert "[2025-08-21] 睡眠 06:48→14:07｜睡眠品質 4/5｜心情 5/5｜精力 3/5" in out
    # Values present
    assert "06:48" in out
    assert "14:07" in out
    assert "4/5" in out
    assert "5/5" in out
    assert "3/5" in out
    # Labels present
    assert "睡眠" in out
    assert "心情" in out
    assert "精力" in out
    # Diary text still present
    assert "睡眠與心情紀錄" in out


def test_formatter_omits_absent_structured_fields():
    entry = make_entry("2025-08-21T10:00:00", "僅有心情紀錄", mood=4)
    out = EntryFormatter.format_entries([entry])
    assert "心情 4/5" in out
    # Other labels absent
    assert "睡眠" not in out
    assert "精力" not in out
    assert "睡眠品質" not in out


def test_formatter_shows_partial_sleep_pair():
    """When only bedtime is known, wake side renders as ?."""
    entry = make_entry(
        "2025-08-21T10:00:00",
        "只有入睡時間",
        sleep_bedtime="23:30",
    )
    out = EntryFormatter.format_entries([entry])
    assert "23:30" in out
    assert "?" in out
    assert "睡眠 23:30→?" in out


def test_formatter_falls_back_without_structured_fields():
    entry = make_entry("2025-08-21T10:00:00", "純文字日記")
    out = EntryFormatter.format_entries([entry])
    assert out == "[2025-08-21]\n純文字日記"
    # No metadata separators or labels
    assert "｜" not in out
    assert "睡眠" not in out
    assert "心情" not in out
    assert "精力" not in out


def test_prompt_template_mentions_metadata_anchors():
    """Prompt template should acknowledge structured metadata as factual anchors."""
    template = AnalysisPromptTemplate()
    rendered = template.render(entries_text="[2025-08-21]\n測試")
    # Some indication the LLM should treat structured indicators as factual
    assert "結構化" in rendered or "指標" in rendered
