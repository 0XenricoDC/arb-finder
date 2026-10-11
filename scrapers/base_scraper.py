"""
Abstract base class for all platform scrapers.

Provides common functionality for fetching odds data from betting platforms
including async HTTP requests, retry logic, and team name normalization.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import logging
import re

import aiohttp
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)


logger = logging.getLogger(__name__)


class ScraperError(Exception):
    """Base exception for scraper errors."""
    pass


class RateLimitError(ScraperError):
    """Raised when rate limited by the platform."""
    pass


class ParseError(ScraperError):
    """Raised when parsing response data fails."""
    pass


class BaseScraper(ABC):
    """
    Abstract base class for betting platform scrapers.

    Attributes:
        platform_name: Identifier for the platform (e.g., "azuro", "overtime")
        config: Platform-specific configuration dict
        session: Shared aiohttp ClientSession for requests
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the scraper with platform configuration.

        Args:
            config: Platform config dict containing endpoints, rate limits, etc.
        """
        self.config = config
        self.platform_name = config.get("name", self.__class__.__name__)
        self.enabled = config.get("enabled", True)
        self.refresh_interval = config.get("refresh_interval", 30)
        self._session: Optional[aiohttp.ClientSession] = None

        self.logger = logging.getLogger(f"{__name__}.{self.platform_name}")

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers=self._get_default_headers(),
            )
        return self._session

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _get_default_headers(self) -> Dict[str, str]:
        """Get default HTTP headers for requests."""
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def _make_request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Make an HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            **kwargs: Additional arguments passed to aiohttp request

        Returns:
            Parsed JSON response as dict

        Raises:
            RateLimitError: If rate limited (429 status)
            ScraperError: For other HTTP errors
        """
        session = await self.get_session()

        self.logger.debug(f"Making {method} request to {url}")

        async with session.request(method, url, **kwargs) as response:
            if response.status == 429:
                self.logger.warning(f"Rate limited by {self.platform_name}")
                raise RateLimitError(f"Rate limited by {self.platform_name}")

            if response.status >= 400:
                text = await response.text()
                self.logger.error(f"HTTP {response.status} from {url}: {text[:200]}")
                raise ScraperError(f"HTTP {response.status}: {text[:200]}")

            return await response.json()

    async def get(self, url: str, **kwargs: Any) -> Dict[str, Any]:
        """Make a GET request."""
        return await self._make_request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> Dict[str, Any]:
        """Make a POST request."""
        return await self._make_request("POST", url, **kwargs)

    # =========================================================================
    # Abstract Methods - Must be implemented by subclasses
    # =========================================================================

    @abstractmethod
    async def fetch_events(self) -> List[Dict[str, Any]]:
        """
        Fetch all upcoming events from the platform.

        Returns:
            List of event dictionaries with standardized structure

        Raises:
            ScraperError: If fetching fails
        """
        pass

    @abstractmethod
    def parse_event(self, raw_event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse a raw event from the platform's format to standardized format.

        Args:
            raw_event: Raw event data from the platform API

        Returns:
            Standardized event dict with keys:
                - event_id: str
                - sport: str
                - league: str
                - home_team: str
                - away_team: str
                - start_time: datetime
                - markets: Dict[str, Any]
                - raw_data: Dict

        Raises:
            ParseError: If parsing fails
        """
        pass

    @abstractmethod
    def get_odds(self, event: Dict[str, Any], market_type: str) -> Dict[str, float]:
        """
        Extract odds for a specific market from an event.

        Args:
            event: Parsed event dictionary
            market_type: Type of market (e.g., "1x2", "moneyline", "over_under")

        Returns:
            Dict mapping outcome names to decimal odds:
                {"home": 2.10, "draw": 3.50, "away": 3.80}

        Raises:
            ParseError: If odds extraction fails
        """
        pass

    # =========================================================================
    # Common Methods - Shared functionality for all scrapers
    # =========================================================================

    def normalize_team_name(self, name: str) -> str:
        """
        Normalize a team name for matching across platforms.

        Removes common suffixes, punctuation, and converts to lowercase.

        Args:
            name: Raw team name from platform

        Returns:
            Normalized team name
        """
        if not name:
            return ""

        # Convert to lowercase and strip whitespace
        normalized = name.lower().strip()

        # Remove common suffixes/prefixes
        suffixes = [
            r'\bfc\b', r'\bsc\b', r'\bac\b', r'\bss\b',
            r'\bafc\b', r'\bcfc\b', r'\bssc\b', r'\basdc\b',
            r'\bunited\b', r'\bcity\b', r'\btown\b',
        ]
        for suffix in suffixes:
            normalized = re.sub(suffix, '', normalized)

        # Remove punctuation
        normalized = re.sub(r'[^\w\s]', '', normalized)

        # Collapse multiple spaces
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        return normalized

    def convert_odds_format(
        self,
        odds: float,
        from_format: str = "decimal",
        to_format: str = "decimal",
    ) -> float:
        """
        Convert odds between different formats.

        Supported formats:
            - decimal: European decimal odds (e.g., 2.50)
            - american: American odds (e.g., +150, -200)
            - probability: Implied probability (e.g., 0.40)
            - raw: Raw blockchain format (divide by 10^12)

        Args:
            odds: The odds value to convert
            from_format: Source format
            to_format: Target format

        Returns:
            Converted odds value
        """
        # First convert to decimal as intermediate
        if from_format == "decimal":
            decimal_odds = odds
        elif from_format == "american":
            if odds > 0:
                decimal_odds = (odds / 100) + 1
            else:
                decimal_odds = (100 / abs(odds)) + 1
        elif from_format == "probability":
            decimal_odds = 1 / odds if odds > 0 else 0
        elif from_format == "raw":
            # Azuro-style raw odds (divide by 10^12)
            decimal_odds = odds / 1e12
        else:
            raise ValueError(f"Unknown odds format: {from_format}")

        # Convert from decimal to target format
        if to_format == "decimal":
            return round(decimal_odds, 3)
        elif to_format == "american":
            if decimal_odds >= 2.0:
                return round((decimal_odds - 1) * 100)
            else:
                return round(-100 / (decimal_odds - 1))
        elif to_format == "probability":
            return round(1 / decimal_odds, 4) if decimal_odds > 0 else 0
        elif to_format == "raw":
            return int(decimal_odds * 1e12)
        else:
            raise ValueError(f"Unknown odds format: {to_format}")

    def calculate_implied_probability(self, decimal_odds: float) -> float:
        """
        Calculate implied probability from decimal odds.

        Args:
            decimal_odds: European decimal odds

        Returns:
            Implied probability as float (0-1)
        """
        if decimal_odds <= 0:
            return 0.0
        return round(1 / decimal_odds, 4)

    def is_event_valid(
        self,
        start_time: datetime,
        min_minutes_before: int = 5,
        max_hours_before: int = 48,
    ) -> bool:
        """
        Check if an event is within the valid time window.

        Args:
            start_time: Event start time (UTC)
            min_minutes_before: Minimum minutes before start
            max_hours_before: Maximum hours before start

        Returns:
            True if event is within valid window
        """
        now = datetime.now(timezone.utc)

        # Ensure start_time is timezone aware
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)

        time_until_start = start_time - now
        minutes_until = time_until_start.total_seconds() / 60
        hours_until = minutes_until / 60

        return min_minutes_before < minutes_until < (max_hours_before * 60)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(platform={self.platform_name}, enabled={self.enabled})>"
