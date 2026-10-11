"""
Data models for the arbitrage finder.

Defines standardized data structures for events, markets, odds, and matches.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class Sport(Enum):
    """Supported sports."""
    SOCCER = "soccer"
    BASKETBALL = "basketball"
    TENNIS = "tennis"
    HOCKEY = "hockey"
    BASEBALL = "baseball"
    MMA = "mma"
    ESPORTS = "esports"
    UNKNOWN = "unknown"


class MarketType(Enum):
    """Supported market types."""
    MONEYLINE = "moneyline"  # 2-way (home/away)
    ONE_X_TWO = "1x2"        # 3-way (home/draw/away)
    OVER_UNDER = "over_under"
    SPREAD = "spread"


@dataclass
class OddsEntry:
    """Odds for a single outcome from a platform."""
    platform: str
    outcome: str              # "home", "away", "draw", "over", "under"
    decimal_odds: float
    implied_prob: float
    timestamp: datetime = field(default_factory=lambda: datetime.utcnow())
    liquidity: Optional[float] = None
    max_stake: Optional[float] = None
    url: Optional[str] = None


@dataclass
class Market:
    """A betting market with outcomes and odds."""
    market_type: MarketType
    outcomes: Dict[str, OddsEntry]  # outcome_name -> OddsEntry
    line: Optional[float] = None    # For over/under, spread


@dataclass
class Event:
    """A sports event from a single platform."""
    event_id: str
    platform: str
    sport: str
    league: str
    home_team: str
    away_team: str
    home_team_normalized: str
    away_team_normalized: str
    start_time: datetime
    markets: Dict[str, Any]
    url: Optional[str] = None
    raw_data: Optional[Dict] = None


@dataclass
class MatchedEvent:
    """
    An event matched across multiple platforms.

    Contains the canonical event info and odds from all platforms.
    """
    match_id: str
    sport: str
    league: str
    home_team: str
    away_team: str
    start_time: datetime

    # Source events from each platform
    platform_events: Dict[str, Event] = field(default_factory=dict)

    # Combined odds: market_type -> outcome -> List[OddsEntry]
    combined_odds: Dict[str, Dict[str, List[OddsEntry]]] = field(default_factory=dict)

    # Best odds per outcome: market_type -> outcome -> OddsEntry
    best_odds: Dict[str, Dict[str, OddsEntry]] = field(default_factory=dict)

    # Match quality score (0-100)
    match_score: float = 0.0

    def add_platform_event(self, event: Event) -> None:
        """Add an event from a platform to this matched event."""
        self.platform_events[event.platform] = event
        self._update_combined_odds(event)
        self._update_best_odds()

    def _update_combined_odds(self, event: Event) -> None:
        """Update combined odds with odds from an event."""
        for market_type, market_data in event.markets.items():
            if market_type not in self.combined_odds:
                self.combined_odds[market_type] = {}

            outcomes = market_data.get("outcomes", {})
            for outcome_name, outcome_data in outcomes.items():
                if outcome_name not in self.combined_odds[market_type]:
                    self.combined_odds[market_type][outcome_name] = []

                odds_entry = OddsEntry(
                    platform=event.platform,
                    outcome=outcome_name,
                    decimal_odds=outcome_data["decimal_odds"],
                    implied_prob=outcome_data.get("implied_prob", 1/outcome_data["decimal_odds"]),
                    url=event.url,
                )
                self.combined_odds[market_type][outcome_name].append(odds_entry)

    def _update_best_odds(self) -> None:
        """Update best odds for each outcome across all platforms."""
        for market_type, outcomes in self.combined_odds.items():
            if market_type not in self.best_odds:
                self.best_odds[market_type] = {}

            for outcome_name, odds_list in outcomes.items():
                if odds_list:
                    # Best odds = highest decimal odds
                    best = max(odds_list, key=lambda x: x.decimal_odds)
                    self.best_odds[market_type][outcome_name] = best

    def get_platforms(self) -> List[str]:
        """Get list of platforms that have this event."""
        return list(self.platform_events.keys())

    def get_best_odds_for_market(self, market_type: str) -> Dict[str, float]:
        """Get best odds for each outcome in a market."""
        if market_type not in self.best_odds:
            return {}
        return {
            outcome: entry.decimal_odds
            for outcome, entry in self.best_odds[market_type].items()
        }


@dataclass
class ArbLeg:
    """A single leg of an arbitrage bet."""
    platform: str
    outcome: str
    odds: float
    stake: float
    potential_return: float
    url: Optional[str] = None


@dataclass
class ArbitrageOpportunity:
    """A detected arbitrage opportunity."""
    opportunity_id: str
    matched_event: MatchedEvent
    market_type: str
    legs: List[ArbLeg]
    total_implied_prob: float   # Sum of 1/odds (< 1.0 means profit)
    profit_percent: float       # (1 - total_implied_prob) * 100
    total_stake: float
    guaranteed_profit: float
    found_at: datetime = field(default_factory=lambda: datetime.utcnow())
    expires_at: Optional[datetime] = None

    @property
    def is_valid(self) -> bool:
        """Check if arbitrage is still valid (profitable)."""
        return self.profit_percent > 0
