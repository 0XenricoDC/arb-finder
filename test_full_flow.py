"""
Test the full arbitrage flow with simulated events.
"""

import asyncio
import sys
from datetime import datetime, timezone, timedelta

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

from core import EventMatcher, ArbitrageCalculator
from notifications import ArbNotifier
from config.settings import TELEGRAM_CONFIG


async def test_full_flow():
    """Test the complete flow with simulated events."""
    print("=" * 60)
    print("FULL FLOW TEST - Simulated Arbitrage")
    print("=" * 60)

    # Simulated events from two platforms with arbitrage opportunity
    azuro_events = [
        {
            "event_id": "azuro_test_001",
            "platform": "azuro",
            "sport": "soccer",
            "league": "Serie A",
            "home_team": "Inter Milan",
            "away_team": "AC Milan",
            "home_team_normalized": "inter",
            "away_team_normalized": "milan",
            "start_time": datetime.now(timezone.utc) + timedelta(hours=2),
            "markets": {
                "1x2": {
                    "market_type": "1x2",
                    "outcomes": {
                        "home": {"outcome": "home", "decimal_odds": 2.20, "implied_prob": 0.454, "platform": "azuro"},
                        "draw": {"outcome": "draw", "decimal_odds": 3.80, "implied_prob": 0.263, "platform": "azuro"},
                        "away": {"outcome": "away", "decimal_odds": 3.50, "implied_prob": 0.286, "platform": "azuro"},
                    }
                }
            },
            "url": "https://azuro.org/test",
        }
    ]

    overtime_events = [
        {
            "event_id": "overtime_test_001",
            "platform": "overtime",
            "sport": "soccer",
            "league": "Italian Serie A",
            "home_team": "Inter",
            "away_team": "Milan",
            "home_team_normalized": "inter",
            "away_team_normalized": "milan",
            "start_time": datetime.now(timezone.utc) + timedelta(hours=2),
            "markets": {
                "1x2": {
                    "market_type": "1x2",
                    "outcomes": {
                        # Higher odds on Overtime = arbitrage opportunity
                        "home": {"outcome": "home", "decimal_odds": 2.15, "implied_prob": 0.465, "platform": "overtime"},
                        "draw": {"outcome": "draw", "decimal_odds": 4.00, "implied_prob": 0.250, "platform": "overtime"},
                        "away": {"outcome": "away", "decimal_odds": 4.50, "implied_prob": 0.222, "platform": "overtime"},
                    }
                }
            },
            "url": "https://overtime.com/test",
        }
    ]

    print("\n1. MATCHING EVENTS")
    print("-" * 40)

    matcher = EventMatcher(fuzzy_threshold=85)
    events_by_platform = {
        "azuro": azuro_events,
        "overtime": overtime_events,
    }

    matched = matcher.match_all(events_by_platform)
    print(f"   Matched events: {len(matched)}")

    if matched:
        m = matched[0]
        print(f"   Match: {m.home_team} vs {m.away_team}")
        print(f"   Platforms: {m.get_platforms()}")

    print("\n2. CALCULATING ARBITRAGE")
    print("-" * 40)

    calculator = ArbitrageCalculator(
        min_profit_percent=0.5,
        max_profit_percent=20.0,
        default_stake=100.0,
    )

    opportunities = calculator.find_all_arbitrage(matched)
    print(f"   Opportunities found: {len(opportunities)}")

    if opportunities:
        arb = opportunities[0]
        print(f"\n   ARBITRAGE FOUND!")
        print(f"   Profit: {arb.profit_percent:.2f}%")
        print(f"   Total stake: EUR {arb.total_stake}")
        print(f"   Guaranteed profit: EUR {arb.guaranteed_profit:.2f}")
        print(f"\n   Legs:")
        for leg in arb.legs:
            print(f"     - {leg.outcome.upper()}: {leg.odds:.2f} @ {leg.platform}")
            print(f"       Stake: EUR {leg.stake:.2f} -> Return: EUR {leg.potential_return:.2f}")

        print("\n3. SENDING TELEGRAM ALERT")
        print("-" * 40)

        notifier = ArbNotifier(
            bot_token=TELEGRAM_CONFIG["bot_token"],
            chat_id=str(TELEGRAM_CONFIG["chat_id"]),
        )

        sent = await notifier.send_alert(arb)
        print(f"   Alert sent: {sent}")

        if sent:
            print("\n   CHECK YOUR TELEGRAM!")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_full_flow())
