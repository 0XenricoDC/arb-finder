"""
Sportbet.one scraper for fetching odds from EOS-based betting platform.

Sportbet.one is a decentralized betting platform on the EOS blockchain.
We try to use their API or fall back to web scraping.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import logging

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper, ScraperError, ParseError


logger = logging.getLogger(__name__)


class SportbetScraper(BaseScraper):
    """
    Scraper for Sportbet.one betting platform.

    Attempts to use API endpoints, falls back to HTML parsing.
    """

    BASE_URL = "https://sportbet.one"
    API_URL = "https://api.sportbet.one"

    # Known API endpoints (may need updating)
    EVENTS_ENDPOINT = "/api/v1/events"
    SPORTS_ENDPOINT = "/api/v1/sports"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        self.enabled_sports = config.get(
            "enabled_sports",
            ["soccer", "basketball", "tennis"]
        )

        self.logger.info("Initialized Sportbet.one scraper")

    def _get_default_headers(self) -> Dict[str, str]:
        """Get headers that mimic a real browser."""
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": self.BASE_URL,
        }

    async def fetch_events(self) -> List[Dict[str, Any]]:
        """
        Fetch events from Sportbet.one.

        Tries API first, then falls back to scraping.
        """
        all_events = []

        # Try API endpoints
        try:
            events = await self._fetch_from_api()
            if events:
                all_events.extend(events)
                self.logger.info(f"Fetched {len(events)} events from Sportbet.one API")
                return all_events
        except Exception as e:
            self.logger.debug(f"API fetch failed: {e}")

        # Try scraping main page
        try:
            events = await self._scrape_main_page()
            all_events.extend(events)
        except Exception as e:
            self.logger.warning(f"Failed to scrape main page: {e}")

        # Try scraping individual sport pages
        for sport in self.enabled_sports:
            try:
                events = await self._scrape_sport_page(sport)
                all_events.extend(events)
            except Exception as e:
                self.logger.debug(f"Failed to scrape {sport}: {e}")

        self.logger.info(f"Fetched {len(all_events)} events from Sportbet.one")
        return all_events

    async def _fetch_from_api(self) -> List[Dict[str, Any]]:
        """Try to fetch from potential API endpoints."""
        events = []

        # Try various API endpoint patterns
        api_endpoints = [
            f"{self.API_URL}/events",
            f"{self.API_URL}/v1/events",
            f"{self.API_URL}/api/events",
            f"{self.BASE_URL}/api/events",
            f"{self.BASE_URL}/api/v1/events",
            f"{self.BASE_URL}/api/v1/sports/events",
            f"{self.BASE_URL}/api/matches",
            # EOS-specific endpoints
            f"{self.BASE_URL}/api/eos/events",
            f"https://api.sportbet.one/v1/matches",
        ]

        for endpoint in api_endpoints:
            try:
                self.logger.debug(f"Trying API endpoint: {endpoint}")
                response = await self.get(endpoint)

                if response and isinstance(response, (list, dict)):
                    self.logger.info(f"Found working API: {endpoint}")

                    data = response
                    if isinstance(response, dict):
                        data = response.get("data") or response.get("events") or response.get("matches") or []

                    for item in data:
                        try:
                            parsed = self._parse_api_event(item)
                            if parsed:
                                events.append(parsed)
                        except Exception:
                            continue

                    if events:
                        return events

            except Exception as e:
                self.logger.debug(f"Endpoint {endpoint} failed: {e}")
                continue

        return events

    def _parse_api_event(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse an event from API response."""
        try:
            event_id = raw.get("id") or raw.get("event_id") or raw.get("match_id")
            if not event_id:
                return None

            # Try various field names for teams
            home_team = (raw.get("home_team") or raw.get("homeTeam") or
                        raw.get("team1") or raw.get("home") or "")
            away_team = (raw.get("away_team") or raw.get("awayTeam") or
                        raw.get("team2") or raw.get("away") or "")

            # Handle nested team objects
            if isinstance(home_team, dict):
                home_team = home_team.get("name", "")
            if isinstance(away_team, dict):
                away_team = away_team.get("name", "")

            if not home_team or not away_team:
                return None

            # Parse sport
            sport = raw.get("sport", raw.get("sport_name", "unknown"))
            if isinstance(sport, dict):
                sport = sport.get("name", "unknown")
            sport = sport.lower()

            # Parse league
            league = raw.get("league") or raw.get("tournament") or raw.get("competition") or "Unknown"
            if isinstance(league, dict):
                league = league.get("name", "Unknown")

            # Parse start time
            start_time = self._parse_timestamp(raw)

            # Parse odds
            markets = self._parse_odds(raw)

            if not markets:
                return None

            return {
                "event_id": f"sportbet_{event_id}",
                "platform": "sportbet",
                "sport": sport,
                "league": league,
                "home_team": home_team,
                "away_team": away_team,
                "home_team_normalized": self.normalize_team_name(home_team),
                "away_team_normalized": self.normalize_team_name(away_team),
                "start_time": start_time,
                "markets": markets,
                "url": f"{self.BASE_URL}/match/{event_id}",
                "raw_data": raw,
            }

        except Exception as e:
            self.logger.debug(f"Failed to parse API event: {e}")
            return None

    def _parse_timestamp(self, raw: Dict[str, Any]) -> datetime:
        """Parse timestamp from various formats."""
        ts = (raw.get("start_time") or raw.get("startTime") or
              raw.get("kickoff") or raw.get("date") or raw.get("timestamp"))

        if ts:
            try:
                if isinstance(ts, (int, float)):
                    # Unix timestamp
                    if ts > 10000000000:  # Milliseconds
                        ts = ts / 1000
                    return datetime.fromtimestamp(ts, tz=timezone.utc)
                else:
                    # ISO format string
                    return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            except Exception:
                pass

        return datetime.now(timezone.utc)

    def _parse_odds(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Parse odds from various formats."""
        markets = {}

        # Try direct odds fields
        home_odds = self._extract_odds_value(raw, ["home_odds", "homeOdds", "odds_home", "1", "odds1"])
        away_odds = self._extract_odds_value(raw, ["away_odds", "awayOdds", "odds_away", "2", "odds2"])
        draw_odds = self._extract_odds_value(raw, ["draw_odds", "drawOdds", "odds_draw", "X", "oddsX"])

        # Try nested odds object
        if not home_odds:
            odds_data = raw.get("odds") or raw.get("markets") or {}
            if isinstance(odds_data, dict):
                home_odds = self._extract_odds_value(odds_data, ["home", "1", "win1"])
                away_odds = self._extract_odds_value(odds_data, ["away", "2", "win2"])
                draw_odds = self._extract_odds_value(odds_data, ["draw", "X", "tie"])

                # Try 1x2 nested market
                market_1x2 = odds_data.get("1x2") or odds_data.get("match_winner") or odds_data.get("moneyline")
                if isinstance(market_1x2, dict):
                    home_odds = home_odds or self._extract_odds_value(market_1x2, ["1", "home"])
                    draw_odds = draw_odds or self._extract_odds_value(market_1x2, ["X", "draw"])
                    away_odds = away_odds or self._extract_odds_value(market_1x2, ["2", "away"])

            elif isinstance(odds_data, list) and len(odds_data) >= 2:
                home_odds = self._safe_float(odds_data[0])
                away_odds = self._safe_float(odds_data[1])
                if len(odds_data) >= 3:
                    draw_odds = self._safe_float(odds_data[2])

        # Build market structure
        if home_odds and away_odds and home_odds > 1 and away_odds > 1:
            if draw_odds and draw_odds > 1:
                markets["1x2"] = {
                    "market_type": "1x2",
                    "outcomes": {
                        "home": {"outcome": "home", "decimal_odds": home_odds, "implied_prob": 1/home_odds, "platform": "sportbet"},
                        "draw": {"outcome": "draw", "decimal_odds": draw_odds, "implied_prob": 1/draw_odds, "platform": "sportbet"},
                        "away": {"outcome": "away", "decimal_odds": away_odds, "implied_prob": 1/away_odds, "platform": "sportbet"},
                    }
                }
            else:
                markets["moneyline"] = {
                    "market_type": "moneyline",
                    "outcomes": {
                        "home": {"outcome": "home", "decimal_odds": home_odds, "implied_prob": 1/home_odds, "platform": "sportbet"},
                        "away": {"outcome": "away", "decimal_odds": away_odds, "implied_prob": 1/away_odds, "platform": "sportbet"},
                    }
                }

        return markets

    def _extract_odds_value(self, data: Dict, keys: List[str]) -> Optional[float]:
        """Extract odds value from dict trying multiple keys."""
        for key in keys:
            value = data.get(key)
            if value is not None:
                return self._safe_float(value)
        return None

    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float."""
        if value is None:
            return None
        try:
            f = float(value)
            return f if f > 1 else None
        except (ValueError, TypeError):
            return None

    async def _scrape_main_page(self) -> List[Dict[str, Any]]:
        """Scrape events from main page."""
        events = []

        try:
            session = await self.get_session()
            async with session.get(self.BASE_URL, headers=self._get_default_headers()) as response:
                if response.status != 200:
                    return events

                html = await response.text()
                events = self._parse_html(html, "unknown")

        except Exception as e:
            self.logger.debug(f"Failed to scrape main page: {e}")

        return events

    async def _scrape_sport_page(self, sport: str) -> List[Dict[str, Any]]:
        """Scrape events from a specific sport page."""
        events = []
        urls_to_try = [
            f"{self.BASE_URL}/sports/{sport}",
            f"{self.BASE_URL}/{sport}",
            f"{self.BASE_URL}/sport/{sport}",
        ]

        for url in urls_to_try:
            try:
                session = await self.get_session()
                async with session.get(url, headers=self._get_default_headers()) as response:
                    if response.status == 200:
                        html = await response.text()
                        events = self._parse_html(html, sport)
                        if events:
                            return events
            except Exception:
                continue

        return events

    def _parse_html(self, html: str, sport: str) -> List[Dict[str, Any]]:
        """Parse events from HTML content."""
        events = []
        soup = BeautifulSoup(html, "lxml")

        # Look for event/match containers with various class patterns
        patterns = [
            r"event|match|game|fixture",
            r"bet-item|betting-event",
            r"match-row|event-row",
        ]

        for pattern in patterns:
            containers = soup.find_all(["div", "tr", "li"], class_=re.compile(pattern, re.I))

            for container in containers:
                try:
                    event = self._parse_html_event(container, sport)
                    if event:
                        events.append(event)
                except Exception:
                    continue

            if events:
                break

        return events

    def _parse_html_event(self, element, sport: str) -> Optional[Dict[str, Any]]:
        """Parse a single event from HTML element."""
        try:
            # Find team names
            team_elements = element.find_all(class_=re.compile(r"team|participant|player|name", re.I))

            teams = []
            for el in team_elements:
                text = el.get_text(strip=True)
                if text and len(text) > 1 and not text.replace(".", "").isdigit():
                    teams.append(text)

            if len(teams) < 2:
                return None

            home_team = teams[0]
            away_team = teams[1]

            # Find odds
            odds_elements = element.find_all(class_=re.compile(r"odd|coef|price|rate", re.I))
            odds_values = []

            for el in odds_elements:
                text = el.get_text(strip=True)
                match = re.search(r'\d+\.?\d*', text)
                if match:
                    val = float(match.group())
                    if val > 1:
                        odds_values.append(val)

            if len(odds_values) < 2:
                return None

            # Build markets
            markets = {}
            if len(odds_values) >= 3:
                markets["1x2"] = {
                    "market_type": "1x2",
                    "outcomes": {
                        "home": {"outcome": "home", "decimal_odds": odds_values[0], "implied_prob": 1/odds_values[0], "platform": "sportbet"},
                        "draw": {"outcome": "draw", "decimal_odds": odds_values[1], "implied_prob": 1/odds_values[1], "platform": "sportbet"},
                        "away": {"outcome": "away", "decimal_odds": odds_values[2], "implied_prob": 1/odds_values[2], "platform": "sportbet"},
                    }
                }
            else:
                markets["moneyline"] = {
                    "market_type": "moneyline",
                    "outcomes": {
                        "home": {"outcome": "home", "decimal_odds": odds_values[0], "implied_prob": 1/odds_values[0], "platform": "sportbet"},
                        "away": {"outcome": "away", "decimal_odds": odds_values[1], "implied_prob": 1/odds_values[1], "platform": "sportbet"},
                    }
                }

            event_id = element.get("data-id") or element.get("id") or f"{home_team}_{away_team}".replace(" ", "_")[:20]

            return {
                "event_id": f"sportbet_{event_id}",
                "platform": "sportbet",
                "sport": sport,
                "league": "Unknown",
                "home_team": home_team,
                "away_team": away_team,
                "home_team_normalized": self.normalize_team_name(home_team),
                "away_team_normalized": self.normalize_team_name(away_team),
                "start_time": datetime.now(timezone.utc),
                "markets": markets,
                "url": self.BASE_URL,
                "raw_data": {},
            }

        except Exception:
            return None

    def parse_event(self, raw_event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse event - delegates to API parser."""
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
