# 🤖 Claude Code Commands - Quick Reference

## Project Setup

```bash
# Initialize project
mkdir arb-finder && cd arb-finder
python -m venv venv && source venv/bin/activate
pip install aiohttp gql beautifulsoup4 python-telegram-bot thefuzz pydantic tenacity

# Create structure
mkdir -p config scrapers core utils notifications
touch config/__init__.py scrapers/__init__.py core/__init__.py utils/__init__.py notifications/__init__.py
```

---

## Prompt Templates for Claude Code

### 1️⃣ Create Base Scraper
```
Create a Python abstract base class for web scrapers in `scrapers/base_scraper.py`:
- Abstract methods: fetch_events(), parse_event(), get_odds()
- Common methods: normalize_team_name(), convert_odds_format()
- Use aiohttp for async HTTP requests
- Include retry logic with exponential backoff
- Add proper logging
```

### 2️⃣ Implement Azuro Scraper
```
Create `scrapers/azuro_scraper.py` that:
- Inherits from BaseScraper
- Queries the Azuro GraphQL subgraph at: https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-polygon-v3
- Fetches upcoming sports events (soccer, basketball, tennis)
- Parses the response into Event objects with odds
- Handles pagination for large result sets
- Converts Azuro's raw odds format (divide by 10^12)

Use this GraphQL query:
query GetGames($startsAt: BigInt!) {
  games(where: {startsAt_gt: $startsAt, status: Created}, first: 100) {
    gameId, title, startsAt
    sport { name }
    league { name, country { name } }
    participants { name }
    conditions { outcomes { outcomeId, currentOdds } }
  }
}
```

### 3️⃣ Implement Overtime Scraper
```
Create `scrapers/overtime_scraper.py` that:
- Fetches from Overtime Markets API: https://api.thalesmarket.io/overtime/v2/networks/10/markets
- Parses JSON response into Event objects
- Extracts homeOdds, awayOdds, drawOdds
- Filters for pre-match events only
- Handles network errors gracefully
```

### 4️⃣ Create Event Matcher
```
Create `core/matcher.py` with EventMatcher class that:
- Takes events from multiple platforms
- Normalizes team names (remove FC, SC, punctuation, etc.)
- Uses fuzzy matching (thefuzz library) with 85% threshold
- Matches by: normalized team names + start time within 2 hours
- Returns List[MatchedEvent] with odds from all platforms
- Include team aliases dictionary for common teams
```

### 5️⃣ Create Arbitrage Calculator
```
Create `core/calculator.py` with ArbitrageCalculator class:
- Method: calculate_2way_arb(odds1, odds2) -> (bool, profit_percent)
- Method: calculate_3way_arb(home, draw, away) -> (bool, profit_percent)
- Method: calculate_optimal_stakes(total, odds_list) -> stake_list
- Method: find_best_odds(matched_event) -> best odds per outcome
- Filter results by min_profit (1%) and max_profit (20%)
```

### 6️⃣ Create Telegram Notifier
```
Create `notifications/telegram_bot.py`:
- Class ArbNotifier with async send_alert method
- Format messages with HTML markup
- Include: event details, profit %, stakes for €100
- Add cooldown to prevent duplicate alerts (5 min)
- Handle Telegram API errors gracefully
```

### 7️⃣ Create Main Runner
```
Create `main.py` that:
- Initializes all scrapers based on config
- Runs continuous loop with 60 second intervals
- Fetches events from all platforms concurrently
- Matches events across platforms
- Calculates arbitrage opportunities
- Sends Telegram alerts for valid opportunities
- Logs all activity
- Handles graceful shutdown on SIGINT
```

---

## Testing Commands

```
# Test individual scraper
Write a test script that:
1. Imports AzuroScraper
2. Fetches soccer events for next 24 hours
3. Prints first 5 events with odds
4. Validates data structure

# Test matching
Write a test that:
1. Creates mock events from 2 platforms with slightly different team names
2. Runs EventMatcher
3. Verifies matches are found correctly

# Test calculator
Write unit tests for ArbitrageCalculator:
- Test 2-way arb with known profitable odds
- Test 3-way arb with known profitable odds
- Test stake calculation accuracy
- Test edge cases (invalid odds, etc.)
```

---

## Environment Variables

```bash
# .env file
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id
LOG_LEVEL=INFO
MIN_PROFIT_PERCENT=1.0
REFRESH_INTERVAL=60
```

---

## Quick Debug Commands

```python
# Test Azuro connection
import asyncio
from gql import gql, Client
from gql.transport.aiohttp import AIOHTTPTransport

async def test_azuro():
    transport = AIOHTTPTransport(url="https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-polygon-v3")
    async with Client(transport=transport) as session:
        query = gql("{ games(first: 5) { gameId title } }")
        result = await session.execute(query)
        print(result)

asyncio.run(test_azuro())
```

```python
# Test Overtime connection
import asyncio
import aiohttp

async def test_overtime():
    async with aiohttp.ClientSession() as session:
        async with session.get("https://api.thalesmarket.io/overtime/v2/networks/10/markets") as resp:
            data = await resp.json()
            print(f"Found {len(data.get('markets', []))} markets")

asyncio.run(test_overtime())
```

---

## Deployment (Optional)

```bash
# Run with PM2
npm install -g pm2
pm2 start main.py --interpreter python3 --name arb-finder

# Run with Docker
docker build -t arb-finder .
docker run -d --env-file .env arb-finder

# Run with systemd
sudo cp arb-finder.service /etc/systemd/system/
sudo systemctl enable arb-finder
sudo systemctl start arb-finder
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| GraphQL timeout | Increase timeout in AIOHTTPTransport |
| Rate limited | Add delay between requests, reduce frequency |
| Team not matching | Add alias to TEAM_ALIASES dict |
| Telegram not sending | Verify token and chat_id, check bot permissions |
| Odds format wrong | Check if platform uses decimal/american/fractional |

---

*Use these prompts sequentially with Claude Code for implementation*
