"""
Configuration settings for the Arbitrage Finder Bot
"""

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# =============================================================================
# PLATFORM CONFIGURATIONS
# =============================================================================

PLATFORMS = {
    "azuro": {
        "name": "Azuro",
        "type": "defi",
        "chain": "polygon",
        "subgraph_url": "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-polygon-v3",
        "enabled": True,
        "oracle": "chainlink_azuro",
        "can_ban": False,
    },
    "overtime": {
        "name": "Overtime Markets",
        "type": "defi", 
        "chain": "optimism",
        "api_url": "https://api.overtimemarkets.xyz",
        "enabled": True,
        "oracle": "chainlink_thales",
        "can_ban": False,
    },
    "dexsport": {
        "name": "Dexsport",
        "type": "defi",
        "chain": "multi",
        "api_url": "https://dexsport.io",
        "enabled": True,
        "oracle": "chainlink_dexsport",
        "can_ban": False,
    },
    "sportbet_one": {
        "name": "Sportbet.one",
        "type": "defi",
        "chain": "eos",
        "api_url": "https://sportbet.one",
        "enabled": True,
        "oracle": "eos_native",
        "can_ban": False,
    },
    "betfair": {
        "name": "Betfair Exchange",
        "type": "cefi",
        "api_url": "https://api.betfair.com/exchange",
        "enabled": False,  # Requires API key
        "can_ban": False,  # Exchange model - winner friendly
    },
}

# =============================================================================
# ARBITRAGE SETTINGS
# =============================================================================

ARB_CONFIG = {
    # Minimum profit percentage to alert (after fees)
    "min_profit_percent": 1.0,
    
    # Maximum profit percentage (filter out likely errors)
    "max_profit_percent": 15.0,
    
    # Default stake for calculations (EUR)
    "default_stake": 100,
    
    # Refresh interval in seconds
    "refresh_interval": 60,
    
    # Markets to monitor
    "markets": ["1x2", "over_under", "moneyline", "spread"],
    
    # Sports to monitor
    "sports": ["soccer", "basketball", "tennis", "esports"],
}

# =============================================================================
# TELEGRAM BOT SETTINGS
# =============================================================================

TELEGRAM_CONFIG = {
    "bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
    "chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
    "enabled": True,
}

# =============================================================================
# LOGGING
# =============================================================================

LOG_CONFIG = {
    "level": "INFO",
    "file": "arb_finder.log",
    "console": True,
}

# =============================================================================
# SPORT MAPPINGS (for cross-platform matching)
# =============================================================================

SPORT_MAPPINGS = {
    "soccer": ["soccer", "football", "calcio", "fútbol", "fussball"],
    "basketball": ["basketball", "nba", "euroleague", "basket"],
    "tennis": ["tennis", "atp", "wta"],
    "esports": ["esports", "e-sports", "gaming", "lol", "dota", "csgo", "cs2"],
    "american_football": ["american_football", "nfl", "ncaa_football"],
    "hockey": ["hockey", "ice_hockey", "nhl"],
    "mma": ["mma", "ufc", "mixed_martial_arts"],
}

# =============================================================================
# TEAM NAME NORMALIZATION
# =============================================================================

TEAM_ALIASES = {
    # Italian Serie A
    "inter_milan": ["inter", "inter milan", "internazionale", "fc internazionale", "inter milano"],
    "ac_milan": ["milan", "ac milan", "a.c. milan", "ac milano"],
    "juventus": ["juventus", "juve", "juventus fc", "juventus turin"],
    "napoli": ["napoli", "ssc napoli", "napoli fc"],
    "roma": ["roma", "as roma", "a.s. roma"],
    "lazio": ["lazio", "ss lazio", "s.s. lazio"],
    
    # Premier League
    "manchester_united": ["man utd", "manchester united", "man united", "mufc"],
    "manchester_city": ["man city", "manchester city", "mcfc"],
    "liverpool": ["liverpool", "liverpool fc", "lfc"],
    "arsenal": ["arsenal", "arsenal fc", "afc"],
    "chelsea": ["chelsea", "chelsea fc", "cfc"],
    
    # La Liga
    "barcelona": ["barcelona", "fc barcelona", "barca", "barça"],
    "real_madrid": ["real madrid", "r. madrid", "real", "rmcf"],
    "atletico_madrid": ["atletico", "atletico madrid", "atleti", "atm"],
    
    # Add more as needed...
}
