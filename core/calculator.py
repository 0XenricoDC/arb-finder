"""
Arbitrage calculation engine.

Calculates arbitrage opportunities, optimal stakes, and expected profits
for matched events across betting platforms.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import uuid

from core.models import (
    MatchedEvent,
    ArbitrageOpportunity,
    ArbLeg,
    OddsEntry,
)


logger = logging.getLogger(__name__)


class ArbitrageCalculator:
    """
    Calculator for detecting and analyzing arbitrage opportunities.

    Supports 2-way (moneyline) and 3-way (1X2) markets.
    """

    # Default profit thresholds
    DEFAULT_MIN_PROFIT = 1.0    # Minimum profit % to consider
    DEFAULT_MAX_PROFIT = 20.0   # Maximum profit % (above likely error)
    DEFAULT_STAKE = 100.0       # Default total stake for calculations

    def __init__(
        self,
        min_profit_percent: float = DEFAULT_MIN_PROFIT,
        max_profit_percent: float = DEFAULT_MAX_PROFIT,
        default_stake: float = DEFAULT_STAKE,
    ):
        """
        Initialize the calculator.

        Args:
            min_profit_percent: Minimum profit % to report (filters noise)
            max_profit_percent: Maximum profit % to report (filters errors)
            default_stake: Default total stake for calculations
        """
        self.min_profit = min_profit_percent
        self.max_profit = max_profit_percent
        self.default_stake = default_stake

        self.logger = logging.getLogger(f"{__name__}.ArbitrageCalculator")

    def calculate_2way_arb(
        self,
        odds_a: float,
        odds_b: float,
    ) -> Tuple[bool, float]:
        """
        Calculate arbitrage for a 2-outcome market (moneyline).

        Args:
            odds_a: Decimal odds for outcome A (e.g., home win)
            odds_b: Decimal odds for outcome B (e.g., away win)

        Returns:
            Tuple of (is_arbitrage, profit_percent)
            - is_arbitrage: True if arbitrage opportunity exists
            - profit_percent: Guaranteed profit as percentage
        """
        if odds_a <= 1.0 or odds_b <= 1.0:
            return False, 0.0

        # Calculate implied probabilities
        implied_prob_a = 1 / odds_a
        implied_prob_b = 1 / odds_b
        total_implied = implied_prob_a + implied_prob_b

        # Arbitrage exists if total implied probability < 100%
        is_arb = total_implied < 1.0

        if is_arb:
            profit_percent = (1 - total_implied) * 100
        else:
            profit_percent = 0.0

        return is_arb, round(profit_percent, 4)

    def calculate_3way_arb(
        self,
        odds_home: float,
        odds_draw: float,
        odds_away: float,
    ) -> Tuple[bool, float]:
        """
        Calculate arbitrage for a 3-outcome market (1X2).

        Args:
            odds_home: Decimal odds for home win
            odds_draw: Decimal odds for draw
            odds_away: Decimal odds for away win

        Returns:
            Tuple of (is_arbitrage, profit_percent)
        """
        if odds_home <= 1.0 or odds_draw <= 1.0 or odds_away <= 1.0:
            return False, 0.0

        # Calculate implied probabilities
        implied_home = 1 / odds_home
        implied_draw = 1 / odds_draw
        implied_away = 1 / odds_away
        total_implied = implied_home + implied_draw + implied_away

        # Arbitrage exists if total implied probability < 100%
        is_arb = total_implied < 1.0

        if is_arb:
            profit_percent = (1 - total_implied) * 100
        else:
            profit_percent = 0.0

        return is_arb, round(profit_percent, 4)

    def calculate_nway_arb(self, odds_list: List[float]) -> Tuple[bool, float]:
        """
        Calculate arbitrage for any number of outcomes.

        Args:
            odds_list: List of decimal odds for each outcome

        Returns:
            Tuple of (is_arbitrage, profit_percent)
        """
        if not odds_list or any(o <= 1.0 for o in odds_list):
            return False, 0.0

        total_implied = sum(1 / o for o in odds_list)
        is_arb = total_implied < 1.0
        profit_percent = (1 - total_implied) * 100 if is_arb else 0.0

        return is_arb, round(profit_percent, 4)

    def calculate_optimal_stakes(
        self,
        total_stake: float,
        odds_list: List[float],
    ) -> List[float]:
        """
        Calculate optimal stake distribution for guaranteed profit.

        Distributes stakes such that any winning outcome returns the same amount.

        Formula: stake_i = total_stake / (odds_i * sum(1/odds_j for all j))

        Args:
            total_stake: Total amount to stake across all outcomes
            odds_list: List of decimal odds for each outcome

        Returns:
            List of stake amounts corresponding to each outcome
        """
        if not odds_list or any(o <= 1.0 for o in odds_list):
            return [0.0] * len(odds_list)

        # Calculate sum of implied probabilities
        total_implied = sum(1 / o for o in odds_list)

        # Calculate stake for each outcome
        stakes = []
        for odds in odds_list:
            stake = total_stake / (odds * total_implied)
            stakes.append(round(stake, 2))

        return stakes

    def calculate_returns(
        self,
        stakes: List[float],
        odds_list: List[float],
    ) -> List[float]:
        """
        Calculate potential returns for each outcome.

        Args:
            stakes: Stake amounts for each outcome
            odds_list: Decimal odds for each outcome

        Returns:
            List of potential returns for each outcome
        """
        returns = []
        for stake, odds in zip(stakes, odds_list):
            returns.append(round(stake * odds, 2))
        return returns

    def find_best_odds(
        self,
        matched_event: MatchedEvent,
        market_type: str = "1x2",
    ) -> Dict[str, OddsEntry]:
        """
        Find the best odds for each outcome across all platforms.

        Args:
            matched_event: Event matched across platforms
            market_type: Market type to analyze ("1x2", "moneyline")

        Returns:
            Dict mapping outcome name to best OddsEntry
        """
        # MatchedEvent already tracks best odds
        if market_type in matched_event.best_odds:
            return matched_event.best_odds[market_type]

        # Fallback: manually find best odds
        best = {}
        combined = matched_event.combined_odds.get(market_type, {})

        for outcome, odds_list in combined.items():
            if odds_list:
                best_entry = max(odds_list, key=lambda x: x.decimal_odds)
                best[outcome] = best_entry

        return best

    def find_arbitrage(
        self,
        matched_event: MatchedEvent,
    ) -> List[ArbitrageOpportunity]:
        """
        Find all arbitrage opportunities in a matched event.

        Args:
            matched_event: Event with odds from multiple platforms

        Returns:
            List of valid arbitrage opportunities
        """
        opportunities = []

        # Check each market type
        for market_type in matched_event.best_odds.keys():
            arb = self._check_market_arbitrage(matched_event, market_type)
            if arb:
                opportunities.append(arb)

        return opportunities

    def _check_market_arbitrage(
        self,
        matched_event: MatchedEvent,
        market_type: str,
    ) -> Optional[ArbitrageOpportunity]:
        """
        Check for arbitrage in a specific market.

        Args:
            matched_event: Matched event
            market_type: Market type to check

        Returns:
            ArbitrageOpportunity if found, None otherwise
        """
        best_odds = self.find_best_odds(matched_event, market_type)

        if not best_odds:
            return None

        # Get odds values
        odds_list = [entry.decimal_odds for entry in best_odds.values()]
        outcome_names = list(best_odds.keys())

        # Check for arbitrage based on market type
        if market_type == "1x2" and len(odds_list) == 3:
            # Ensure we have home, draw, away in correct order
            home_odds = best_odds.get("home")
            draw_odds = best_odds.get("draw")
            away_odds = best_odds.get("away")

            if not all([home_odds, draw_odds, away_odds]):
                return None

            is_arb, profit = self.calculate_3way_arb(
                home_odds.decimal_odds,
                draw_odds.decimal_odds,
                away_odds.decimal_odds,
            )

        elif market_type == "moneyline" and len(odds_list) == 2:
            home_odds = best_odds.get("home")
            away_odds = best_odds.get("away")

            if not all([home_odds, away_odds]):
                return None

            is_arb, profit = self.calculate_2way_arb(
                home_odds.decimal_odds,
                away_odds.decimal_odds,
            )

        else:
            # Generic n-way calculation
            is_arb, profit = self.calculate_nway_arb(odds_list)

        # Apply profit filters
        if not is_arb:
            return None

        if profit < self.min_profit:
            self.logger.debug(
                f"Profit {profit:.2f}% below minimum {self.min_profit}% for "
                f"{matched_event.home_team} vs {matched_event.away_team}"
            )
            return None

        if profit > self.max_profit:
            self.logger.warning(
                f"Profit {profit:.2f}% exceeds maximum {self.max_profit}% - "
                f"likely data error for {matched_event.home_team} vs {matched_event.away_team}"
            )
            return None

        # Calculate optimal stakes
        stakes = self.calculate_optimal_stakes(self.default_stake, odds_list)
        returns = self.calculate_returns(stakes, odds_list)

        # Build arbitrage legs
        legs = []
        for i, outcome in enumerate(outcome_names):
            entry = best_odds[outcome]
            legs.append(ArbLeg(
                platform=entry.platform,
                outcome=outcome,
                odds=entry.decimal_odds,
                stake=stakes[i],
                potential_return=returns[i],
                url=entry.url,
            ))

        # Calculate total implied probability
        total_implied = sum(1 / o for o in odds_list)
        guaranteed_return = returns[0] if returns else 0  # All returns should be equal
        guaranteed_profit = guaranteed_return - self.default_stake

        return ArbitrageOpportunity(
            opportunity_id=str(uuid.uuid4())[:8],
            matched_event=matched_event,
            market_type=market_type,
            legs=legs,
            total_implied_prob=round(total_implied, 4),
            profit_percent=round(profit, 2),
            total_stake=self.default_stake,
            guaranteed_profit=round(guaranteed_profit, 2),
            found_at=datetime.utcnow(),
            expires_at=matched_event.start_time,
        )

    def find_all_arbitrage(
        self,
        matched_events: List[MatchedEvent],
    ) -> List[ArbitrageOpportunity]:
        """
        Find arbitrage opportunities across all matched events.

        Args:
            matched_events: List of matched events

        Returns:
            List of all valid arbitrage opportunities, sorted by profit
        """
        all_opportunities = []

        for matched in matched_events:
            opportunities = self.find_arbitrage(matched)
            all_opportunities.extend(opportunities)

        # Sort by profit percentage (highest first)
        all_opportunities.sort(key=lambda x: x.profit_percent, reverse=True)

        self.logger.info(
            f"Found {len(all_opportunities)} arbitrage opportunities "
            f"from {len(matched_events)} matched events"
        )

        return all_opportunities

    def format_opportunity(self, arb: ArbitrageOpportunity) -> str:
        """
        Format an arbitrage opportunity as a readable string.

        Args:
            arb: Arbitrage opportunity to format

        Returns:
            Formatted string
        """
        lines = [
            f"{'='*50}",
            f"ARBITRAGE: {arb.profit_percent:.2f}% profit",
            f"{'='*50}",
            f"Event: {arb.matched_event.home_team} vs {arb.matched_event.away_team}",
            f"League: {arb.matched_event.league}",
            f"Market: {arb.market_type}",
            f"Start: {arb.matched_event.start_time.strftime('%Y-%m-%d %H:%M UTC')}",
            f"",
            f"Stakes (total: €{arb.total_stake:.2f}):",
        ]

        for leg in arb.legs:
            lines.append(
                f"  • {leg.outcome.upper()}: {leg.odds:.2f} @ {leg.platform}"
            )
            lines.append(
                f"    Stake: €{leg.stake:.2f} → Return: €{leg.potential_return:.2f}"
            )

        lines.extend([
            f"",
            f"Guaranteed profit: €{arb.guaranteed_profit:.2f}",
            f"Total implied prob: {arb.total_implied_prob:.4f}",
            f"{'='*50}",
        ])

        return "\n".join(lines)
