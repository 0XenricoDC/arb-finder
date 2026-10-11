"""
Sports Betting Arbitrage Finder - Main Entry Point

Scans multiple DeFi betting platforms for arbitrage opportunities
and sends alerts via Telegram.
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone
from typing import List, Optional

from scrapers import AzuroScraper, OvertimeScraper, PolymarketScraper, ScraperError
from core import EventMatcher, ArbitrageCalculator, MatchedEvent, ArbitrageOpportunity
from notifications import ArbNotifier, MockNotifier

# Import settings from config
from config.settings import TELEGRAM_CONFIG, ARB_CONFIG, PLATFORMS


# =============================================================================
# Configuration
# =============================================================================

CONFIG = {
    # Platforms
    "platforms": {
        "azuro": {
            "enabled": PLATFORMS.get("azuro", {}).get("enabled", True),
            "name": "Azuro",
            "chain": "polygon",
            "subgraph": "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-polygon-v3",
            "enabled_sports": ["football", "soccer", "basketball", "tennis", "ice hockey"],
            "refresh_interval": 30,
        },
        "overtime": {
            "enabled": PLATFORMS.get("overtime", {}).get("enabled", True),
            "name": "Overtime",
            "chain": "optimism",
            "network_id": 10,
            "api_base": "https://api.thalesmarket.io/overtime/v2",
            "enabled_sports": ["soccer", "basketball", "tennis"],
            "refresh_interval": 30,
        },
        "polymarket": {
            "enabled": True,
            "name": "Polymarket",
            "chain": "polygon",
            "refresh_interval": 60,
        },
    },

    # Arbitrage settings
    "arb": {
        "min_profit_percent": ARB_CONFIG.get("min_profit_percent", 1.0),
        "max_profit_percent": ARB_CONFIG.get("max_profit_percent", 20.0),
        "default_stake": ARB_CONFIG.get("default_stake", 100),
    },

    # Matching settings
    "matching": {
        "fuzzy_threshold": 85,
        "time_tolerance_hours": 2,
    },

    # Telegram settings - from config/settings.py
    "telegram": {
        "enabled": TELEGRAM_CONFIG.get("enabled", False),
        "bot_token": TELEGRAM_CONFIG.get("bot_token", ""),
        "chat_id": str(TELEGRAM_CONFIG.get("chat_id", "")),
        "cooldown_seconds": 300,
    },

    # General settings
    "scan_interval_seconds": ARB_CONFIG.get("refresh_interval", 60),
    "log_level": "INFO",
}


# =============================================================================
# Logging Setup
# =============================================================================

def setup_logging(level: str = "INFO") -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Reduce noise from libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("gql").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


# =============================================================================
# Main Application
# =============================================================================

class ArbitrageFinder:
    """
    Main application class for finding arbitrage opportunities.

    Coordinates scrapers, matching, calculation, and notifications.
    """

    def __init__(self, config: dict):
        """
        Initialize the arbitrage finder.

        Args:
            config: Application configuration dict
        """
        self.config = config
        self.scrapers = []
        self.matcher: Optional[EventMatcher] = None
        self.calculator: Optional[ArbitrageCalculator] = None
        self.notifier: Optional[ArbNotifier] = None

        self._running = False
        self._scan_count = 0
        self._total_opportunities = 0

    async def initialize(self) -> None:
        """Initialize all components."""
        logger.info("Initializing Arbitrage Finder...")

        # Initialize scrapers
        self._init_scrapers()

        # Initialize matcher
        self.matcher = EventMatcher(
            fuzzy_threshold=self.config["matching"]["fuzzy_threshold"],
            time_tolerance_hours=self.config["matching"]["time_tolerance_hours"],
        )

        # Initialize calculator
        self.calculator = ArbitrageCalculator(
            min_profit_percent=self.config["arb"]["min_profit_percent"],
            max_profit_percent=self.config["arb"]["max_profit_percent"],
            default_stake=self.config["arb"]["default_stake"],
        )

        # Initialize notifier
        self._init_notifier()

        logger.info(f"Initialized with {len(self.scrapers)} scrapers")

    def _init_scrapers(self) -> None:
        """Initialize platform scrapers based on config."""
        platforms = self.config["platforms"]

        if platforms["azuro"]["enabled"]:
            self.scrapers.append(AzuroScraper(platforms["azuro"]))
            logger.info("Azuro scraper enabled")

        if platforms["overtime"]["enabled"]:
            self.scrapers.append(OvertimeScraper(platforms["overtime"]))
            logger.info("Overtime scraper enabled")

        if platforms.get("polymarket", {}).get("enabled", False):
            self.scrapers.append(PolymarketScraper(platforms["polymarket"]))
            logger.info("Polymarket scraper enabled")

    def _init_notifier(self) -> None:
        """Initialize Telegram notifier."""
        tg_config = self.config["telegram"]

        if tg_config["enabled"] and tg_config["bot_token"] and tg_config["chat_id"]:
            self.notifier = ArbNotifier(
                bot_token=tg_config["bot_token"],
                chat_id=tg_config["chat_id"],
                cooldown_seconds=tg_config["cooldown_seconds"],
            )
            logger.info("Telegram notifications enabled")
        else:
            self.notifier = MockNotifier()
            logger.info("Using mock notifier (Telegram disabled)")

    async def run(self) -> None:
        """Run the main scanning loop."""
        self._running = True

        logger.info("=" * 60)
        logger.info("Arbitrage Finder Started")
        logger.info("=" * 60)

        # Send startup notification
        await self.notifier.send_startup_message()

        try:
            while self._running:
                await self._scan_cycle()
                await asyncio.sleep(self.config["scan_interval_seconds"])

        except asyncio.CancelledError:
            logger.info("Scan loop cancelled")
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            await self.shutdown()

    async def _scan_cycle(self) -> None:
        """Execute one complete scan cycle."""
        self._scan_count += 1
        cycle_start = datetime.now(timezone.utc)

        logger.info(f"Starting scan cycle #{self._scan_count}")

        try:
            # 1. Fetch events from all platforms
            events_by_platform = await self._fetch_all_events()

            if len(events_by_platform) < 2:
                logger.warning("Need at least 2 platforms with events to find arbitrage")
                return

            total_events = sum(len(e) for e in events_by_platform.values())
            logger.info(f"Fetched {total_events} events from {len(events_by_platform)} platforms")

            # 2. Match events across platforms
            matched_events = self.matcher.match_all(events_by_platform)
            logger.info(f"Matched {len(matched_events)} events across platforms")

            if not matched_events:
                logger.info("No matched events found")
                return

            # 3. Find arbitrage opportunities
            opportunities = self.calculator.find_all_arbitrage(matched_events)

            # 4. Process opportunities
            if opportunities:
                await self._process_opportunities(opportunities)
            else:
                logger.info("No arbitrage opportunities found this cycle")

            # Log cycle summary
            elapsed = (datetime.now(timezone.utc) - cycle_start).total_seconds()
            logger.info(
                f"Cycle #{self._scan_count} completed in {elapsed:.1f}s | "
                f"Events: {total_events} | Matched: {len(matched_events)} | "
                f"Opportunities: {len(opportunities)}"
            )

        except Exception as e:
            logger.error(f"Error in scan cycle: {e}", exc_info=True)

    async def _fetch_all_events(self) -> dict:
        """
        Fetch events from all enabled scrapers.

        Returns:
            Dict mapping platform name to list of events
        """
        events_by_platform = {}

        # Fetch from all scrapers concurrently
        tasks = [self._fetch_from_scraper(scraper) for scraper in self.scrapers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for scraper, result in zip(self.scrapers, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to fetch from {scraper.platform_name}: {result}")
                continue

            if result:
                events_by_platform[scraper.platform_name] = result
                logger.info(f"  {scraper.platform_name}: {len(result)} events")

        return events_by_platform

    async def _fetch_from_scraper(self, scraper) -> List[dict]:
        """
        Fetch events from a single scraper with error handling.

        Args:
            scraper: Scraper instance

        Returns:
            List of events or empty list on error
        """
        try:
            return await scraper.fetch_events()
        except ScraperError as e:
            logger.warning(f"Scraper error for {scraper.platform_name}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching from {scraper.platform_name}: {e}")
            return []

    async def _process_opportunities(
        self,
        opportunities: List[ArbitrageOpportunity],
    ) -> None:
        """
        Process and alert on arbitrage opportunities.

        Args:
            opportunities: List of detected opportunities
        """
        logger.info(f"Found {len(opportunities)} arbitrage opportunities!")

        for arb in opportunities:
            self._total_opportunities += 1

            # Log to console
            logger.info(
                f"  [ARB] {arb.profit_percent:.2f}% profit | "
                f"{arb.matched_event.home_team} vs {arb.matched_event.away_team} | "
                f"{arb.market_type} | "
                f"Platforms: {[leg.platform for leg in arb.legs]}"
            )

            # Print detailed info
            print(self.calculator.format_opportunity(arb))

            # Send Telegram alert
            await self.notifier.send_alert(arb)

    async def run_once(self) -> List[ArbitrageOpportunity]:
        """
        Run a single scan cycle and return opportunities.

        Useful for testing or one-shot execution.

        Returns:
            List of found opportunities
        """
        await self.initialize()

        events_by_platform = await self._fetch_all_events()

        if len(events_by_platform) < 2:
            logger.warning("Need at least 2 platforms")
            return []

        matched_events = self.matcher.match_all(events_by_platform)
        opportunities = self.calculator.find_all_arbitrage(matched_events)

        await self.shutdown()
        return opportunities

    async def shutdown(self) -> None:
        """Clean up resources."""
        logger.info("Shutting down...")

        self._running = False

        # Close scrapers
        for scraper in self.scrapers:
            try:
                await scraper.close()
            except Exception as e:
                logger.warning(f"Error closing {scraper.platform_name}: {e}")

        logger.info(
            f"Shutdown complete. Total scans: {self._scan_count}, "
            f"Total opportunities: {self._total_opportunities}"
        )

    def stop(self) -> None:
        """Signal the main loop to stop."""
        self._running = False


# =============================================================================
# Entry Point
# =============================================================================

async def main() -> None:
    """Main entry point."""
    setup_logging(CONFIG["log_level"])

    finder = ArbitrageFinder(CONFIG)

    try:
        await finder.initialize()
        await finder.run()
    except KeyboardInterrupt:
        logger.info("Shutting down on keyboard interrupt...")
    finally:
        await finder.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
