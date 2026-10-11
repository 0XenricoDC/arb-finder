"""
Unit tests for ArbitrageCalculator.

Tests arbitrage detection, stake calculation, and edge cases.
"""

import unittest
import sys
from datetime import datetime, timezone

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

from core.calculator import ArbitrageCalculator
from core.models import MatchedEvent, OddsEntry


class TestCalculate2WayArb(unittest.TestCase):
    """Tests for 2-way (moneyline) arbitrage calculation."""

    def setUp(self):
        self.calc = ArbitrageCalculator(
            min_profit_percent=0.5,
            max_profit_percent=20.0,
            default_stake=100.0,
        )

    def test_profitable_2way_arb(self):
        """Test detection of profitable 2-way arbitrage."""
        # Example: Home 2.20 + Away 2.10 = 0.454 + 0.476 = 0.93 < 1.0
        # Profit = 7%
        is_arb, profit = self.calc.calculate_2way_arb(2.20, 2.10)

        self.assertTrue(is_arb)
        self.assertAlmostEqual(profit, 6.9264, places=2)

    def test_marginal_2way_arb(self):
        """Test marginal arbitrage (small profit)."""
        # 1/1.95 + 1/1.95 = 0.513 + 0.513 = 1.026 > 1.0 (no arb)
        # But 1/2.05 + 1/2.05 = 0.488 + 0.488 = 0.976 < 1.0 (arb)
        is_arb, profit = self.calc.calculate_2way_arb(2.05, 2.05)

        self.assertTrue(is_arb)
        self.assertAlmostEqual(profit, 2.44, places=1)

    def test_no_arb_2way(self):
        """Test when no arbitrage exists (bookmaker margin)."""
        # Typical bookmaker odds with margin
        # 1/1.90 + 1/1.90 = 0.526 + 0.526 = 1.052 > 1.0
        is_arb, profit = self.calc.calculate_2way_arb(1.90, 1.90)

        self.assertFalse(is_arb)
        self.assertEqual(profit, 0.0)

    def test_no_arb_strong_favorite(self):
        """Test no arb with strong favorite."""
        # Heavy favorite: 1/1.10 + 1/6.00 = 0.909 + 0.167 = 1.076 > 1.0
        is_arb, profit = self.calc.calculate_2way_arb(1.10, 6.00)

        self.assertFalse(is_arb)
        self.assertEqual(profit, 0.0)


class TestCalculate3WayArb(unittest.TestCase):
    """Tests for 3-way (1X2) arbitrage calculation."""

    def setUp(self):
        self.calc = ArbitrageCalculator()

    def test_profitable_3way_arb(self):
        """Test detection of profitable 3-way arbitrage."""
        # Example from spec:
        # Home 2.20, Draw 3.80, Away 4.50
        # 1/2.20 + 1/3.80 + 1/4.50 = 0.455 + 0.263 + 0.222 = 0.94 < 1.0
        # Profit = 6%
        is_arb, profit = self.calc.calculate_3way_arb(2.20, 3.80, 4.50)

        self.assertTrue(is_arb)
        self.assertAlmostEqual(profit, 6.0, places=0)

    def test_marginal_3way_arb(self):
        """Test marginal 3-way arbitrage."""
        # 1/2.10 + 1/3.50 + 1/3.80 = 0.476 + 0.286 + 0.263 = 1.025 > 1.0 (no arb)
        is_arb, profit = self.calc.calculate_3way_arb(2.10, 3.50, 3.80)

        self.assertFalse(is_arb)
        self.assertEqual(profit, 0.0)

    def test_barely_profitable_3way(self):
        """Test barely profitable 3-way arbitrage."""
        # Craft odds that sum to just under 1.0
        # 1/2.15 + 1/3.60 + 1/4.10 = 0.465 + 0.278 + 0.244 = 0.987 < 1.0
        is_arb, profit = self.calc.calculate_3way_arb(2.15, 3.60, 4.10)

        self.assertTrue(is_arb)
        self.assertGreater(profit, 0)
        self.assertLess(profit, 2.0)

    def test_no_arb_3way_typical(self):
        """Test typical bookmaker odds with no arbitrage."""
        # Standard soccer odds with ~5% margin
        # 1/2.00 + 1/3.40 + 1/3.40 = 0.50 + 0.294 + 0.294 = 1.088 > 1.0
        is_arb, profit = self.calc.calculate_3way_arb(2.00, 3.40, 3.40)

        self.assertFalse(is_arb)
        self.assertEqual(profit, 0.0)


class TestOptimalStakes(unittest.TestCase):
    """Tests for optimal stake calculation."""

    def setUp(self):
        self.calc = ArbitrageCalculator(default_stake=100.0)

    def test_2way_stake_calculation(self):
        """Test stake calculation for 2-way market."""
        # Odds: 2.20, 2.10
        # Total implied: 1/2.20 + 1/2.10 = 0.4545 + 0.4762 = 0.9307
        stakes = self.calc.calculate_optimal_stakes(100.0, [2.20, 2.10])

        self.assertEqual(len(stakes), 2)

        # Verify stakes sum approximately to total
        self.assertAlmostEqual(sum(stakes), 100.0, delta=1.0)

        # Verify returns are equal for both outcomes
        returns = self.calc.calculate_returns(stakes, [2.20, 2.10])
        self.assertAlmostEqual(returns[0], returns[1], delta=0.5)

    def test_3way_stake_calculation(self):
        """Test stake calculation for 3-way market."""
        # Odds: 2.20, 3.80, 4.50
        stakes = self.calc.calculate_optimal_stakes(100.0, [2.20, 3.80, 4.50])

        self.assertEqual(len(stakes), 3)

        # Stakes should sum to approximately total
        self.assertAlmostEqual(sum(stakes), 100.0, delta=1.0)

        # All returns should be approximately equal
        returns = self.calc.calculate_returns(stakes, [2.20, 3.80, 4.50])
        self.assertAlmostEqual(returns[0], returns[1], delta=1.0)
        self.assertAlmostEqual(returns[1], returns[2], delta=1.0)

    def test_stake_proportions(self):
        """Test that stakes are inversely proportional to odds."""
        stakes = self.calc.calculate_optimal_stakes(100.0, [2.00, 4.00])

        # Higher odds should have lower stake
        self.assertGreater(stakes[0], stakes[1])

        # Stake ratio should be inverse of odds ratio
        # stake[0]/stake[1] should approximately equal odds[1]/odds[0]
        stake_ratio = stakes[0] / stakes[1]
        odds_ratio = 4.00 / 2.00
        self.assertAlmostEqual(stake_ratio, odds_ratio, delta=0.1)

    def test_returns_calculation(self):
        """Test return calculation accuracy."""
        stakes = [50.0, 30.0, 20.0]
        odds = [2.00, 3.50, 5.00]

        returns = self.calc.calculate_returns(stakes, odds)

        self.assertEqual(returns[0], 100.0)  # 50 * 2.00
        self.assertEqual(returns[1], 105.0)  # 30 * 3.50
        self.assertEqual(returns[2], 100.0)  # 20 * 5.00


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and error handling."""

    def setUp(self):
        self.calc = ArbitrageCalculator(
            min_profit_percent=1.0,
            max_profit_percent=20.0,
        )

    def test_invalid_odds_below_one(self):
        """Test handling of invalid odds below 1.0."""
        is_arb, profit = self.calc.calculate_2way_arb(0.5, 2.00)
        self.assertFalse(is_arb)
        self.assertEqual(profit, 0.0)

    def test_invalid_odds_zero(self):
        """Test handling of zero odds."""
        is_arb, profit = self.calc.calculate_2way_arb(0, 2.00)
        self.assertFalse(is_arb)

    def test_invalid_odds_negative(self):
        """Test handling of negative odds."""
        is_arb, profit = self.calc.calculate_3way_arb(-1.5, 3.00, 4.00)
        self.assertFalse(is_arb)

    def test_invalid_odds_one(self):
        """Test handling of odds equal to 1.0."""
        is_arb, profit = self.calc.calculate_2way_arb(1.0, 2.00)
        self.assertFalse(is_arb)

    def test_empty_odds_list(self):
        """Test handling of empty odds list for stakes."""
        stakes = self.calc.calculate_optimal_stakes(100.0, [])
        self.assertEqual(stakes, [])

    def test_nway_arb_generic(self):
        """Test generic n-way arbitrage calculation."""
        # 4-way market
        odds = [3.00, 3.00, 3.00, 3.00]
        # 4 * (1/3.00) = 4 * 0.333 = 1.333 > 1.0 (no arb)
        is_arb, profit = self.calc.calculate_nway_arb(odds)
        self.assertFalse(is_arb)

        # Profitable 4-way
        odds = [4.50, 4.50, 4.50, 4.50]
        # 4 * (1/4.50) = 4 * 0.222 = 0.889 < 1.0 (arb)
        is_arb, profit = self.calc.calculate_nway_arb(odds)
        self.assertTrue(is_arb)
        self.assertAlmostEqual(profit, 11.1, places=0)


class TestProfitFiltering(unittest.TestCase):
    """Tests for profit filtering logic."""

    def test_below_min_profit(self):
        """Test that opportunities below min_profit are filtered."""
        calc = ArbitrageCalculator(min_profit_percent=3.0)

        # Create a matched event with ~2.4% profit (below 3% threshold)
        # 1/2.05 + 1/2.05 = 0.976, profit = 2.4%
        matched = create_mock_matched_event(
            home_odds=2.05,
            away_odds=2.05,
            platform_home="azuro",
            platform_away="overtime",
        )

        opportunities = calc.find_arbitrage(matched)

        # Should be filtered out due to low profit (2.4% < 3%)
        self.assertEqual(len(opportunities), 0)

    def test_above_max_profit(self):
        """Test that opportunities above max_profit are filtered (likely errors)."""
        calc = ArbitrageCalculator(max_profit_percent=15.0)

        # Create event with suspiciously high profit (25%)
        matched = create_mock_matched_event(
            home_odds=3.00,
            away_odds=3.00,
            platform_home="azuro",
            platform_away="overtime",
        )

        opportunities = calc.find_arbitrage(matched)

        # 1/3.0 + 1/3.0 = 0.667 => 33% profit, should be filtered
        self.assertEqual(len(opportunities), 0)

    def test_valid_profit_range(self):
        """Test that valid profit opportunities are returned."""
        calc = ArbitrageCalculator(
            min_profit_percent=1.0,
            max_profit_percent=20.0,
        )

        # Create event with ~7% profit (within range)
        matched = create_mock_matched_event(
            home_odds=2.20,
            away_odds=2.10,
            platform_home="azuro",
            platform_away="overtime",
        )

        opportunities = calc.find_arbitrage(matched)

        self.assertEqual(len(opportunities), 1)
        self.assertGreater(opportunities[0].profit_percent, 1.0)
        self.assertLess(opportunities[0].profit_percent, 20.0)


class TestArbitrageOpportunityStructure(unittest.TestCase):
    """Tests for ArbitrageOpportunity data structure."""

    def setUp(self):
        self.calc = ArbitrageCalculator(
            min_profit_percent=0.5,
            max_profit_percent=50.0,
            default_stake=100.0,
        )

    def test_opportunity_has_required_fields(self):
        """Test that returned opportunities have all required fields."""
        matched = create_mock_matched_event(
            home_odds=2.20,
            away_odds=2.10,
            platform_home="azuro",
            platform_away="overtime",
        )

        opportunities = self.calc.find_arbitrage(matched)
        self.assertEqual(len(opportunities), 1)

        opp = opportunities[0]

        # Check required fields exist
        self.assertIsNotNone(opp.opportunity_id)
        self.assertIsNotNone(opp.matched_event)
        self.assertIsNotNone(opp.market_type)
        self.assertIsNotNone(opp.legs)
        self.assertIsNotNone(opp.total_implied_prob)
        self.assertIsNotNone(opp.profit_percent)
        self.assertIsNotNone(opp.total_stake)
        self.assertIsNotNone(opp.guaranteed_profit)

    def test_opportunity_legs_structure(self):
        """Test that opportunity legs have correct structure."""
        matched = create_mock_matched_event(
            home_odds=2.20,
            away_odds=2.10,
            platform_home="azuro",
            platform_away="overtime",
        )

        opportunities = self.calc.find_arbitrage(matched)
        opp = opportunities[0]

        self.assertEqual(len(opp.legs), 2)

        for leg in opp.legs:
            self.assertIn(leg.outcome, ["home", "away"])
            self.assertIn(leg.platform, ["azuro", "overtime"])
            self.assertGreater(leg.odds, 1.0)
            self.assertGreater(leg.stake, 0)
            self.assertGreater(leg.potential_return, 0)

    def test_guaranteed_profit_calculation(self):
        """Test that guaranteed profit is calculated correctly."""
        matched = create_mock_matched_event(
            home_odds=2.20,
            away_odds=2.10,
            platform_home="azuro",
            platform_away="overtime",
        )

        opportunities = self.calc.find_arbitrage(matched)
        opp = opportunities[0]

        # Guaranteed profit should be positive for valid arb
        self.assertGreater(opp.guaranteed_profit, 0)

        # Profit should match percentage
        expected_profit = opp.total_stake * (opp.profit_percent / 100)
        self.assertAlmostEqual(opp.guaranteed_profit, expected_profit, delta=1.0)


def create_mock_matched_event(
    home_odds: float,
    away_odds: float,
    platform_home: str = "azuro",
    platform_away: str = "overtime",
    draw_odds: float = None,
) -> MatchedEvent:
    """
    Create a mock MatchedEvent for testing.

    Args:
        home_odds: Odds for home outcome
        away_odds: Odds for away outcome
        platform_home: Platform offering home odds
        platform_away: Platform offering away odds
        draw_odds: Optional draw odds (for 3-way markets)

    Returns:
        MatchedEvent with configured odds
    """
    matched = MatchedEvent(
        match_id="test_123",
        sport="soccer",
        league="Test League",
        home_team="Team A",
        away_team="Team B",
        start_time=datetime.now(timezone.utc),
    )

    # Add home odds
    home_entry = OddsEntry(
        platform=platform_home,
        outcome="home",
        decimal_odds=home_odds,
        implied_prob=1/home_odds,
    )

    # Add away odds
    away_entry = OddsEntry(
        platform=platform_away,
        outcome="away",
        decimal_odds=away_odds,
        implied_prob=1/away_odds,
    )

    # Determine market type
    if draw_odds:
        market_type = "1x2"
        draw_entry = OddsEntry(
            platform=platform_home,
            outcome="draw",
            decimal_odds=draw_odds,
            implied_prob=1/draw_odds,
        )
        matched.combined_odds[market_type] = {
            "home": [home_entry],
            "draw": [draw_entry],
            "away": [away_entry],
        }
        matched.best_odds[market_type] = {
            "home": home_entry,
            "draw": draw_entry,
            "away": away_entry,
        }
    else:
        market_type = "moneyline"
        matched.combined_odds[market_type] = {
            "home": [home_entry],
            "away": [away_entry],
        }
        matched.best_odds[market_type] = {
            "home": home_entry,
            "away": away_entry,
        }

    return matched


class TestFormatOpportunity(unittest.TestCase):
    """Tests for opportunity formatting."""

    def setUp(self):
        self.calc = ArbitrageCalculator(
            min_profit_percent=0.5,
            max_profit_percent=50.0,
        )

    def test_format_contains_key_info(self):
        """Test that formatted output contains key information."""
        matched = create_mock_matched_event(
            home_odds=2.20,
            away_odds=2.10,
            platform_home="azuro",
            platform_away="overtime",
        )

        opportunities = self.calc.find_arbitrage(matched)
        formatted = self.calc.format_opportunity(opportunities[0])

        # Check key info is present
        self.assertIn("Team A", formatted)
        self.assertIn("Team B", formatted)
        self.assertIn("azuro", formatted)
        self.assertIn("overtime", formatted)
        self.assertIn("profit", formatted.lower())
        self.assertIn("stake", formatted.lower())


if __name__ == "__main__":
    # Run tests with verbosity
    unittest.main(verbosity=2)
