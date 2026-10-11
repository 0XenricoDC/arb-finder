"""
Core modules for arbitrage detection.
"""

from core.models import (
    Sport,
    MarketType,
    OddsEntry,
    Market,
    Event,
    MatchedEvent,
    ArbLeg,
    ArbitrageOpportunity,
)
from core.matcher import EventMatcher, TEAM_ALIASES
from core.calculator import ArbitrageCalculator

__all__ = [
    # Models
    "Sport",
    "MarketType",
    "OddsEntry",
    "Market",
    "Event",
    "MatchedEvent",
    "ArbLeg",
    "ArbitrageOpportunity",
    # Matcher
    "EventMatcher",
    "TEAM_ALIASES",
    # Calculator
    "ArbitrageCalculator",
]
