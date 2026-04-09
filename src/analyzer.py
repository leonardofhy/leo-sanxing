"""Enhanced LLM analysis module with improved structure"""

import json
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Protocol, Any, Generator
from datetime import datetime, timezone
from enum import Enum
import requests
from contextlib import contextmanager

from .models import DiaryEntry, InsightPack, DailySummary, Theme
from .config import Config
from .logger import get_logger

logger = get_logger(__name__)


# ============================================================================
# Enums and Constants
# ============================================================================


class AnalysisMode(Enum):
    """Analysis modes for different levels of detail"""

    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class LLMProvider(Enum):
    """Supported LLM providers"""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    CUSTOM = "custom"


# ============================================================================
# Data Classes for Better Type Safety
# ============================================================================


@dataclass
class LLMRequest:
    """Encapsulates an LLM request"""

    prompt: str
    system_prompt: str
    temperature: float = 0.7
    response_format: Dict[str, str] = field(default_factory=lambda: {"type": "json_object"})
    stream: bool = False
    max_tokens: Optional[int] = None


@dataclass
class LLMResponse:
    """Encapsulates an LLM response"""

    content: str
    raw_response: Dict[str, Any]
    model: str
    usage: Optional[Dict[str, int]] = None
    duration_ms: Optional[int] = None


# ============================================================================
# Prompt Management
# ============================================================================


class PromptTemplate(ABC):
    """Abstract base for prompt templates"""

    @abstractmethod
    def render(self, **kwargs) -> str:
        """Render the prompt with given context"""
        pass


class AnalysisPromptTemplate(PromptTemplate):
    """Template for diary analysis prompts"""

    def __init__(self, template: Optional[str] = None):
        self.template = template or self._default_template()

    def render(self, entries_text: str, **kwargs) -> str:
        """Render the analysis prompt"""
        return self.template.format(entries_text=entries_text, **kwargs)

    @staticmethod
    def _default_template() -> str:
        return """你是一位精準、沉著且具同理心的個人成長教練，正在分析多日的日誌內容。
請「只輸出」一個有效 JSON，不要加入解釋、前後綴或 Markdown。使用下列固定英文字鍵 (維持英文，不可翻譯)：
- dailySummaries: 陣列，元素格式 {{date, summary}}，summary 為該日期的精煉重點 (不超過 60 中文字)。
- themes: 陣列，元素格式 {{label, support}}，最多 5 個；label 需 ≤12 個全形字，代表跨日出現的核心主題；support 為整數 (出現/支持度)。
- reflectiveQuestion: 一個引導式、開放式反思問題（避免是/否回答，聚焦模式 / 習慣 / 意義）。
- anomalies: （可選）字串陣列，指出不尋常或與過往模式偏離的觀察。
- hiddenSignals: （可選）字串陣列，指出尚未被使用者明確寫出的潛在趨勢或情緒信號。
- emotionalIndicators: （可選）字串陣列，聚焦情緒調節、壓力、動機等微妙指標。

分析重點指引：
1. 抽取可行洞察：聚焦行為模式、能量變化、情緒調節、價值一致性。
2. 避免空泛語句（如：保持加油、繼續努力）；輸出具體、觀察式描述。
3. 不捏造未出現的事件；允許指出資料不足處。
4. 若日誌含凌晨（<03:00）內容，仍視為其邏輯日期。
5. reflectiveQuestion 要能引導下一步探索，而非重述既有狀態。
6. 每則日誌的日期行後可能附帶結構化指標（睡眠時段、睡眠品質、心情、精力，皆為使用者當日自評）。請將這些數值視為客觀事實錨點，用以對照文字敘述，不得虛構不存在的數值。

使用者日誌內容 (原文可能混合語言)：
{entries_text}

請執行：
- 先整體掃描 → 建立主題與信號 → 逐日濃縮 → 生成反思問題。
僅輸出最終 JSON，無任何多餘文字。"""


class PromptManager:
    """Manages different prompt templates"""

    def __init__(self):
        self.templates: Dict[str, PromptTemplate] = {
            "analysis": AnalysisPromptTemplate(),
        }
        self.system_prompts: Dict[str, str] = {
            "default": (
                "你是一位精準且具結構化思維的個人成長教練。"
                "所有回覆必須是有效 JSON（UTF-8），不得含有額外文字。"
                "所有輸出的中文應該都以繁體中文呈現。"
            )
        }

    def get_template(self, name: str) -> PromptTemplate:
        """Get a prompt template by name"""
        if name not in self.templates:
            raise ValueError(f"Unknown template: {name}")
        return self.templates[name]

    def get_system_prompt(self, name: str = "default") -> str:
        """Get a system prompt by name"""
        return self.system_prompts.get(name, self.system_prompts["default"])

    def register_template(self, name: str, template: PromptTemplate):
        """Register a new prompt template"""
        self.templates[name] = template


# ============================================================================
# LLM Client Interface
# ============================================================================


class LLMClient(Protocol):
    """Protocol for LLM clients"""

    def call(self, request: LLMRequest) -> LLMResponse:
        """Make an LLM API call"""
        ...

    def call_streaming(self, request: LLMRequest) -> Generator[str, None, str]:
        """Make a streaming LLM API call"""
        ...


# ============================================================================
# HTTP Client with Better Error Handling
# ============================================================================


class HTTPLLMClient:
    """HTTP client for LLM API calls"""

    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(self._create_headers())

    def _create_headers(self) -> Dict[str, str]:
        """Create HTTP headers for API requests"""
        return {
            "Authorization": f"Bearer {self.config.LLM_API_KEY}",
            "Content-Type": "application/json",
        }

    def call(self, request: LLMRequest) -> LLMResponse:
        """Make a non-streaming API call"""
        payload = self._build_payload(request)

        start_time = time.time()
        response = self.session.post(
            self.config.LLM_ENDPOINT, json=payload, timeout=self.config.LLM_TIMEOUT
        )
        duration_ms = int((time.time() - start_time) * 1000)

        response.raise_for_status()
        data = response.json()

        content = data["choices"][0]["message"]["content"]

        return LLMResponse(
            content=content,
            raw_response=data,
            model=request.system_prompt,
            usage=data.get("usage"),
            duration_ms=duration_ms,
        )

    def call_streaming(self, request: LLMRequest) -> Generator[str, None, str]:
        """Make a streaming API call"""
        payload = self._build_payload(request)
        payload["stream"] = True

        with self.session.post(
            self.config.LLM_ENDPOINT, json=payload, timeout=self.config.LLM_TIMEOUT, stream=True
        ) as response:
            response.raise_for_status()

            collected = []
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue

                if line.startswith("data:"):
                    chunk = line[len("data:") :].strip()
                    if chunk == "[DONE]":
                        break

                    try:
                        j = json.loads(chunk)
                        delta = j.get("choices", [{}])[0].get("delta", {})
                        if "content" in delta:
                            token = delta["content"]
                            collected.append(token)
                            yield token
                    except json.JSONDecodeError:
                        # Some providers might emit plain text
                        collected.append(chunk)
                        yield chunk

            return "".join(collected)

    def _build_payload(self, request: LLMRequest) -> Dict:
        """Build API payload from request"""
        payload = {
            "model": self.config.LLM_MODEL,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.prompt},
            ],
            "temperature": request.temperature,
        }

        if request.response_format:
            payload["response_format"] = request.response_format

        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        return payload

    def close(self):
        """Close the session"""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ============================================================================
# Response Parser with Validation
# ============================================================================


class ResponseParser:
    """Parses and validates LLM responses"""

    @staticmethod
    def extract_json(content: str) -> Dict:
        """Extract JSON from potentially messy LLM output"""
        # Try direct parse first
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try to find JSON boundaries
        json_start = content.find("{")
        json_end = content.rfind("}")

        if json_start == -1 or json_end == -1:
            raise ValueError("No JSON object detected in content")

        json_str = content[json_start : json_end + 1]
        return json.loads(json_str)

    @staticmethod
    def validate_analysis_response(data: Dict) -> bool:
        """Validate that response has required fields"""
        required_fields = ["dailySummaries", "themes", "reflectiveQuestion"]

        for field in required_fields:
            if field not in data:
                logger.warning(f"Missing required field: {field}")
                return False

        # Validate dailySummaries structure
        if not isinstance(data["dailySummaries"], list):
            return False

        for summary in data["dailySummaries"]:
            if not all(k in summary for k in ["date", "summary"]):
                return False

        # Validate themes structure
        if not isinstance(data["themes"], list):
            return False

        for theme in data["themes"]:
            if not all(k in theme for k in ["label", "support"]):
                return False

        return True

    def parse_analysis_response(
        self, data: Dict, run_id: str, entries_count: int, version: str
    ) -> InsightPack:
        """Parse validated response into InsightPack"""

        meta = {
            "run_id": run_id,
            "version": version,
            "entriesAnalyzed": entries_count,
            "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

        daily_summaries = [
            DailySummary(date=ds["date"], summary=ds["summary"])
            for ds in data.get("dailySummaries", [])
        ]

        themes = [
            Theme(label=t.get("label"), support=int(t.get("support", 0)))
            for t in data.get("themes", [])
        ]

        return InsightPack(
            meta=meta,
            dailySummaries=daily_summaries,
            themes=themes,
            reflectiveQuestion=data.get(
                "reflectiveQuestion", "請回顧今天的一件小事，它代表了你想成為的人嗎?"
            ),
            anomalies=data.get("anomalies", []),
            hiddenSignals=data.get("hiddenSignals", []),
            emotionalIndicators=data.get("emotionalIndicators", []),
        )


# ============================================================================
# Retry Strategy
# ============================================================================


class RetryStrategy:
    """Configurable retry strategy"""

    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        backoff_factor: float = 2.0,
        max_delay: float = 60.0,
    ):
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.backoff_factor = backoff_factor
        self.max_delay = max_delay

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number"""
        delay = self.initial_delay * (self.backoff_factor**attempt)
        return min(delay, self.max_delay)

    @contextmanager
    def attempt(self, attempt_num: int):
        """Context manager for retry attempts"""
        if attempt_num > 0:
            delay = self.calculate_delay(attempt_num - 1)
            logger.info(f"Waiting {delay:.1f}s before retry attempt {attempt_num + 1}")
            time.sleep(delay)
        yield


# ============================================================================
# Entry Formatter
# ============================================================================


class EntryFormatter:
    """Formats diary entries for LLM consumption"""

    @staticmethod
    def _format_metadata_header(entry: DiaryEntry) -> Optional[str]:
        """Build the optional metadata line for an entry.

        Returns ``None`` when the entry has no structured fields populated,
        so callers can fall back to the plain ``[logical_date]`` header.
        """
        parts: List[str] = []

        bedtime = getattr(entry, "sleep_bedtime", None)
        wake = getattr(entry, "wake_time", None)
        if bedtime is not None or wake is not None:
            bt = bedtime if bedtime is not None else "?"
            wt = wake if wake is not None else "?"
            parts.append(f"睡眠 {bt}→{wt}")

        sq = getattr(entry, "sleep_quality", None)
        if sq is not None:
            parts.append(f"睡眠品質 {sq}/5")

        m = getattr(entry, "mood", None)
        if m is not None:
            parts.append(f"心情 {m}/5")

        e = getattr(entry, "energy", None)
        if e is not None:
            parts.append(f"精力 {e}/5")

        if not parts:
            return None

        return f"[{entry.logical_date}] " + "｜".join(parts)

    @staticmethod
    def format_entries(entries: List[DiaryEntry]) -> str:
        """Format entries into structured text.

        When structured fields are present, a metadata header line precedes
        the diary text; otherwise the plain ``[logical_date]`` header is
        used (backward-compatible behavior).
        """
        if not entries:
            return ""

        formatted = []
        for entry in entries:
            header = EntryFormatter._format_metadata_header(entry)
            if header is None:
                header = f"[{entry.logical_date}]"
            formatted.append(f"{header}\n{entry.diary_text}")

        return "\n\n".join(formatted)

    @staticmethod
    def format_entries_with_metadata(entries: List[DiaryEntry]) -> str:
        """Format entries with additional metadata"""
        if not entries:
            return ""

        formatted = []
        for entry in entries:
            meta = []
            if hasattr(entry, "word_count"):
                meta.append(f"字數: {entry.word_count}")
            if hasattr(entry, "sentiment_score"):
                meta.append(f"情緒: {entry.sentiment_score:.2f}")

            entry_text = f"[{entry.logical_date}]"
            if meta:
                entry_text += f" ({', '.join(meta)})"
            entry_text += f"\n{entry.diary_text}"

            formatted.append(entry_text)

        return "\n\n".join(formatted)


# ============================================================================
# Main Enhanced Analyzer
# ============================================================================


class LLMAnalyzer:
    """Enhanced LLM analyzer with better structure and separation of concerns"""

    def __init__(
        self,
        config: Config,
        client: Optional[LLMClient] = None,
        prompt_manager: Optional[PromptManager] = None,
        parser: Optional[ResponseParser] = None,
        formatter: Optional[EntryFormatter] = None,
        retry_strategy: Optional[RetryStrategy] = None,
    ):
        self.config = config
        self.client = client or HTTPLLMClient(config)
        self.prompt_manager = prompt_manager or PromptManager()
        self.parser = parser or ResponseParser()
        self.formatter = formatter or EntryFormatter()
        self.retry_strategy = retry_strategy or RetryStrategy(max_attempts=config.LLM_MAX_RETRIES)

    def analyze(
        self,
        entries: List[DiaryEntry],
        run_id: str,
        mode: AnalysisMode = AnalysisMode.STANDARD,
        stream: bool = False,
    ) -> InsightPack:
        """
        Analyze diary entries and generate insights

        Args:
            entries: List of diary entries to analyze
            run_id: Unique identifier for this analysis run
            mode: Analysis mode (quick/standard/deep)
            stream: Whether to use streaming for LLM calls

        Returns:
            InsightPack with analysis results
        """
        if not entries:
            return InsightPack.create_fallback(run_id, self.config.VERSION, 0)

        # Format entries
        entries_text = self.formatter.format_entries(entries)

        # Build request
        template = self.prompt_manager.get_template("analysis")
        prompt = template.render(entries_text=entries_text)

        request = LLMRequest(
            prompt=prompt,
            system_prompt=self.prompt_manager.get_system_prompt(),
            temperature=self._get_temperature(mode),
            stream=stream,
        )

        # Try with retries
        last_error = None
        for attempt in range(self.retry_strategy.max_attempts):
            with self.retry_strategy.attempt(attempt):
                try:
                    # Call LLM
                    if stream and hasattr(self.config, "LLM_STREAM") and self.config.LLM_STREAM:
                        response_content = self._call_streaming(request)
                    else:
                        response = self.client.call(request)
                        response_content = response.content

                    # Parse response
                    data = self.parser.extract_json(response_content)

                    # Validate
                    if not self.parser.validate_analysis_response(data):
                        raise ValueError("Invalid response structure")

                    # Create InsightPack
                    pack = self.parser.parse_analysis_response(
                        data, run_id, len(entries), self.config.VERSION
                    )

                    logger.info(
                        f"Analysis successful on attempt {attempt + 1}/{self.retry_strategy.max_attempts}"
                    )
                    return pack

                except Exception as e:
                    last_error = e
                    logger.warning(
                        f"Attempt {attempt + 1}/{self.retry_strategy.max_attempts} failed: {e}"
                    )

        # All attempts failed
        logger.error(f"All LLM attempts failed. Last error: {last_error}")
        return InsightPack.create_fallback(run_id, self.config.VERSION, len(entries))

    def _call_streaming(self, request: LLMRequest) -> str:
        """Handle streaming LLM call with output"""
        logger.info("Starting streaming LLM call")
        collected = []

        try:
            for token in self.client.call_streaming(request):
                collected.append(token)
                sys.stdout.write(token)
                sys.stdout.flush()
        finally:
            print()  # Newline after streaming

        return "".join(collected)

    def _get_temperature(self, mode: AnalysisMode) -> float:
        """Get temperature based on analysis mode"""
        temperatures = {AnalysisMode.QUICK: 0.5, AnalysisMode.STANDARD: 0.7, AnalysisMode.DEEP: 0.9}
        return temperatures.get(mode, 0.7)

    def analyze_batch(
        self,
        entry_batches: List[List[DiaryEntry]],
        run_id: str,
        mode: AnalysisMode = AnalysisMode.STANDARD,
    ) -> List[InsightPack]:
        """Analyze multiple batches of entries"""
        results = []

        for i, batch in enumerate(entry_batches):
            batch_id = f"{run_id}_batch_{i}"
            logger.info(f"Analyzing batch {i + 1}/{len(entry_batches)}")

            pack = self.analyze(batch, batch_id, mode)
            results.append(pack)

        return results

    def close(self):
        """Clean up resources"""
        if hasattr(self.client, "close"):
            self.client.close()


# ============================================================================
# Factory Function for Backward Compatibility
# ============================================================================

def create_llm_analyzer(config: Config) -> LLMAnalyzer:
    """Factory function to create an analyzer with default components"""
    return LLMAnalyzer(config)
