# ⚡ Sports Betting Arbitrage Finder

Bot per trovare opportunità di arbitraggio tra piattaforme DeFi e CeFi di betting sportivo.

## 🎯 Cosa Fa

1. **Scraping** - Raccoglie quote da multiple piattaforme
2. **Matching** - Identifica lo stesso evento su piattaforme diverse
3. **Calcolo** - Trova opportunità di arbitraggio (sure bets)
4. **Alert** - Notifica via Telegram quando trova un'opportunità

## 🏦 Piattaforme Supportate

| Piattaforma | Tipo | Chain | Oracle | Status |
|-------------|------|-------|--------|--------|
| Azuro | DeFi | Polygon | Chainlink | ✅ |
| Overtime | DeFi | Optimism | Chainlink | ✅ |
| Dexsport | DeFi | Multi | Chainlink | 🔄 |
| Sportbet.one | DeFi | EOS | Native | 🔄 |

## 🚀 Quick Start

```bash
# Clone
git clone <repo>
cd arb-finder

# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your Telegram credentials

# Run
python main.py
```

## 📁 Struttura

```
arb-finder/
├── config/          # Configurazioni
├── scrapers/        # Scraper per ogni piattaforma
├── core/            # Logica matching e calcolo
├── utils/           # Utilities
├── notifications/   # Telegram bot
└── main.py          # Entry point
```

## 📊 Come Funziona l'Arbitraggio

```
Evento: Inter vs Milan

Piattaforma A:  Home 2.10 | Draw 3.50 | Away 3.80
Piattaforma B:  Home 1.95 | Draw 3.60 | Away 4.10

Migliori quote: Home 2.10 (A) | Draw 3.60 (B) | Away 4.10 (B)

Probabilità implicita: 1/2.10 + 1/3.60 + 1/4.10 = 0.94

Profitto garantito: (1 - 0.94) × 100 = 6% ✅
```

## ⚙️ Configurazione

Modifica `config/settings.py`:

```python
ARB_SETTINGS = {
    "min_profit_percent": 1.0,   # Minimo profitto per alert
    "max_profit_percent": 15.0,  # Filtra probabili errori
    "default_stake": 100,        # EUR per calcoli
}
```

## 📱 Telegram Alert

```
⚡️ ARBITRAGE FOUND! ⚡️

🏆 Serie A
⚽️ Inter vs Milan
🕐 15/02 20:45 UTC

📊 Market: 1X2
💰 Profit: 2.34%

Stakes (€100 total):
• Home: 2.15 @ Azuro → €46.51
• Draw: 3.70 @ Overtime → €27.03
• Away: 4.20 @ Dexsport → €23.81
```

## ⚠️ Disclaimer

- L'arbitraggio è legale in Italia
- Questo tool è solo per ricerca/alert
- Esecuzione manuale consigliata
- Verifica sempre le quote prima di puntare
- Non è consulenza finanziaria

## 📚 Docs

- [Implementation Spec](./IMPLEMENTATION_SPEC.md) - Specifiche complete
- [Claude Code Commands](./CLAUDE_CODE_COMMANDS.md) - Comandi per sviluppo

## 📄 License

MIT
