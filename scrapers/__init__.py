"""
Platform scrapers for fetching betting odds.
"""

from scrapers.base_scraper import (
    BaseScraper,
    ScraperError,
    RateLimitError,
    ParseError,
)
from scrapers.azuro_scraper import AzuroScraper
from scrapers.overtime_scraper import OvertimeScraper
from scrapers.dexsport_scraper import DexsportScraper
from scrapers.sportbet_scraper import SportbetScraper

__all__ = [
    "BaseScraper",
    "ScraperError",
    "RateLimitError",
    "ParseError",
    "AzuroScraper",
    "OvertimeScraper",
    "DexsportScraper",
    "SportbetScraper",
]
