"""Entry normalization and filtering"""

from typing import List, Optional
from datetime import datetime, date
from .models import DiaryEntry
from .config import Config
from .logger import get_logger

logger = get_logger(__name__)


class EntryNormalizer:
    """Normalize and filter diary entries"""
    
    def __init__(self, config: Config):
        self.config = config
        
    def normalize(self, records: List[dict]) -> List[DiaryEntry]:
        """
        Parse timestamps, filter invalid entries, create DiaryEntry objects
        """
        entries = []
        skipped = 0
        
        for record in records:
            entry = self._process_record(record)
            if entry:
                entries.append(entry)
            else:
                skipped += 1
        
        logger.info("Normalized %d entries, skipped %d", len(entries), skipped)
        
        # Sort by timestamp
        entries.sort(key=lambda e: e.timestamp)
        
        return entries
    
    def _process_record(self, record: dict) -> Optional[DiaryEntry]:
        """Process single record into DiaryEntry or None if invalid"""
        raw_timestamp = str(record.get(self.config.TIMESTAMP_COLUMN, "")).strip()
        diary_text = str(record.get(self.config.DIARY_COLUMN, "")).strip()

        # Skip if diary too short
        if len(diary_text) < self.config.MIN_DIARY_LENGTH:
            return None

        # Parse timestamp
        parsed_dt = self._parse_timestamp(raw_timestamp)
        if not parsed_dt:
            logger.warning("Failed to parse timestamp: %s", raw_timestamp)
            return None

        # Optional user-provided logical date (source of truth when present)
        raw_logical_date = str(record.get(self.config.LOGICAL_DATE_COLUMN, "")).strip()
        explicit_logical_date = self._parse_logical_date(raw_logical_date)

        return DiaryEntry.from_raw(
            raw_timestamp,
            diary_text,
            parsed_dt,
            explicit_logical_date=explicit_logical_date,
        )

    def _parse_timestamp(self, raw: str) -> Optional[datetime]:
        """Try multiple timestamp formats"""
        for pattern in self.config.TIMESTAMP_PATTERNS:
            try:
                return datetime.strptime(raw, pattern)
            except ValueError:
                continue
        return None

    def _parse_logical_date(self, raw: str) -> Optional[date]:
        """Parse the user-filled 今天的日期 column as DD/MM/YYYY.

        Returns None when the field is missing, empty, or unparseable. This
        is expected for older rows, so we log at debug level rather than
        warning to avoid noisy logs.
        """
        if not raw:
            logger.debug("Logical date column missing or empty; falling back to timestamp rule")
            return None
        try:
            return datetime.strptime(raw, "%d/%m/%Y").date()
        except ValueError:
            logger.debug("Failed to parse logical date %r; falling back to timestamp rule", raw)
            return None
    
    def detect_anomalies(self, entries: List[DiaryEntry]) -> List[str]:
        """Detect gaps and length spikes"""
        anomalies = []
        
        if len(entries) < 2:
            return anomalies
            
        # Gap detection
        for i in range(1, len(entries)):
            gap_days = (entries[i].logical_date - entries[i-1].logical_date).days
            if gap_days > 3:
                anomalies.append(f"{gap_days}-day gap before {entries[i].logical_date}")
        
        # Length spike detection (need 30+ entries)
        if len(entries) >= 30:
            recent_30 = entries[-30:]
            lengths = [e.entry_length for e in recent_30]
            mean_len = sum(lengths) / len(lengths)
            std_dev = (sum((x - mean_len) ** 2 for x in lengths) / len(lengths)) ** 0.5
            
            for entry in entries[-5:]:  # Check last 5 entries
                if entry.entry_length > mean_len + 2 * std_dev:
                    anomalies.append(f"Length spike on {entry.logical_date}: {entry.entry_length} chars")
        
        return anomalies
