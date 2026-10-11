# 🎯 Sports Betting Arbitrage Finder - Implementation Spec

## Project Overview

**Obiettivo:** Costruire un bot che trova opportunità di arbitraggio tra piattaforme di betting DeFi e CeFi, con alert via Telegram per esecuzione manuale.

**Stack:** Python 3.11+ | asyncio | aiohttp | GraphQL | Telegram Bot API

---

## 🏗️ Architecture

```
arb-finder/
├── config/
│   ├── __init__.py
│   └── settings.py          # Configurazioni piattaforme e parametri
├── scrapers/
│   ├── __init__.py
│   ├── base_scraper.py      # Abstract base class
│   ├── azuro_scraper.py     # Azuro Protocol (GraphQL subgraph)
│   ├── overtime_scraper.py  # Overtime Markets API
│   ├── dexsport_scraper.py  # Dexsport scraping
│   └── sportbet_scraper.py  # Sportbet.one (EOS)
├── core/
│   ├── __init__.py
│   ├── models.py            # Data classes (Event, Odds, Market)
│   ├── matcher.py           # Event matching cross-platform
│   ├── calculator.py        # Arbitrage calculation engine
│   └── analyzer.py          # Opportunity analysis & filtering
├── utils/
│   ├── __init__.py
│   ├── team_normalizer.py   # Team name normalization
│   ├── logger.py            # Logging setup
│   └── helpers.py           # Utility functions
├── notifications/
│   ├── __init__.py
│   └── telegram_bot.py      # Telegram alerts
├── main.py                  # Entry point
├── requirements.txt
└── README.md
```

---

## 📊 Data Models

### Event
```python
@dataclass
class Event:
    event_id: str                    # Unique identifier
    sport: Sport                     # Enum: SOCCER, BASKETBALL, etc.
    league: str                      # "Serie A", "NBA", etc.
    home_team: str                   # Normalized team name
    away_team: str                   # Normalized team name
    start_time: datetime             # UTC timestamp
    markets: Dict[str, Market]       # market_key -> Market
    source_platform: str             # Origin platform
    raw_data: Dict                   # Original API response
```

### Market
```python
@dataclass
class Market:
    market_type: MarketType          # MONEYLINE, OVER_UNDER, SPREAD
    line: Optional[float]            # 2.5 for O/U 2.5, None for 1X2
    outcomes: Dict[str, OddsEntry]   # outcome_key -> OddsEntry
```

### OddsEntry
```python
@dataclass
class OddsEntry:
    platform: str                    # "azuro", "overtime", etc.
    outcome: str                     # "home", "away", "draw", "over", "under"
    decimal_odds: float              # European decimal odds (e.g., 2.10)
    implied_prob: float              # 1/odds (e.g., 0.476)
    timestamp: datetime              # When scraped
    liquidity: Optional[float]       # Available liquidity (DeFi)
    max_stake: Optional[float]       # Maximum bet allowed
    url: Optional[str]               # Direct link to bet
```

### ArbitrageOpportunity
```python
@dataclass
class ArbitrageOpportunity:
    event: MatchedEvent              # The matched event
    market_type: MarketType          # Which market has arb
    legs: List[ArbLeg]               # Each leg of the arb
    total_implied_prob: float        # Sum of 1/odds (< 1.0 = profit)
    profit_percent: float            # (1 - total_implied_prob) * 100
    optimal_stakes: Dict[str, float] # Platform -> stake amount
    expected_profit: float           # In base currency
    found_at: datetime
    expires_at: datetime             # Event start time
```

---

## 🔌 Platform Scrapers

### 1. Azuro Protocol (Priority: HIGH)

**Endpoint:** GraphQL Subgraph
```
https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-polygon-v3
```

**Query per fetch eventi:**
```graphql
query GetUpcomingEvents($startTime: BigInt!, $sport: String) {
  games(
    where: {
      startsAt_gt: $startTime
      status: Created
      sport_: { name: $sport }
    }
    orderBy: startsAt
    first: 100
  ) {
    gameId
    slug
    title
    startsAt
    sport {
      name
      slug
    }
    league {
      name
      country {
        name
      }
    }
    participants {
      name
      image
    }
    conditions {
      conditionId
      outcomes {
        outcomeId
        currentOdds
      }
      core {
        type
        margin
      }
    }
  }
}
```

**Mapping outcomes Azuro:**
- `outcomeId` 1 = Home Win
- `outcomeId` 2 = Away Win  
- `outcomeId` 3 = Draw (for 1X2)

**Note implementative:**
- Le odds sono in formato raw (need divide by 10^12)
- Usare `aiohttp` con session pooling
- Cache results per 30 secondi
- Rate limit: ~100 req/min

---

### 2. Overtime Markets (Priority: HIGH)

**Docs:** https://docs.overtimemarkets.xyz/

**Endpoints principali:**
```
Base URL: https://api.thalesmarket.io/overtime/v2

GET /networks/{networkId}/markets
GET /networks/{networkId}/markets/{marketAddress}
```

**Network IDs:**
- Optimism: 10
- Arbitrum: 42161
- Base: 8453

**Response structure:**
```json
{
  "markets": [
    {
      "gameId": "0x...",
      "sport": "Soccer",
      "type": "moneyline",
      "maturityDate": 1707321600,
      "homeTeam": "Inter",
      "awayTeam": "Milan", 
      "homeOdds": 1.85,
      "awayOdds": 2.10,
      "drawOdds": 3.50,
      "isPaused": false,
      "isCanceled": false
    }
  ]
}
```

**Note implementative:**
- Odds già in formato decimale
- Supporta filtro per sport
- WebSocket disponibile per live updates (futuro)

---

### 3. Dexsport.io (Priority: MEDIUM)

**Approccio:** Web scraping (no public API)

**Target URL:** `https://dexsport.io/sports/{sport}`

**Strategia:**
1. Use `playwright` o `selenium` per rendering JS
2. Intercept XHR requests per trovare API interna
3. Parse DOM come fallback

**Struttura pagina (da ispezionare):**
```html
<div class="event-card">
  <div class="teams">
    <span class="home">Team A</span>
    <span class="away">Team B</span>
  </div>
  <div class="odds">
    <button class="odd home">1.85</button>
    <button class="odd draw">3.40</button>
    <button class="odd away">2.10</button>
  </div>
</div>
```

**Note:**
- Potrebbe richiedere rotazione user-agent
- Implementare retry con exponential backoff
- Verificare ToS per scraping

---

### 4. Sportbet.one (Priority: MEDIUM)

**Chain:** EOS Blockchain

**Approccio:** Query EOS smart contract o scraping

**EOS Contract:** `sportbetone` (da verificare)

**Strategia alternativa:**
```python
# Se API non disponibile, scrape dalla pagina
import aiohttp

async def scrape_sportbet():
    async with aiohttp.ClientSession() as session:
        async with session.get('https://sportbet.one/sports/soccer') as resp:
            html = await resp.text()
            # Parse with BeautifulSoup
```

---

## 🧮 Arbitrage Calculator

### Formula Base (2-way)
```python
def calculate_arb_2way(odds_a: float, odds_b: float) -> tuple[bool, float]:
    """
    Calculate if arbitrage exists for 2-outcome market.
    
    Args:
        odds_a: Decimal odds for outcome A (e.g., home win)
        odds_b: Decimal odds for outcome B (e.g., away win)
    
    Returns:
        (is_arb, profit_percent)
    """
    implied_prob = (1/odds_a) + (1/odds_b)
    is_arb = implied_prob < 1.0
    profit_percent = (1 - implied_prob) * 100 if is_arb else 0
    return is_arb, profit_percent
```

### Formula 3-way (1X2 Soccer)
```python
def calculate_arb_3way(odds_home: float, odds_draw: float, odds_away: float) -> tuple[bool, float]:
    """
    Calculate arbitrage for 3-outcome market (1X2).
    """
    implied_prob = (1/odds_home) + (1/odds_draw) + (1/odds_away)
    is_arb = implied_prob < 1.0
    profit_percent = (1 - implied_prob) * 100 if is_arb else 0
    return is_arb, profit_percent
```

### Optimal Stakes Calculator
```python
def calculate_optimal_stakes(
    total_stake: float,
    odds: List[float]
) -> List[float]:
    """
    Calculate optimal stake distribution for guaranteed profit.
    
    Formula: stake_i = total_stake / (odds_i * sum(1/odds_j for all j))
    """
    implied_probs = [1/o for o in odds]
    total_implied = sum(implied_probs)
    
    stakes = []
    for i, odd in enumerate(odds):
        stake = total_stake / (odd * total_implied)
        stakes.append(round(stake, 2))
    
    return stakes
```

### Example Calculation
```
Event: Inter vs Milan
Platform A (Azuro): Home 2.10, Draw 3.50, Away 3.80
Platform B (Overtime): Home 1.95, Draw 3.60, Away 4.10

Best odds combination:
- Home: 2.10 (Azuro)
- Draw: 3.60 (Overtime)  
- Away: 4.10 (Overtime)

Implied probability: 1/2.10 + 1/3.60 + 1/4.10 = 0.476 + 0.278 + 0.244 = 0.998

Profit: (1 - 0.998) * 100 = 0.2% ❌ (below threshold)

---

Better example with real arb:
- Home: 2.20 (Azuro)
- Draw: 3.80 (Overtime)
- Away: 4.50 (Dexsport)

Implied: 1/2.20 + 1/3.80 + 1/4.50 = 0.455 + 0.263 + 0.222 = 0.940

Profit: (1 - 0.940) * 100 = 6.0% ✅

For €100 total stake:
- Home stake: 100 / (2.20 * 0.940) = €48.35
- Draw stake: 100 / (3.80 * 0.940) = €28.00
- Away stake: 100 / (4.50 * 0.940) = €23.65

Any outcome pays: ~€106.37 (€6.37 guaranteed profit)
```

---

## 🔄 Event Matching Algorithm

### Challenge
Lo stesso evento appare con nomi diversi su piattaforme diverse:
- Azuro: "FC Internazionale Milano vs AC Milan"
- Overtime: "Inter - Milan"
- Dexsport: "Inter Milan vs A.C. Milan"

### Matching Strategy

```python
class EventMatcher:
    def __init__(self):
        self.team_aliases = load_team_aliases()  # From config
        self.fuzzy_threshold = 85  # Minimum similarity score
    
    def normalize_team(self, name: str) -> str:
        """Normalize team name to canonical form."""
        name = name.lower().strip()
        
        # Remove common suffixes
        for suffix in ['fc', 'sc', 'ac', 'ss', 'afc', 'cfc']:
            name = name.replace(suffix, '')
        
        # Remove punctuation
        name = re.sub(r'[^\w\s]', '', name)
        
        # Check aliases
        for canonical, aliases in self.team_aliases.items():
            if name in aliases or any(alias in name for alias in aliases):
                return canonical
        
        return name.strip()
    
    def match_events(
        self, 
        events_a: List[Event], 
        events_b: List[Event]
    ) -> List[MatchedEvent]:
        """Match events from two platforms."""
        matched = []
        
        for event_a in events_a:
            home_a = self.normalize_team(event_a.home_team)
            away_a = self.normalize_team(event_a.away_team)
            
            for event_b in events_b:
                home_b = self.normalize_team(event_b.home_team)
                away_b = self.normalize_team(event_b.away_team)
                
                # Check exact match
                if home_a == home_b and away_a == away_b:
                    # Verify time is within 2 hours
                    time_diff = abs(event_a.start_time - event_b.start_time)
                    if time_diff.total_seconds() < 7200:
                        matched.append(MatchedEvent(event_a, event_b))
                        continue
                
                # Fuzzy match fallback
                home_score = fuzz.ratio(home_a, home_b)
                away_score = fuzz.ratio(away_a, away_b)
                
                if home_score > self.fuzzy_threshold and away_score > self.fuzzy_threshold:
                    matched.append(MatchedEvent(event_a, event_b))
        
        return matched
```

---

## 📱 Telegram Bot Integration

### Setup
```python
from telegram import Bot
from telegram.constants import ParseMode

class ArbNotifier:
    def __init__(self, token: str, chat_id: str):
        self.bot = Bot(token=token)
        self.chat_id = chat_id
    
    async def send_alert(self, arb: ArbitrageOpportunity):
        message = self._format_message(arb)
        await self.bot.send_message(
            chat_id=self.chat_id,
            text=message,
            parse_mode=ParseMode.HTML
        )
    
    def _format_message(self, arb: ArbitrageOpportunity) -> str:
        return f"""
⚡️ <b>ARBITRAGE FOUND!</b> ⚡️

🏆 <b>{arb.event.league}</b>
⚽️ {arb.event.home_team} vs {arb.event.away_team}
🕐 {arb.event.start_time.strftime('%d/%m %H:%M')} UTC

📊 <b>Market:</b> {arb.market_type.value}
💰 <b>Profit:</b> {arb.profit_percent:.2f}%

<b>Stakes (€100 total):</b>
{self._format_legs(arb)}

⏰ <i>Found at {arb.found_at.strftime('%H:%M:%S')}</i>
"""
    
    def _format_legs(self, arb: ArbitrageOpportunity) -> str:
        lines = []
        for leg in arb.legs:
            lines.append(
                f"• {leg.outcome}: <b>{leg.odds}</b> @ {leg.platform}\n"
                f"  Stake: €{arb.optimal_stakes[leg.platform]:.2f}"
            )
        return "\n".join(lines)
```

### Message Example
```
⚡️ ARBITRAGE FOUND! ⚡️

🏆 Serie A
⚽️ Inter vs Milan
🕐 15/02 20:45 UTC

📊 Market: 1X2
💰 Profit: 2.34%

Stakes (€100 total):
• Home: 2.15 @ Azuro
  Stake: €46.51
• Draw: 3.70 @ Overtime
  Stake: €27.03
• Away: 4.20 @ Dexsport
  Stake: €23.81

⏰ Found at 14:32:15
```

---

## ⚙️ Configuration (settings.py)

```python
# =============================================================================
# PLATFORMS
# =============================================================================

PLATFORMS = {
    "azuro": {
        "enabled": True,
        "name": "Azuro",
        "type": "defi",
        "chain": "polygon",
        "subgraph": "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-polygon-v3",
        "refresh_interval": 30,  # seconds
    },
    "overtime": {
        "enabled": True,
        "name": "Overtime Markets",
        "type": "defi",
        "chain": "optimism",
        "api_base": "https://api.thalesmarket.io/overtime/v2",
        "network_id": 10,
        "refresh_interval": 30,
    },
    "dexsport": {
        "enabled": True,
        "name": "Dexsport",
        "type": "defi",
        "chain": "multi",
        "base_url": "https://dexsport.io",
        "refresh_interval": 60,
    },
    "sportbet_one": {
        "enabled": True,
        "name": "Sportbet.one",
        "type": "defi",
        "chain": "eos",
        "base_url": "https://sportbet.one",
        "refresh_interval": 60,
    },
}

# =============================================================================
# ARBITRAGE SETTINGS
# =============================================================================

ARB_SETTINGS = {
    "min_profit_percent": 1.0,      # Minimum profit to alert
    "max_profit_percent": 15.0,     # Filter likely errors
    "default_stake": 100,           # EUR for calculations
    "pre_match_only": True,         # No live betting
    "hours_before_start": 48,       # How far ahead to look
    "min_time_to_start": 5,         # Minutes - avoid last second
}

# =============================================================================
# SPORTS & MARKETS
# =============================================================================

ENABLED_SPORTS = [
    "soccer",
    "basketball", 
    "tennis",
]

ENABLED_MARKETS = [
    "1x2",           # Match winner (3-way)
    "moneyline",     # Match winner (2-way)
    "over_under",    # Total goals/points
]

# =============================================================================
# TELEGRAM
# =============================================================================

TELEGRAM = {
    "enabled": True,
    "bot_token": "YOUR_BOT_TOKEN",
    "chat_id": "YOUR_CHAT_ID",
    "alert_cooldown": 300,  # Don't re-alert same arb within 5 min
}

# =============================================================================
# TEAM ALIASES (for matching)
# =============================================================================

TEAM_ALIASES = {
    # Serie A
    "inter": ["inter", "inter milan", "internazionale", "fc inter"],
    "milan": ["milan", "ac milan", "a.c. milan"],
    "juventus": ["juventus", "juve"],
    "napoli": ["napoli", "ssc napoli"],
    "roma": ["roma", "as roma"],
    "lazio": ["lazio", "ss lazio"],
    "atalanta": ["atalanta", "atalanta bergamo"],
    "fiorentina": ["fiorentina", "acf fiorentina"],
    
    # Premier League
    "manchester_utd": ["man utd", "manchester united", "man united"],
    "manchester_city": ["man city", "manchester city"],
    "liverpool": ["liverpool"],
    "arsenal": ["arsenal"],
    "chelsea": ["chelsea"],
    "tottenham": ["tottenham", "spurs"],
    
    # La Liga
    "barcelona": ["barcelona", "barca", "fc barcelona"],
    "real_madrid": ["real madrid", "real"],
    "atletico": ["atletico madrid", "atletico", "atleti"],
    
    # Bundesliga
    "bayern": ["bayern", "bayern munich", "bayern munchen"],
    "dortmund": ["dortmund", "borussia dortmund", "bvb"],
    
    # Add more as needed...
}
```

---

## 🚀 Main Entry Point

```python
# main.py

import asyncio
import logging
from datetime import datetime, timedelta

from config.settings import PLATFORMS, ARB_SETTINGS, TELEGRAM
from scrapers import AzuroScraper, OvertimeScraper, DexsportScraper
from core.matcher import EventMatcher
from core.calculator import ArbitrageCalculator
from notifications.telegram_bot import ArbNotifier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ArbitrageFinder:
    def __init__(self):
        self.scrapers = self._init_scrapers()
        self.matcher = EventMatcher()
        self.calculator = ArbitrageCalculator()
        self.notifier = ArbNotifier(
            token=TELEGRAM["bot_token"],
            chat_id=TELEGRAM["chat_id"]
        ) if TELEGRAM["enabled"] else None
        
        self.last_alerts = {}  # Track sent alerts to avoid duplicates
    
    def _init_scrapers(self):
        scrapers = []
        if PLATFORMS["azuro"]["enabled"]:
            scrapers.append(AzuroScraper(PLATFORMS["azuro"]))
        if PLATFORMS["overtime"]["enabled"]:
            scrapers.append(OvertimeScraper(PLATFORMS["overtime"]))
        if PLATFORMS["dexsport"]["enabled"]:
            scrapers.append(DexsportScraper(PLATFORMS["dexsport"]))
        return scrapers
    
    async def run(self):
        """Main loop"""
        logger.info("🚀 Arbitrage Finder started")
        
        while True:
            try:
                await self._scan_cycle()
            except Exception as e:
                logger.error(f"Error in scan cycle: {e}")
            
            await asyncio.sleep(ARB_SETTINGS["refresh_interval"])
    
    async def _scan_cycle(self):
        """Single scan cycle"""
        # 1. Fetch events from all platforms
        all_events = {}
        for scraper in self.scrapers:
            try:
                events = await scraper.fetch_events()
                all_events[scraper.platform_name] = events
                logger.info(f"Fetched {len(events)} events from {scraper.platform_name}")
            except Exception as e:
                logger.error(f"Error fetching from {scraper.platform_name}: {e}")
        
        # 2. Match events across platforms
        matched_events = self.matcher.match_all(all_events)
        logger.info(f"Matched {len(matched_events)} events across platforms")
        
        # 3. Find arbitrage opportunities
        opportunities = []
        for matched in matched_events:
            arbs = self.calculator.find_arbitrage(matched)
            opportunities.extend(arbs)
        
        # 4. Filter and alert
        for arb in opportunities:
            if self._should_alert(arb):
                await self._send_alert(arb)
    
    def _should_alert(self, arb) -> bool:
        """Check if we should send alert (avoid duplicates)"""
        key = f"{arb.event.event_id}_{arb.market_type}"
        
        if key in self.last_alerts:
            last_time = self.last_alerts[key]
            if datetime.now() - last_time < timedelta(seconds=TELEGRAM["alert_cooldown"]):
                return False
        
        return True
    
    async def _send_alert(self, arb):
        """Send alert via Telegram"""
        if self.notifier:
            await self.notifier.send_alert(arb)
            key = f"{arb.event.event_id}_{arb.market_type}"
            self.last_alerts[key] = datetime.now()
            logger.info(f"✅ Alert sent: {arb.profit_percent:.2f}% on {arb.event.home_team} vs {arb.event.away_team}")


if __name__ == "__main__":
    finder = ArbitrageFinder()
    asyncio.run(finder.run())
```

---

## 📦 Requirements

```txt
# requirements.txt

# Async HTTP
aiohttp>=3.9.0
aiohttp-retry>=2.8.0

# GraphQL (for Azuro)
gql>=3.5.0
gql[aiohttp]>=3.5.0

# Web scraping (for Dexsport, Sportbet)
beautifulsoup4>=4.12.0
playwright>=1.40.0
lxml>=5.0.0

# String matching
python-Levenshtein>=0.23.0
thefuzz>=0.22.0

# Telegram
python-telegram-bot>=20.7

# Data handling
pydantic>=2.5.0
python-dateutil>=2.8.0

# Utilities
python-dotenv>=1.0.0
tenacity>=8.2.0

# Development
pytest>=7.4.0
pytest-asyncio>=0.23.0
black>=23.12.0
```

---

## 🔧 Setup Instructions

### 1. Clone e setup ambiente
```bash
git clone <repo>
cd arb-finder
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

### 2. Configura Telegram Bot
1. Parla con @BotFather su Telegram
2. Crea nuovo bot con `/newbot`
3. Copia il token nel `settings.py`
4. Avvia chat con il bot e ottieni il chat_id con:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```

### 3. Run
```bash
python main.py
```

---

## 📋 Implementation Checklist

### Phase 1: Core Infrastructure
- [ ] Setup project structure
- [ ] Implement data models (`models.py`)
- [ ] Implement base scraper class
- [ ] Setup logging

### Phase 2: Scrapers
- [ ] Azuro scraper (GraphQL)
- [ ] Overtime scraper (REST API)
- [ ] Dexsport scraper (Web scraping)
- [ ] Sportbet.one scraper

### Phase 3: Matching & Calculation
- [ ] Team name normalizer
- [ ] Event matcher algorithm
- [ ] Arbitrage calculator
- [ ] Stake optimizer

### Phase 4: Notifications
- [ ] Telegram bot setup
- [ ] Alert formatting
- [ ] Duplicate prevention
- [ ] Rate limiting

### Phase 5: Testing & Optimization
- [ ] Unit tests for calculator
- [ ] Integration tests for scrapers
- [ ] Performance optimization
- [ ] Error handling improvements

### Phase 6: Enhancements (Future)
- [ ] Web dashboard
- [ ] Historical arb tracking
- [ ] Auto-execution (DeFi side)
- [ ] Live betting support

---

## ⚠️ Important Notes

### Legal Considerations (Italy)
- Arbitrage betting is **legal** in Italy
- Use only ADM-licensed bookmakers for CeFi
- DeFi platforms operate in regulatory grey area
- Winnings over €500 are taxed at 20%

### Risk Management
- Start with small stakes to test
- Verify odds haven't changed before placing
- Account for gas fees on DeFi platforms
- Have funds ready on all platforms

### Technical Risks
- Odds can change between detection and execution
- API rate limits may cause missed opportunities
- Network latency affects DeFi transactions
- Scraping may break if sites change structure

---

## 📞 Support & Updates

Per domande o issues durante l'implementazione, riferirsi a:
- Azuro Docs: https://docs.azuro.org/
- Overtime Docs: https://docs.overtimemarkets.xyz/
- Telegram Bot API: https://core.telegram.org/bots/api

---

*Document Version: 1.0*
*Last Updated: February 2025*
*Author: Claude (Anthropic)*
