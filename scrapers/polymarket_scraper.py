"""
Polymarket scraper for fetching odds from prediction markets.

Polymarket is a prediction market platform on Polygon.
While not strictly sports betting, it often has sports-related markets.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import logging

from scrapers.base_scraper import BaseScraper, ScraperError, ParseError


logger = logging.getLogger(__name__)


class PolymarketScraper(BaseScraper):
    """
    Scraper for Polymarket prediction markets.

    Uses the Polymarket CLOB API.
    """

    BASE_URL = "https://clob.polymarket.com"
    GAMMA_URL = "https://gamma-api.polymarket.com"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.logger.info("Initialized Polymarket scraper")

    async def fetch_events(self) -> List[Dict[str, Any]]:
        """Fetch active markets from Polymarket."""
        all_events = []

        try:
            # Fetch markets from Gamma API
            url = f"{self.GAMMA_URL}/markets"
            params = {
                "closed": "false",
                "limit": 100,
            }

            response = await self.get(url, params=params)
            markets = response if isinstance(response, list) else response.get("data", [])

            self.logger.debug(f"Received {len(markets)} markets from Polymarket")

            for market in markets:
                try:
                    # Filter for sports-related markets
                    tags = market.get("tags", [])
                    category = market.get("category", "").lower()

                    is_sports = any(
                        tag.lower() in ["sports", "nfl", "nba", "soccer", "football", "tennis", "mma", "ufc"]
                        for tag in tags
                    ) or category in ["sports", "nfl", "nba"]

                    if not is_sports:
                        continue

                    parsed = self.parse_event(market)
                    if parsed:
                        all_events.append(parsed)

                except ParseError as e:
                    self.logger.warning(f"Failed to parse market: {e}")
                    continue

            self.logger.info(f"Fetched {len(all_events)} sports events from Polymarket")
            return all_events

        except Exception as e:
            self.logger.error(f"Error fetching from Polymarket: {e}")
            raise ScraperError(f"Failed to fetch from Polymarket: {e}")

    def parse_event(self, raw_event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a Polymarket market into event format."""
        try:
            market_id = raw_event.get("id") or raw_event.get("condition_id")
            if not market_id:
                return None

            question = raw_event.get("question", "")

            # Try to extract teams from question
            # Format is often "Team A vs Team B" or "Will Team A win?"
            home_team = "Yes"
            away_team = "No"

            if " vs " in question.lower():
                parts = question.split(" vs ")
                if len(parts) >= 2:
                    home_team = parts[0].strip()
                    away_team = parts[1].split("?")[0].strip()

            # Get end date
            end_date = raw_event.get("end_date_iso") or raw_event.get("end_date")
            if end_date:
                if isinstance(end_date, str):
                    start_time = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                else:
                    start_time = datetime.fromtimestamp(end_date, tz=timezone.utc)
            else:
                start_time = datetime.now(timezone.utc)

            # Parse outcomes/tokens
            tokens = raw_event.get("tokens", [])
            outcomes = raw_event.get("outcomes", [])

            markets = self._parse_outcomes(tokens, outcomes)

            if not markets:
                return None

            return {
                "event_id": f"polymarket_{market_id}",
                "platform": "polymarket",
                "sport": raw_event.get("category", "prediction"),
                "league": "Polymarket",
                "home_team": home_team,
                "away_team": away_team,
                "home_team_normalized": self.normalize_team_name(home_team),
                "away_team_normalized": self.normalize_team_name(away_team),
                "start_time": start_time,
                "markets": markets,
                "url": f"https://polymarket.com/event/{raw_event.get('slug', market_id)}",
                "raw_data": raw_event,
            }

        except Exception as e:
            raise ParseError(f"Failed to parse Polymarket event: {e}")

    def _parse_outcomes(
        self,
        tokens: List[Dict],
        outcomes: List[str]
    ) -> Dict[str, Any]:
        """Parse Polymarket tokens into market odds."""
        markets = {}

        if len(tokens) >= 2:
            # Binary market (Yes/No)
            parsed_outcomes = {}

            for i, token in enumerate(tokens[:2]):
                price = token.get("price", 0)
                if price and price > 0:
                    # Price is probability, convert to decimal odds
                    decimal_odds = 1 / price if price < 1 else price

                    outcome_name = outcomes[i] if i < len(outcomes) else ("home" if i == 0 else "away")
                    if outcome_name.lower() in ["yes", "true"]:
                        outcome_name = "home"
                    elif outcome_name.lower() in ["no", "false"]:
                        outcome_name = "away"

                    parsed_outcomes[outcome_name] = {
                        "outcome": outcome_name,
                        "decimal_odds": round(decimal_odds, 3),
                        "implied_prob": round(price, 4),
                        "platform": "polymarket",
                    }

            if len(parsed_outcomes) == 2:
                markets["moneyline"] = {
                    "market_type": "moneyline",
                    "outcomes": parsed_outcomes,
                }

        return markets

    def get_odds(self, event: Dict[str, Any], market_type: str) -> Dict[str, float]:
        """Extract odds for a specific market."""
        markets = event.get("markets", {})
        market = markets.get(market_type)

        if not market:
            raise ParseError(f"Market '{market_type}' not found")

        return {
            name: data["decimal_odds"]
            for name, data in market.get("outcomes", {}).items()
        }
