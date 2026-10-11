# ⚡ Arb Finder — Sports Betting Arbitrage Scanner

> Scrapes odds from DeFi sports-betting platforms, matches the same event across books, finds sure-bets and alerts you on Telegram.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![asyncio](https://img.shields.io/badge/async-aiohttp-2C5BB4)
![Telegram](https://img.shields.io/badge/alerts-Telegram-26A5E4?logo=telegram&logoColor=white)

🇮🇹 [Versione italiana](./README.it.md)

---

## How it works

1. **Scrape** — collects live odds from multiple platforms concurrently
2. **Match** — identifies the same event across platforms (fuzzy team names + kick-off time tolerance)
3. **Calculate** — finds 2-way / 3-way arbitrage and the optimal stake split
4. **Alert** — sends a Telegram message with odds, platforms and stakes

### The math

```
Event: Inter vs Milan
Platform A:  Home 2.10 | Draw 3.50 | Away 3.80
Platform B:  Home 1.95 | Draw 3.60 | Away 4.10

Best odds:   Home 2.10 (A) | Draw 3.60 (B) | Away 4.10 (B)
Implied probability: 1/2.10 + 1/3.60 + 1/4.10 = 0.94  →  guaranteed profit ≈ 6%
```

## Supported platforms

| Platform | Type | Chain | Status |
|---|---|---|---|
| Azuro | DeFi | Polygon | ✅ |
| Overtime Markets | DeFi | Optimism | ✅ |
| Polymarket | Prediction market | Polygon | ✅ |
| Dexsport | DeFi | Multi-chain | 🔄 |
| Sportbet.one | DeFi | EOS | 🔄 |

## Quick start

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
python main.py
```

Profit thresholds and default stake are configured in `config/settings.py`:

```python
ARB_CONFIG = {
    "min_profit_percent": 1.0,   # minimum profit to alert
    "max_profit_percent": 15.0,  # filter out likely data errors
    "default_stake": 100,        # stake used for calculations
}
```

## Example alert

```
⚡️ ARBITRAGE FOUND! ⚡️
🏆 Serie A — ⚽️ Inter vs Milan — 🕐 15/02 20:45 UTC
📊 Market: 1X2   💰 Profit: 2.34%

Stakes (€100 total):
• Home: 2.15 @ Azuro    → €46.51
• Draw: 3.70 @ Overtime → €27.03
• Away: 4.20 @ Dexsport → €23.81
```

## Project structure

```
config/          settings and platform definitions
scrapers/        one scraper per platform (shared async base class)
core/            event matching, arbitrage calculator, data models
notifications/   Telegram bot
main.py          scan loop entry point
```

## Disclaimer

For research and alerting only. Always re-check odds before placing a bet. Nothing here is financial advice.
