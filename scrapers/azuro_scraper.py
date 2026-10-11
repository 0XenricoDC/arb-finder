"""
Azuro Protocol scraper for fetching odds from the Polygon subgraph.

Azuro is a decentralized betting protocol that exposes odds data via
a GraphQL subgraph on The Graph.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import logging

from gql import gql, Client
from gql.transport.aiohttp import AIOHTTPTransport
from gql.transport.exceptions import TransportQueryError

from scrapers.base_scraper import BaseScraper, ScraperError, ParseError


logger = logging.getLogger(__name__)


# GraphQL query for fetching upcoming games with odds
GAMES_QUERY = gql("""
query GetGames($startsAt: BigInt!) {
  games(where: {startsAt_gt: $startsAt}, first: 100) {
    gameId
    title
    startsAt
    status
    sport { name }
    league { name, country { name } }
    participants { name }
    conditions { outcomes { outcomeId, currentOdds } }
  }
}
""")


# Mapping of Azuro outcome IDs to standardized outcome names
# These vary by market type
OUTCOME_MAP_1X2 = {
    "1": "home",
    "2": "away",
    "3": "draw",
}

OUTCOME_MAP_MONEYLINE = {
    "1": "home",
    "2": "away",
}

# Sport name mapping to standardized names
# Azuro returns sport names like "Football", "Ice Hockey", etc.
SPORT_MAP = {
    "football": "soccer",
    "soccer": "soccer",
    "basketball": "basketball",
    "tennis": "tennis",
    "esports": "esports",
    "mma": "mma",
    "boxing": "boxing",
    "ice hockey": "hockey",
    "hockey": "hockey",
    "american football": "american football",
    "baseball": "baseball",
    "cricket": "cricket",
    "rugby": "rugby",
}


class AzuroScraper(BaseScraper):
    """
    Scraper for Azuro Protocol betting odds.

    Fetches data from the Azuro GraphQL subgraph on Polygon.
    """

    # Default subgraph endpoints by chain
    SUBGRAPH_URLS = {
        "polygon": "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-polygon-v3",
        "gnosis": "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-gnosis-v3",
        "arbitrum": "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-arbitrum-one-v3",
        "linea": "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-linea-v3",
    }

    # Azuro stores odds as raw integers, divide by this to get decimal
    ODDS_PRECISION = 10 ** 12

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Azuro scraper.

        Args:
            config: Platform configuration dict with keys:
                - subgraph: GraphQL endpoint URL (optional, defaults to polygon)
                - chain: Chain name for default subgraph selection
                - enabled_sports: List of sports to fetch
        """
        super().__init__(config)

        # Determine subgraph URL
        chain = config.get("chain", "polygon")
        self.subgraph_url = config.get(
            "subgraph",
            self.SUBGRAPH_URLS.get(chain, self.SUBGRAPH_URLS["polygon"])
        )

        # Sports to fetch (using Azuro's slug format)
        self.enabled_sports = config.get("enabled_sports", ["football", "basketball", "tennis"])

        # GraphQL client (initialized lazily)
        self._gql_client: Optional[Client] = None

        self.logger.info(f"Initialized Azuro scraper for {chain} chain")

    async def _get_gql_client(self) -> Client:
        """Get or create the GraphQL client."""
        if self._gql_client is None:
            transport = AIOHTTPTransport(
                url=self.subgraph_url,
                headers=self._get_default_headers(),
            )
            self._gql_client = Client(
                transport=transport,
                fetch_schema_from_transport=False,
            )
        return self._gql_client

    async def close(self) -> None:
        """Close all connections."""
        if self._gql_client:
            await self._gql_client.close_async()
            self._gql_client = None
        await super().close()

    async def fetch_events(self) -> List[Dict[str, Any]]:
        """
        Fetch all upcoming events from Azuro.

        Returns:
            List of parsed event dictionaries

        Raises:
            ScraperError: If fetching fails
        """
        all_events = []

        try:
            client = await self._get_gql_client()

            # Current timestamp for filtering
            now_timestamp = int(datetime.now(timezone.utc).timestamp())

            async with client as session:
                self.logger.debug("Fetching games from Azuro")

                variables = {"startsAt": str(now_timestamp)}

                result = await session.execute(GAMES_QUERY, variable_values=variables)
                games = result.get("games", [])

                # Parse each game
                for raw_game in games:
                    try:
                        parsed = self.parse_event(raw_game)
                        if parsed:
                            # Filter by enabled sports
                            if parsed["sport"].lower() in [s.lower() for s in self.enabled_sports]:
                                all_events.append(parsed)
                    except ParseError as e:
                        self.logger.warning(f"Failed to parse game {raw_game.get('gameId')}: {e}")
                        continue

            self.logger.info(f"Fetched {len(all_events)} events from Azuro")
            return all_events

        except TransportQueryError as e:
            self.logger.error(f"GraphQL query error: {e}")
            raise ScraperError(f"Azuro GraphQL query failed: {e}")
        except Exception as e:
            self.logger.error(f"Error fetching from Azuro: {e}")
            raise ScraperError(f"Failed to fetch from Azuro: {e}")

    def parse_event(self, raw_event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse a raw Azuro game into standardized event format.

        Args:
            raw_event: Raw game data from GraphQL response

        Returns:
            Standardized event dict or None if invalid

        Raises:
            ParseError: If critical parsing fails
        """
        try:
            game_id = raw_event.get("gameId")
            if not game_id:
                raise ParseError("Missing gameId")

            # Extract participants (home/away teams)
            # First participant is home, second is away
            participants = raw_event.get("participants", [])
            if len(participants) < 2:
                self.logger.debug(f"Game {game_id} has < 2 participants, skipping")
                return None

            home_team = participants[0].get("name", "Unknown")
            away_team = participants[1].get("name", "Unknown")

            # Parse sport
            sport_data = raw_event.get("sport", {})
            sport_name = sport_data.get("name", "unknown").lower()
            sport = SPORT_MAP.get(sport_name, sport_name)

            # Parse league
            league_data = raw_event.get("league", {})
            league_name = league_data.get("name", "Unknown League")
            country = league_data.get("country", {}).get("name", "")
            league = f"{country} - {league_name}" if country else league_name

            # Parse start time
            starts_at = raw_event.get("startsAt")
            if starts_at:
                start_time = datetime.fromtimestamp(int(starts_at), tz=timezone.utc)
            else:
                raise ParseError(f"Missing startsAt for game {game_id}")

            # Parse markets and odds from conditions
            markets = self._parse_conditions(raw_event.get("conditions", []))

            if not markets:
                self.logger.debug(f"Game {game_id} has no valid markets, skipping")
                return None

            return {
                "event_id": f"azuro_{game_id}",
                "platform": "azuro",
                "sport": sport,
                "league": league,
                "home_team": home_team,
                "away_team": away_team,
                "home_team_normalized": self.normalize_team_name(home_team),
                "away_team_normalized": self.normalize_team_name(away_team),
                "start_time": start_time,
                "markets": markets,
                "url": f"https://azuro.org/events/{game_id}",
                "raw_data": raw_event,
            }

        except ParseError:
            raise
        except Exception as e:
            raise ParseError(f"Failed to parse event: {e}")

    def _parse_conditions(self, conditions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Parse Azuro conditions into market odds.

        Azuro uses "conditions" to represent different betting markets.
        Each condition has outcomes with odds.

        Args:
            conditions: List of condition dicts from API

        Returns:
            Dict of market_type -> market data
        """
        markets = {}

        for condition in conditions:
            outcomes = condition.get("outcomes", [])

            if not outcomes:
                continue

            # Determine market type based on number of outcomes
            num_outcomes = len(outcomes)

            if num_outcomes == 3:
                # 1X2 market (home/draw/away)
                market_type = "1x2"
                outcome_map = OUTCOME_MAP_1X2
            elif num_outcomes == 2:
                # Moneyline or other 2-way market
                market_type = "moneyline"
                outcome_map = OUTCOME_MAP_MONEYLINE
            else:
                # Skip complex markets for now
                continue

            # Parse odds for each outcome
            parsed_outcomes = {}

            # Define outcome names based on position for markets with non-standard IDs
            if num_outcomes == 2:
                position_names = ["home", "away"]
            elif num_outcomes == 3:
                position_names = ["home", "draw", "away"]
            else:
                position_names = [f"outcome_{i}" for i in range(num_outcomes)]

            for idx, outcome in enumerate(outcomes):
                outcome_id = str(outcome.get("outcomeId"))
                raw_odds = outcome.get("currentOdds")

                if raw_odds is None:
                    continue

                # Convert from raw format to decimal
                try:
                    decimal_odds = self._convert_raw_odds(raw_odds)
                except (ValueError, TypeError):
                    continue

                # Skip invalid odds
                if decimal_odds < 1.01 or decimal_odds > 100:
                    continue

                # Try standard mapping first, fall back to position-based naming
                outcome_name = outcome_map.get(outcome_id)
                if outcome_name is None and idx < len(position_names):
                    outcome_name = position_names[idx]
                elif outcome_name is None:
                    outcome_name = f"outcome_{outcome_id}"

                parsed_outcomes[outcome_name] = {
                    "outcome": outcome_name,
                    "decimal_odds": decimal_odds,
                    "implied_prob": self.calculate_implied_probability(decimal_odds),
                    "platform": "azuro",
                    "outcome_id": outcome_id,
                }

            # Only add market if we have all expected outcomes
            if market_type == "1x2" and len(parsed_outcomes) == 3:
                markets[market_type] = {
                    "market_type": market_type,
                    "outcomes": parsed_outcomes,
                }
            elif market_type == "moneyline" and len(parsed_outcomes) == 2:
                markets[market_type] = {
                    "market_type": market_type,
                    "outcomes": parsed_outcomes,
                }

        return markets

    def _convert_raw_odds(self, raw_odds: Any) -> float:
        """
        Convert Azuro odds to decimal format.

        Azuro may return odds in different formats:
        - Decimal format (1.0 - 100.0): Already in usable format
        - Raw integer format (10^12 scale): Needs division

        Args:
            raw_odds: Raw odds value (string, int, or float)

        Returns:
            Decimal odds (e.g., 2.50)
        """
        # Handle string input
        if isinstance(raw_odds, str):
            raw_odds = float(raw_odds)

        # If odds are already in decimal format (reasonable range), use directly
        if 1.0 < raw_odds < 1000.0:
            return round(raw_odds, 3)

        # Otherwise, assume raw format and divide by precision
        decimal_odds = raw_odds / self.ODDS_PRECISION
        return round(decimal_odds, 3)

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
                    "platform": "azuro",
                    "implied_prob": outcome_data["implied_prob"],
                }

        return result
