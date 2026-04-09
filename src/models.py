"""Data models for diary entries and insights"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta, timezone
from typing import List, Dict, Any, Optional
import hashlib
import json


@dataclass
class DiaryEntry:
    """Normalized diary entry"""
    raw_timestamp: str
    timestamp: datetime
    ts_epoch: int
    logical_date: date
    diary_text: str
    entry_length: int
    entry_id: str
    is_early_morning: bool = False
    sleep_bedtime: Optional[str] = None   # normalized HH:MM, e.g. "06:48"
    wake_time: Optional[str] = None       # normalized HH:MM
    sleep_quality: Optional[int] = None   # 1-5
    mood: Optional[int] = None            # 1-5
    energy: Optional[int] = None          # 1-5

    @classmethod
    def from_raw(
        cls,
        raw_timestamp: str,
        diary_text: str,
        parsed_dt: datetime,
        explicit_logical_date: Optional[date] = None,
        sleep_bedtime: Optional[str] = None,
        wake_time: Optional[str] = None,
        sleep_quality: Optional[int] = None,
        mood: Optional[int] = None,
        energy: Optional[int] = None,
    ) -> "DiaryEntry":
        """Create entry with computed fields.

        ``is_early_morning`` always reflects an objective fact about the
        timestamp (hour < 3). ``logical_date`` prefers ``explicit_logical_date``
        when provided (source of truth from the user-filled 今天的日期 column)
        and otherwise falls back to the early-morning adjustment rule.

        Structured fields (sleep_bedtime, wake_time, sleep_quality, mood,
        energy) are optional and default to None when absent from source data.
        """
        # Early morning flag reflects the timestamp, independent of logical_date.
        is_early_morning = parsed_dt.hour < 3
        if explicit_logical_date is not None:
            logical_date = explicit_logical_date
        else:
            logical_date = (
                parsed_dt.date()
                if not is_early_morning
                else (parsed_dt - timedelta(days=1)).date()
            )

        # Generate stable ID
        id_source = f"{raw_timestamp}{diary_text[:64]}"
        entry_id = hashlib.sha1(id_source.encode()).hexdigest()

        return cls(
            raw_timestamp=raw_timestamp,
            timestamp=parsed_dt,
            ts_epoch=int(parsed_dt.timestamp() * 1000),
            logical_date=logical_date,
            diary_text=diary_text.strip(),
            entry_length=len(diary_text.strip()),
            entry_id=entry_id,
            is_early_morning=is_early_morning,
            sleep_bedtime=sleep_bedtime,
            wake_time=wake_time,
            sleep_quality=sleep_quality,
            mood=mood,
            energy=energy,
        )


@dataclass
class DailySummary:
    """Single day summary"""
    date: str
    summary: str


@dataclass
class Theme:
    """Extracted theme with support count"""
    label: str
    support: int


@dataclass
class InsightPack:
    """Complete analysis output"""
    meta: Dict[str, Any]
    dailySummaries: List[DailySummary] = field(default_factory=list)
    themes: List[Theme] = field(default_factory=list)
    reflectiveQuestion: str = "請回顧今天的一件小事，它代表了你想成為的人嗎?"
    anomalies: List[str] = field(default_factory=list)
    hiddenSignals: List[str] = field(default_factory=list)
    emotionalIndicators: List[Dict] = field(default_factory=list)
    
    def to_json(self) -> str:
        """Serialize to JSON string"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "meta": self.meta,
            "dailySummaries": [{"date": ds.date, "summary": ds.summary} 
                              for ds in self.dailySummaries],
            "themes": [{"label": t.label, "support": t.support} 
                      for t in self.themes],
            "reflectiveQuestion": self.reflectiveQuestion,
            "anomalies": self.anomalies,
            "hiddenSignals": self.hiddenSignals,
            "emotionalIndicators": self.emotionalIndicators
        }
    
    @classmethod
    def create_fallback(cls, run_id: str, version: Dict, entries_count: int = 0) -> "InsightPack":
        """Create minimal fallback pack when LLM fails"""
        return cls(
            meta={
                "run_id": run_id,
                "version": version,
                "entriesAnalyzed": entries_count,
                "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "mode": "fallback"
            }
        )
