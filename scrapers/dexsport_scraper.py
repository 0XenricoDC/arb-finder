"""
Dexsport.io scraper for fetching odds.

Dexsport is a DeFi betting platform. Since there's no public API,
we attempt to find internal API endpoints or fall back to web scraping.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import logging

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper, ScraperError, ParseError


logger = logging.getLogger(__name__)


# Sport URL mappings for Dexsport
SPORT_URLS = {
    "soccer": "soccer",
    "football": "soccer",
    "basketball": "basketball",
    "tennis": "tennis",
    "esports": "esports",
    "mma": "mma",
    "hockey": "hockey",
}


class DexsportScraper(BaseScraper):
    """
    Scraper for Dexsport betting platform.

    Attempts to use internal API, falls back to HTML parsing.
    """

    BASE_URL = "https://dexsport.io"
    API_URL = "https://api.dexsport.io"  # Potential API endpoint

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        self.enabled_sports = config.get(
            "enabled_sports",
            ["soccer", "basketball", "tennis"]
        )

        self.logger.info("Initialized Dexsport scraper")

    def _get_default_headers(self) -> Dict[str, str]:
        """Get headers that mimic a real browser."""
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": self.BASE_URL,
            "Origin": self.BASE_URL,
        }

    async def fetch_events(self) -> List[Dict[str, Any]]:
        """
        Fetch events from Dexsport.

        Tries API first, then falls back to scraping.
        """
        all_events = []

        # Try to find and use internal API
        try:
            events = await self._fetch_from_api()
            if events:
                all_events.extend(events)
                self.logger.info(f"Fetched {len(events)} events from Dexsport API")
                return all_events
        except Exception as e:
            self.logger.debug(f"API fetch failed, trying HTML scraping: {e}")

        # Fallback to HTML scraping for each sport
        for sport in self.enabled_sports:
            try:
                sport_url = SPORT_URLS.get(sport, sport)
                events = await self._scrape_sport_page(sport_url)
                all_events.extend(events)
            except Exception as e:
                self.logger.warning(f"Failed to scrape {sport}: {e}")

        self.logger.info(f"Fetched {len(all_events)} events from Dexsport")
        return all_events

    async def _fetch_from_api(self) -> List[Dict[str, Any]]:
        """Try to fetch from potential API endpoints."""
        events = []

        # Common API endpoint patterns to try
        api_endpoints = [
            f"{self.API_URL}/v1/events",
            f"{self.API_URL}/v1/sports/events",
            f"{self.API_URL}/events",
            f"{self.BASE_URL}/api/events",
            f"{self.BASE_URL}/api/v1/events",
            f"{self.BASE_URL}/api/sports",
        ]

        for endpoint in api_endpoints:
            try:
                response = await self.get(endpoint)
                if response and isinstance(response, (list, dict)):
                    # Found a working endpoint
                    self.logger.info(f"Found working API: {endpoint}")
                    data = response if isinstance(response, list) else response.get("data", response.get("events", []))

                    for item in data:
                        try:
                            parsed = self._parse_api_event(item)
                            if parsed:
                                events.append(parsed)
                        except Exception:
                            continue

                    if events:
                        return events
            except Exception:
                continue

        return events

    def _parse_api_event(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse an event from API response."""
        try:
            event_id = raw.get("id") or raw.get("eventId") or raw.get("game_id")
            if not event_id:
                return None

            home_team = raw.get("home") or raw.get("homeTeam") or raw.get("team1", "")
            away_team = raw.get("away") or raw.get("awayTeam") or raw.get("team2", "")

            if not home_team or not away_team:
                return None

            sport = raw.get("sport", raw.get("sportName", "unknown")).lower()
            league = raw.get("league", raw.get("tournament", "Unknown"))

            # Parse start time
            start_ts = raw.get("startTime") or raw.get("start_time") or raw.get("kickoff")
            if start_ts:
                if isinstance(start_ts, (int, float)):
                    start_time = datetime.fromtimestamp(start_ts, tz=timezone.utc)
                else:
                    start_time = datetime.fromisoformat(str(start_ts).replace("Z", "+00:00"))
            else:
                start_time = datetime.now(timezone.utc)

            # Parse odds
            markets = self._parse_api_odds(raw)

            if not markets:
                return None

            return {
                "event_id": f"dexsport_{event_id}",
                "platform": "dexsport",
                "sport": sport,
                "league": league,
                "home_team": home_team,
                "away_team": away_team,
                "home_team_normalized": self.normalize_team_name(home_team),
                "away_team_normalized": self.normalize_team_name(away_team),
                "start_time": start_time,
                "markets": markets,
                "url": f"{self.BASE_URL}/event/{event_id}",
                "raw_data": raw,
            }
        except Exception as e:
            self.logger.debug(f"Failed to parse API event: {e}")
            return None

    def _parse_api_odds(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Parse odds from API response."""
        markets = {}

        # Try various odds field names
        home_odds = raw.get("homeOdds") or raw.get("odds1") or raw.get("home_odds")
        away_odds = raw.get("awayOdds") or raw.get("odds2") or raw.get("away_odds")
        draw_odds = raw.get("drawOdds") or raw.get("oddsX") or raw.get("draw_odds")

        # Also check nested odds structure
        if not home_odds and "odds" in raw:
            odds_data = raw["odds"]
            if isinstance(odds_data, dict):
                home_odds = odds_data.get("home") or odds_data.get("1")
                away_odds = odds_data.get("away") or odds_data.get("2")
                draw_odds = odds_data.get("draw") or odds_data.get("X")
            elif isinstance(odds_data, list) and len(odds_data) >= 2:
                home_odds = odds_data[0]
                away_odds = odds_data[1] if len(odds_data) > 1 else None
                draw_odds = odds_data[2] if len(odds_data) > 2 else None

        if home_odds and away_odds:
            try:
                home_odds = float(home_odds)
                away_odds = float(away_odds)

                if draw_odds:
                    draw_odds = float(draw_odds)
                    markets["1x2"] = {
                        "market_type": "1x2",
                        "outcomes": {
                            "home": {"outcome": "home", "decimal_odds": home_odds, "implied_prob": 1/home_odds, "platform": "dexsport"},
                            "draw": {"outcome": "draw", "decimal_odds": draw_odds, "implied_prob": 1/draw_odds, "platform": "dexsport"},
                            "away": {"outcome": "away", "decimal_odds": away_odds, "implied_prob": 1/away_odds, "platform": "dexsport"},
                        }
                    }
                else:
                    markets["moneyline"] = {
                        "market_type": "moneyline",
                        "outcomes": {
                            "home": {"outcome": "home", "decimal_odds": home_odds, "implied_prob": 1/home_odds, "platform": "dexsport"},
                            "away": {"outcome": "away", "decimal_odds": away_odds, "implied_prob": 1/away_odds, "platform": "dexsport"},
                        }
                    }
            except (ValueError, TypeError, ZeroDivisionError):
                pass

        return markets

    async def _scrape_sport_page(self, sport: str) -> List[Dict[str, Any]]:
        """Scrape events from a sport page using BeautifulSoup."""
        events = []
        url = f"{self.BASE_URL}/sports/{sport}"

        try:
            session = await self.get_session()
            async with session.get(url, headers=self._get_default_headers()) as response:
                if response.status != 200:
                    self.logger.warning(f"Got status {response.status} from {url}")
                    return events

                html = await response.text()
                soup = BeautifulSoup(html, "lxml")

                # Try to find event cards
                event_cards = soup.find_all("div", class_=re.compile(r"event|match|game", re.I))

                for card in event_cards:
                    try:
                        parsed = self._parse_html_event(card, sport)
                        if parsed:
                            events.append(parsed)
                    except Exception as e:
                        self.logger.debug(f"Failed to parse event card: {e}")

                # Also try to extract from embedded JSON/script tags
                scripts = soup.find_all("script")
                for script in scripts:
                    if script.string and ("events" in script.string or "matches" in script.string):
                        try:
                            # Try to extract JSON from script
                            json_match = re.search(r'\{.*"events?".*\}', script.string)
                            if json_match:
                                import json
                                data = json.loads(json_match.group())
                                # Parse the embedded data
                                pass
                        except Exception:
                            pass

        except Exception as e:
            self.logger.error(f"Failed to scrape {url}: {e}")

        return events

    def _parse_html_event(self, card, sport: str) -> Optional[Dict[str, Any]]:
        """Parse an event from HTML card element."""
        try:
            # Try to find team names
            teams = card.find_all(class_=re.compile(r"team|participant|player", re.I))
            if len(teams) < 2:
                # Try alternative selectors
                teams = card.find_all("span", class_=re.compile(r"name", re.I))

            if len(teams) < 2:
                return None

            home_team = teams[0].get_text(strip=True)
            away_team = teams[1].get_text(strip=True)

            if not home_team or not away_team:
                return None

            # Try to find odds
            odds_elements = card.find_all(class_=re.compile(r"odd|coef|price", re.I))

            if len(odds_elements) < 2:
                return None

            odds_values = []
            for el in odds_elements:
                text = el.get_text(strip=True)
                try:
                    odds_values.append(float(text))
                except ValueError:
                    # Try to extract number from text
                    match = re.search(r'\d+\.?\d*', text)
                    if match:
                        odds_values.append(float(match.group()))

            if len(odds_values) < 2:
                return None

            # Build markets
            markets = {}
            if len(odds_values) >= 3:
                markets["1x2"] = {
                    "market_type": "1x2",
                    "outcomes": {
                        "home": {"outcome": "home", "decimal_odds": odds_values[0], "implied_prob": 1/odds_values[0], "platform": "dexsport"},
                        "draw": {"outcome": "draw", "decimal_odds": odds_values[1], "implied_prob": 1/odds_values[1], "platform": "dexsport"},
                        "away": {"outcome": "away", "decimal_odds": odds_values[2], "implied_prob": 1/odds_values[2], "platform": "dexsport"},
                    }
                }
            else:
                markets["moneyline"] = {
                    "market_type": "moneyline",
                    "outcomes": {
                        "home": {"outcome": "home", "decimal_odds": odds_values[0], "implied_prob": 1/odds_values[0], "platform": "dexsport"},
                        "away": {"outcome": "away", "decimal_odds": odds_values[1], "implied_prob": 1/odds_values[1], "platform": "dexsport"},
                    }
                }

            event_id = card.get("data-id") or card.get("id") or f"{home_team}_{away_team}".replace(" ", "_")

            return {
                "event_id": f"dexsport_{event_id}",
                "platform": "dexsport",
                "sport": sport,
                "league": "Unknown",
                "home_team": home_team,
                "away_team": away_team,
                "home_team_normalized": self.normalize_team_name(home_team),
                "away_team_normalized": self.normalize_team_name(away_team),
                "start_time": datetime.now(timezone.utc),
                "markets": markets,
                "url": f"{self.BASE_URL}/sports/{sport}",
                "raw_data": {},
            }

        except Exception as e:
            self.logger.debug(f"HTML parsing error: {e}")
            return None

    def parse_event(self, raw_event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse event - delegates to appropriate parser."""
        return self._parse_api_event(raw_event)

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
