"""
Overtime Markets scraper for fetching odds from the Thales API.

Overtime is a decentralized sports betting platform built on Thales Protocol,
available on Optimism, Arbitrum, and Base networks.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import logging

from scrapers.base_scraper import BaseScraper, ScraperError, ParseError


logger = logging.getLogger(__name__)


# Network IDs for Overtime Markets
NETWORK_IDS = {
    "optimism": 10,
    "arbitrum": 42161,
    "base": 8453,
}

# Sport name mapping to standardized names
SPORT_MAP = {
    "soccer": "soccer",
    "football": "soccer",
    "basketball": "basketball",
    "tennis": "tennis",
    "hockey": "hockey",
    "baseball": "baseball",
    "mma": "mma",
    "esports": "esports",
}


class OvertimeScraper(BaseScraper):
    """
    Scraper for Overtime Markets betting odds.

    Fetches data from the Thales/Overtime REST API.
    """

    BASE_URL = "https://api.thalesmarket.io/overtime/v2"

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Overtime scraper.

        Args:
            config: Platform configuration dict with keys:
                - network: Network name (optimism, arbitrum, base)
                - network_id: Network ID (overrides network name)
                - enabled_sports: List of sports to fetch
        """
        super().__init__(config)

        # Determine network ID
        network = config.get("chain", config.get("network", "optimism"))
        self.network_id = config.get("network_id", NETWORK_IDS.get(network, 10))

        # Sports to fetch
        self.enabled_sports = config.get(
            "enabled_sports",
            ["soccer", "basketball", "tennis"]
        )

        # API base URL
        self.api_base = config.get("api_base", self.BASE_URL)

        self.logger.info(
            f"Initialized Overtime scraper for network {network} (ID: {self.network_id})"
        )

    def _get_markets_url(self) -> str:
        """Get the markets endpoint URL."""
        return f"{self.api_base}/networks/{self.network_id}/markets"

    async def fetch_events(self) -> List[Dict[str, Any]]:
        """
        Fetch all upcoming events from Overtime Markets.

        Returns:
            List of parsed event dictionaries

        Raises:
            ScraperError: If fetching fails
        """
        all_events = []

        try:
            url = self._get_markets_url()
            self.logger.debug(f"Fetching markets from {url}")

            response = await self.get(url)

            # Response can be a list directly or wrapped in an object
            if isinstance(response, list):
                markets = response
            else:
                markets = response.get("markets", response.get("data", []))

            self.logger.debug(f"Received {len(markets)} markets from Overtime")

            for raw_market in markets:
                try:
                    # Skip paused or canceled markets
                    if raw_market.get("isPaused") or raw_market.get("isCanceled"):
                        continue

                    parsed = self.parse_event(raw_market)
                    if parsed:
                        # Filter by enabled sports
                        if parsed["sport"].lower() in [s.lower() for s in self.enabled_sports]:
                            all_events.append(parsed)

                except ParseError as e:
                    self.logger.warning(
                        f"Failed to parse market {raw_market.get('gameId', 'unknown')}: {e}"
                    )
                    continue

            self.logger.info(f"Fetched {len(all_events)} events from Overtime")
            return all_events

        except ScraperError:
            raise
        except Exception as e:
            self.logger.error(f"Error fetching from Overtime: {e}")
            raise ScraperError(f"Failed to fetch from Overtime: {e}")

    def parse_event(self, raw_event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse a raw Overtime market into standardized event format.

        Args:
            raw_event: Raw market data from API response

        Returns:
            Standardized event dict or None if invalid

        Raises:
            ParseError: If critical parsing fails
        """
        try:
            # Get game/market ID
            game_id = raw_event.get("gameId") or raw_event.get("address")
            if not game_id:
                raise ParseError("Missing gameId/address")

            # Extract teams
            home_team = raw_event.get("homeTeam", "")
            away_team = raw_event.get("awayTeam", "")

            if not home_team or not away_team:
                self.logger.debug(f"Market {game_id} missing team names, skipping")
                return None

            # Parse sport
            sport_raw = raw_event.get("sport", "unknown")
            if isinstance(sport_raw, dict):
                sport_raw = sport_raw.get("name", "unknown")
            sport = SPORT_MAP.get(sport_raw.lower(), sport_raw.lower())

            # Parse league
            league = raw_event.get("leagueName", raw_event.get("league", "Unknown League"))
            if isinstance(league, dict):
                league = league.get("name", "Unknown League")

            # Parse start time (maturityDate is Unix timestamp)
            maturity = raw_event.get("maturityDate") or raw_event.get("startsAt")
            if maturity:
                if isinstance(maturity, str):
                    maturity = int(maturity)
                start_time = datetime.fromtimestamp(maturity, tz=timezone.utc)
            else:
                raise ParseError(f"Missing maturityDate for market {game_id}")

            # Check if event is in the future
            if start_time <= datetime.now(timezone.utc):
                self.logger.debug(f"Market {game_id} already started, skipping")
                return None

            # Parse odds and build markets
            markets = self._parse_odds(raw_event)

            if not markets:
                self.logger.debug(f"Market {game_id} has no valid odds, skipping")
                return None

            return {
                "event_id": f"overtime_{game_id}",
                "platform": "overtime",
                "sport": sport,
                "league": league,
                "home_team": home_team,
                "away_team": away_team,
                "home_team_normalized": self.normalize_team_name(home_team),
                "away_team_normalized": self.normalize_team_name(away_team),
                "start_time": start_time,
                "markets": markets,
                "url": f"https://overtimemarkets.xyz/markets/{game_id}",
                "raw_data": raw_event,
            }

        except ParseError:
            raise
        except Exception as e:
            raise ParseError(f"Failed to parse event: {e}")

    def _parse_odds(self, raw_event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse odds from Overtime market data.

        Overtime provides odds directly in decimal format.

        Args:
            raw_event: Raw market data

        Returns:
            Dict of market_type -> market data
        """
        markets = {}

        # Extract odds - Overtime provides them directly in decimal format
        home_odds = self._extract_odds(raw_event, "homeOdds")
        away_odds = self._extract_odds(raw_event, "awayOdds")
        draw_odds = self._extract_odds(raw_event, "drawOdds")

        # Determine market type based on available odds
        if home_odds and away_odds and draw_odds:
            # 3-way market (1X2) - typically soccer
            market_type = "1x2"
            markets[market_type] = {
                "market_type": market_type,
                "outcomes": {
                    "home": {
                        "outcome": "home",
                        "decimal_odds": home_odds,
                        "implied_prob": self.calculate_implied_probability(home_odds),
                        "platform": "overtime",
                    },
                    "draw": {
                        "outcome": "draw",
                        "decimal_odds": draw_odds,
                        "implied_prob": self.calculate_implied_probability(draw_odds),
                        "platform": "overtime",
                    },
                    "away": {
                        "outcome": "away",
                        "decimal_odds": away_odds,
                        "implied_prob": self.calculate_implied_probability(away_odds),
                        "platform": "overtime",
                    },
                },
            }

        elif home_odds and away_odds:
            # 2-way market (moneyline) - basketball, tennis, etc.
            market_type = "moneyline"
            markets[market_type] = {
                "market_type": market_type,
                "outcomes": {
                    "home": {
                        "outcome": "home",
                        "decimal_odds": home_odds,
                        "implied_prob": self.calculate_implied_probability(home_odds),
                        "platform": "overtime",
                    },
                    "away": {
                        "outcome": "away",
                        "decimal_odds": away_odds,
                        "implied_prob": self.calculate_implied_probability(away_odds),
                        "platform": "overtime",
                    },
                },
            }

        return markets

    def _extract_odds(self, data: Dict[str, Any], key: str) -> Optional[float]:
        """
        Extract and validate odds value from market data.

        Args:
            data: Market data dict
            key: Key to extract (e.g., "homeOdds")

        Returns:
            Decimal odds or None if invalid
        """
        value = data.get(key)

        if value is None:
            return None

        try:
            odds = float(value)

            # Validate odds are in reasonable range
            if odds < 1.01 or odds > 100:
                return None

            return round(odds, 3)

        except (ValueError, TypeError):
            return None

    def get_odds(self, event: Dict[str, Any], market_type: str) -> Dict[str, float]:
        """
        Extract odds for a specific market from an event.

        Args:
            event: Parsed event dictionary
            market_type: Market type (e.g., "1x2", "moneyline")

        Returns:
            Dict mapping outcome names to decimal odds

        Raises:
            ParseError: If market not found
        """
        markets = event.get("markets", {})
        market = markets.get(market_type)

        if not market:
            raise ParseError(f"Market '{market_type}' not found in event")

        outcomes = market.get("outcomes", {})
        return {
            name: data["decimal_odds"]
            for name, data in outcomes.items()
        }

    def get_best_odds(self, event: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Get the best available odds for each outcome across all markets.

        Args:
            event: Parsed event dictionary

        Returns:
            Dict mapping market_type -> outcome -> odds info
        """
        result = {}

        for market_type, market in event.get("markets", {}).items():
            result[market_type] = {}
            for outcome_name, outcome_data in market.get("outcomes", {}).items():
                result[market_type][outcome_name] = {
                    "odds": outcome_data["decimal_odds"],
                    "platform": "overtime",
                    "implied_prob": outcome_data["implied_prob"],
                }

        return result
