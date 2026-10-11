"""
Test script for AzuroScraper.

Fetches soccer events and validates data structure.
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# Required fields for validation
REQUIRED_EVENT_FIELDS = [
    "event_id",
    "platform",
    "sport",
    "league",
    "home_team",
    "away_team",
    "start_time",
    "markets",
]

REQUIRED_OUTCOME_FIELDS = [
    "outcome",
    "decimal_odds",
    "implied_prob",
    "platform",
]


def validate_event(event: Dict[str, Any]) -> List[str]:
    """
    Validate an event's data structure.

    Args:
        event: Event dict to validate

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Check required fields
    for field in REQUIRED_EVENT_FIELDS:
        if field not in event:
            errors.append(f"Missing required field: {field}")

    # Validate event_id
    if "event_id" in event and not event["event_id"]:
        errors.append("event_id is empty")

    # Validate platform
    if event.get("platform") != "azuro":
        errors.append(f"Unexpected platform: {event.get('platform')}")

    # Validate start_time
    start_time = event.get("start_time")
    if start_time:
        if not isinstance(start_time, datetime):
            errors.append(f"start_time is not datetime: {type(start_time)}")
        elif start_time < datetime.now(timezone.utc):
            errors.append("start_time is in the past")

    # Validate markets
    markets = event.get("markets", {})
    if not markets:
        errors.append("No markets found")
    else:
        for market_type, market in markets.items():
            market_errors = validate_market(market_type, market)
            errors.extend(market_errors)

    return errors


def validate_market(market_type: str, market: Dict[str, Any]) -> List[str]:
    """Validate a market's data structure."""
    errors = []

    if "outcomes" not in market:
        errors.append(f"Market '{market_type}' missing outcomes")
        return errors

    outcomes = market["outcomes"]

    # Check expected outcomes based on market type
    if market_type == "1x2":
        expected = {"home", "draw", "away"}
        actual = set(outcomes.keys())
        if actual != expected:
            errors.append(f"1x2 market has outcomes {actual}, expected {expected}")

    elif market_type == "moneyline":
        expected = {"home", "away"}
        actual = set(outcomes.keys())
        if actual != expected:
            errors.append(f"Moneyline market has outcomes {actual}, expected {expected}")

    # Validate each outcome
    for outcome_name, outcome_data in outcomes.items():
        outcome_errors = validate_outcome(outcome_name, outcome_data)
        errors.extend(outcome_errors)

    return errors


def validate_outcome(name: str, outcome: Dict[str, Any]) -> List[str]:
    """Validate an outcome's data structure."""
    errors = []

    for field in REQUIRED_OUTCOME_FIELDS:
        if field not in outcome:
            errors.append(f"Outcome '{name}' missing field: {field}")

    # Validate odds value
    odds = outcome.get("decimal_odds")
    if odds is not None:
        if not isinstance(odds, (int, float)):
            errors.append(f"Outcome '{name}' odds is not numeric: {type(odds)}")
        elif odds < 1.01:
            errors.append(f"Outcome '{name}' odds too low: {odds}")
        elif odds > 100:
            errors.append(f"Outcome '{name}' odds too high: {odds}")

    # Validate implied probability
    prob = outcome.get("implied_prob")
    if prob is not None:
        if not isinstance(prob, (int, float)):
            errors.append(f"Outcome '{name}' implied_prob is not numeric")
        elif not 0 < prob < 1:
            errors.append(f"Outcome '{name}' implied_prob out of range: {prob}")

    return errors


def print_event(event: Dict[str, Any], index: int) -> None:
    """Pretty print an event."""
    print(f"\n{'='*60}")
    print(f"EVENT #{index + 1}")
    print(f"{'='*60}")
    print(f"ID:      {event.get('event_id')}")
    print(f"Sport:   {event.get('sport')}")
    print(f"League:  {event.get('league')}")
    print(f"Match:   {event.get('home_team')} vs {event.get('away_team')}")
    print(f"Time:    {event.get('start_time').strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"URL:     {event.get('url', 'N/A')}")

    # Print markets and odds
    markets = event.get("markets", {})
    for market_type, market in markets.items():
        print(f"\n  Market: {market_type.upper()}")
        outcomes = market.get("outcomes", {})

        # Calculate total implied probability
        total_prob = sum(o.get("implied_prob", 0) for o in outcomes.values())
        margin = (total_prob - 1) * 100

        for outcome_name, outcome_data in outcomes.items():
            odds = outcome_data.get("decimal_odds", 0)
            prob = outcome_data.get("implied_prob", 0)
            print(f"    {outcome_name:>6}: {odds:>6.2f} ({prob:.1%})")

        print(f"    {'':>6}  Margin: {margin:.1f}%")


async def test_azuro_scraper():
    """Main test function."""
    print("\n" + "=" * 60)
    print("AZURO SCRAPER TEST")
    print("=" * 60)

    # Import scraper
    try:
        from scrapers import AzuroScraper
        logger.info("✓ Successfully imported AzuroScraper")
    except ImportError as e:
        logger.error(f"✗ Failed to import AzuroScraper: {e}")
        return False

    # Initialize scraper - fetch all sports to see what's available
    config = {
        "name": "Azuro",
        "chain": "polygon",
        # Include all common sports (Azuro uses various naming)
        "enabled_sports": [
            "football", "soccer", "basketball", "tennis",
            "ice hockey", "hockey", "baseball", "mma", "boxing",
            "esports", "american football", "cricket", "rugby",
        ],
        "refresh_interval": 30,
    }

    scraper = AzuroScraper(config)
    logger.info(f"✓ Initialized scraper for {config['chain']} chain")

    try:
        # First, let's do a raw query to see what sports are available
        logger.info("Testing raw GraphQL query...")
        from gql import gql
        from datetime import datetime, timezone

        # Query more games and check for Created status
        raw_query = gql("""
        query GetGames($startsAt: BigInt!) {
          games(where: {startsAt_gt: $startsAt}, first: 50) {
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

        # Use timestamp from an hour ago to ensure we get some events
        now_ts = int(datetime.now(timezone.utc).timestamp()) - 3600
        logger.info(f"Query timestamp: {now_ts} ({datetime.fromtimestamp(now_ts, tz=timezone.utc)})")
        client = await scraper._get_gql_client()

        async with client as session:
            result = await session.execute(raw_query, variable_values={"startsAt": str(now_ts)})
            raw_games = result.get("games", [])
            logger.info(f"Raw query returned {len(raw_games)} games")

            if raw_games:
                print("\nSample raw games:")
                for i, game in enumerate(raw_games[:3]):
                    sport = game.get("sport", {}).get("name", "Unknown")
                    title = game.get("title", "No title")
                    status = game.get("status", "Unknown")
                    conditions = game.get("conditions", [])
                    print(f"  {i+1}. [{sport}] {title}")
                    print(f"      Status: {status}, Conditions: {len(conditions)}")
                    if conditions:
                        for j, cond in enumerate(conditions[:2]):
                            outcomes = cond.get("outcomes", [])
                            print(f"      Condition {j+1}: {len(outcomes)} outcomes")
                            for out in outcomes[:3]:
                                print(f"        - outcomeId: {out.get('outcomeId')}, odds: {out.get('currentOdds')}")

                # Show unique sports
                sports = set(g.get("sport", {}).get("name", "Unknown") for g in raw_games)
                print(f"\nSports found: {sports}")

        # Fetch events through scraper
        logger.info("\nFetching events through scraper...")
        events = await scraper.fetch_events()
        logger.info(f"✓ Fetched {len(events)} events")

        if not events:
            logger.warning("No events found. This might be normal if no soccer games are scheduled.")
            return True

        # Filter events for next 24 hours
        now = datetime.now(timezone.utc)
        next_24h = now + timedelta(hours=24)

        upcoming_events = [
            e for e in events
            if e.get("start_time") and e["start_time"] <= next_24h
        ]
        logger.info(f"✓ {len(upcoming_events)} events in next 24 hours")

        # Validate and print first 5 events
        print("\n" + "-" * 60)
        print("FIRST 5 EVENTS (or all if fewer)")
        print("-" * 60)

        valid_count = 0
        invalid_count = 0
        events_to_show = upcoming_events[:5] if upcoming_events else events[:5]

        for i, event in enumerate(events_to_show):
            # Validate
            errors = validate_event(event)

            if errors:
                invalid_count += 1
                print(f"\n⚠️  Event #{i+1} has validation errors:")
                for error in errors:
                    print(f"    - {error}")
            else:
                valid_count += 1

            # Print event details
            print_event(event, i)

        # Summary
        print("\n" + "=" * 60)
        print("VALIDATION SUMMARY")
        print("=" * 60)
        print(f"Total events fetched:  {len(events)}")
        print(f"Events in next 24h:    {len(upcoming_events)}")
        print(f"Events validated:      {len(events_to_show)}")
        print(f"  ✓ Valid:             {valid_count}")
        print(f"  ✗ Invalid:           {invalid_count}")

        # Validate all events (not just displayed ones)
        all_errors = 0
        for event in events:
            errors = validate_event(event)
            if errors:
                all_errors += 1

        print(f"\nFull validation: {len(events) - all_errors}/{len(events)} events valid")

        if all_errors == 0:
            logger.info("✓ All events passed validation!")
            return True
        else:
            logger.warning(f"⚠ {all_errors} events have validation issues")
            return False

    except Exception as e:
        logger.error(f"✗ Error during test: {e}", exc_info=True)
        return False

    finally:
        # Cleanup
        await scraper.close()
        logger.info("✓ Scraper closed")


async def main():
    """Run the test."""
    success = await test_azuro_scraper()

    print("\n" + "=" * 60)
    if success:
        print("TEST RESULT: ✓ PASSED")
    else:
        print("TEST RESULT: ✗ FAILED")
    print("=" * 60 + "\n")

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
