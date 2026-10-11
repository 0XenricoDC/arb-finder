"""
Telegram notification system for arbitrage alerts.

Sends formatted alerts to a Telegram chat when arbitrage
opportunities are detected.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError, RetryAfter, TimedOut

from core.models import ArbitrageOpportunity, ArbLeg


logger = logging.getLogger(__name__)


class ArbNotifier:
    """
    Telegram notification handler for arbitrage alerts.

    Sends formatted HTML messages to a configured Telegram chat
    with cooldown protection to prevent spam.
    """

    # Default cooldown between alerts for the same opportunity
    DEFAULT_COOLDOWN_SECONDS = 300  # 5 minutes

    # Maximum retries for failed sends
    MAX_RETRIES = 3

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
        enabled: bool = True,
    ):
        """
        Initialize the Telegram notifier.

        Args:
            bot_token: Telegram Bot API token from @BotFather
            chat_id: Target chat/channel ID for notifications
            cooldown_seconds: Minimum seconds between duplicate alerts
            enabled: Whether notifications are enabled
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.cooldown = timedelta(seconds=cooldown_seconds)
        self.enabled = enabled

        # Initialize bot (lazy connection)
        self._bot: Optional[Bot] = None

        # Track sent alerts to prevent duplicates
        # Key: opportunity key, Value: last sent timestamp
        self._sent_alerts: Dict[str, datetime] = {}

        # Cleanup old entries periodically
        self._last_cleanup = datetime.utcnow()
        self._cleanup_interval = timedelta(hours=1)

        self.logger = logging.getLogger(f"{__name__}.ArbNotifier")

        if enabled:
            self.logger.info(f"Telegram notifier initialized for chat {chat_id}")
        else:
            self.logger.info("Telegram notifier disabled")

    @property
    def bot(self) -> Bot:
        """Get or create the Telegram bot instance."""
        if self._bot is None:
            self._bot = Bot(token=self.bot_token)
        return self._bot

    async def send_alert(self, arb: ArbitrageOpportunity) -> bool:
        """
        Send an arbitrage alert to Telegram.

        Args:
            arb: Arbitrage opportunity to alert

        Returns:
            True if alert was sent, False if skipped or failed
        """
        if not self.enabled:
            self.logger.debug("Notifications disabled, skipping alert")
            return False

        # Check cooldown
        alert_key = self._get_alert_key(arb)
        if not self._should_send(alert_key):
            self.logger.debug(f"Alert on cooldown: {alert_key}")
            return False

        # Format message
        message = self._format_message(arb)

        # Send with retry logic
        success = await self._send_with_retry(message)

        if success:
            self._sent_alerts[alert_key] = datetime.utcnow()
            self.logger.info(
                f"Alert sent: {arb.profit_percent:.2f}% on "
                f"{arb.matched_event.home_team} vs {arb.matched_event.away_team}"
            )

        # Periodic cleanup
        self._cleanup_old_alerts()

        return success

    async def send_message(self, text: str, parse_mode: str = ParseMode.HTML) -> bool:
        """
        Send a raw message to Telegram.

        Args:
            text: Message text
            parse_mode: Parse mode (HTML, Markdown, etc.)

        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False

        return await self._send_with_retry(text, parse_mode)

    async def send_startup_message(self) -> bool:
        """Send a startup notification."""
        message = (
            "🚀 <b>Arbitrage Finder Started</b>\n\n"
            f"📅 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
            "🔍 Scanning for opportunities..."
        )
        return await self.send_message(message)

    async def send_summary(
        self,
        opportunities_found: int,
        events_scanned: int,
        platforms: list,
    ) -> bool:
        """
        Send a periodic summary.

        Args:
            opportunities_found: Number of arb opportunities found
            events_scanned: Total events scanned
            platforms: List of active platforms
        """
        message = (
            "📊 <b>Scan Summary</b>\n\n"
            f"🎯 Opportunities: {opportunities_found}\n"
            f"📋 Events scanned: {events_scanned}\n"
            f"🔌 Platforms: {', '.join(platforms)}\n"
            f"⏰ {datetime.utcnow().strftime('%H:%M UTC')}"
        )
        return await self.send_message(message)

    def _format_message(self, arb: ArbitrageOpportunity) -> str:
        """
        Format an arbitrage opportunity as an HTML message.

        Args:
            arb: Arbitrage opportunity

        Returns:
            Formatted HTML message string
        """
        event = arb.matched_event

        # Header with profit
        lines = [
            "⚡️ <b>ARBITRAGE FOUND!</b> ⚡️",
            "",
            f"🏆 <b>{event.league}</b>",
            f"⚽ {event.home_team} vs {event.away_team}",
            f"🕐 {event.start_time.strftime('%d/%m %H:%M')} UTC",
            "",
            f"📊 <b>Market:</b> {arb.market_type.upper()}",
            f"💰 <b>Profit:</b> {arb.profit_percent:.2f}%",
            f"📈 <b>Implied:</b> {arb.total_implied_prob:.4f}",
            "",
            f"<b>Stakes (€{arb.total_stake:.0f} total):</b>",
        ]

        # Add each leg
        for leg in arb.legs:
            lines.append(self._format_leg(leg))

        # Footer
        lines.extend([
            "",
            f"💵 <b>Guaranteed:</b> €{arb.guaranteed_profit:.2f}",
            "",
            f"⏰ <i>Found at {arb.found_at.strftime('%H:%M:%S')} UTC</i>",
        ])

        return "\n".join(lines)

    def _format_leg(self, leg: ArbLeg) -> str:
        """
        Format a single arbitrage leg.

        Args:
            leg: Arbitrage leg

        Returns:
            Formatted string for this leg
        """
        # Emoji based on outcome
        outcome_emoji = {
            "home": "🏠",
            "away": "✈️",
            "draw": "🤝",
            "over": "⬆️",
            "under": "⬇️",
        }.get(leg.outcome.lower(), "•")

        line = (
            f"{outcome_emoji} <b>{leg.outcome.upper()}</b>: "
            f"{leg.odds:.2f} @ {leg.platform}\n"
            f"    └ Stake: €{leg.stake:.2f} → €{leg.potential_return:.2f}"
        )

        return line

    def _get_alert_key(self, arb: ArbitrageOpportunity) -> str:
        """
        Generate a unique key for deduplication.

        Args:
            arb: Arbitrage opportunity

        Returns:
            Unique string key
        """
        event = arb.matched_event
        return f"{event.match_id}_{arb.market_type}"

    def _should_send(self, alert_key: str) -> bool:
        """
        Check if an alert should be sent based on cooldown.

        Args:
            alert_key: Unique alert identifier

        Returns:
            True if alert should be sent
        """
        if alert_key not in self._sent_alerts:
            return True

        last_sent = self._sent_alerts[alert_key]
        elapsed = datetime.utcnow() - last_sent

        return elapsed >= self.cooldown

    async def _send_with_retry(
        self,
        text: str,
        parse_mode: str = ParseMode.HTML,
    ) -> bool:
        """
        Send a message with retry logic.

        Args:
            text: Message text
            parse_mode: Parse mode

        Returns:
            True if sent successfully
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    parse_mode=parse_mode,
                    disable_web_page_preview=True,
                )
                return True

            except RetryAfter as e:
                # Rate limited - wait and retry
                wait_time = e.retry_after
                self.logger.warning(f"Rate limited, waiting {wait_time}s")
                await asyncio.sleep(wait_time)

            except TimedOut:
                # Timeout - retry
                self.logger.warning(f"Telegram timeout, attempt {attempt + 1}/{self.MAX_RETRIES}")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

            except TelegramError as e:
                self.logger.error(f"Telegram error: {e}")
                if attempt == self.MAX_RETRIES - 1:
                    return False
                await asyncio.sleep(1)

            except Exception as e:
                self.logger.error(f"Unexpected error sending Telegram message: {e}")
                return False

        return False

    def _cleanup_old_alerts(self) -> None:
        """Remove old entries from the sent alerts cache."""
        now = datetime.utcnow()

        if now - self._last_cleanup < self._cleanup_interval:
            return

        # Remove entries older than 2x cooldown
        cutoff = now - (self.cooldown * 2)
        old_keys = [
            key for key, timestamp in self._sent_alerts.items()
            if timestamp < cutoff
        ]

        for key in old_keys:
            del self._sent_alerts[key]

        if old_keys:
            self.logger.debug(f"Cleaned up {len(old_keys)} old alert entries")

        self._last_cleanup = now

    async def test_connection(self) -> bool:
        """
        Test the Telegram bot connection.

        Returns:
            True if connection is working
        """
        try:
            me = await self.bot.get_me()
            self.logger.info(f"Connected to Telegram as @{me.username}")
            return True
        except TelegramError as e:
            self.logger.error(f"Failed to connect to Telegram: {e}")
            return False


class MockNotifier(ArbNotifier):
    """
    Mock notifier for testing without Telegram.

    Logs alerts instead of sending them.
    """

    def __init__(self, **kwargs):
        """Initialize mock notifier."""
        # Don't call super().__init__ to avoid needing real credentials
        self.enabled = True
        self.cooldown = timedelta(seconds=kwargs.get("cooldown_seconds", 300))
        self._sent_alerts: Dict[str, datetime] = {}
        self._last_cleanup = datetime.utcnow()
        self._cleanup_interval = timedelta(hours=1)
        self.logger = logging.getLogger(f"{__name__}.MockNotifier")
        self.sent_messages: list = []

    async def send_alert(self, arb: ArbitrageOpportunity) -> bool:
        """Log alert instead of sending."""
        alert_key = self._get_alert_key(arb)

        if not self._should_send(alert_key):
            return False

        message = self._format_message(arb)
        self.sent_messages.append(message)
        self._sent_alerts[alert_key] = datetime.utcnow()

        self.logger.info(
            f"[MOCK] Alert: {arb.profit_percent:.2f}% on "
            f"{arb.matched_event.home_team} vs {arb.matched_event.away_team}"
        )
        print(f"\n{'='*50}")
        print(message.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", ""))
        print(f"{'='*50}\n")

        return True

    async def send_message(self, text: str, parse_mode: str = None) -> bool:
        """Log message instead of sending."""
        self.sent_messages.append(text)
        self.logger.info(f"[MOCK] Message: {text[:100]}...")
        return True

    async def test_connection(self) -> bool:
        """Always returns True for mock."""
        self.logger.info("[MOCK] Connection test: OK")
        return True
