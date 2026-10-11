"""
Event matching engine for cross-platform arbitrage detection.

Matches the same sporting event across different betting platforms
using team name normalization and fuzzy matching.
"""

import hashlib
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from thefuzz import fuzz

from core.models import Event, MatchedEvent, OddsEntry


logger = logging.getLogger(__name__)


# Team aliases for common teams across different naming conventions
TEAM_ALIASES = {
    # Serie A (Italy)
    "inter": ["inter", "inter milan", "internazionale", "fc inter", "inter milano", "fc internazionale"],
    "milan": ["milan", "ac milan", "a.c. milan", "ac milan 1899", "rossoneri"],
    "juventus": ["juventus", "juve", "juventus fc", "juventus turin"],
    "napoli": ["napoli", "ssc napoli", "napoli fc"],
    "roma": ["roma", "as roma", "roma fc", "a.s. roma"],
    "lazio": ["lazio", "ss lazio", "lazio roma", "s.s. lazio"],
    "atalanta": ["atalanta", "atalanta bergamo", "atalanta bc"],
    "fiorentina": ["fiorentina", "acf fiorentina", "fiorentina fc", "viola"],
    "torino": ["torino", "torino fc", "toro"],
    "bologna": ["bologna", "bologna fc", "bologna 1909"],

    # Premier League (England)
    "manchester_united": ["manchester united", "man utd", "man united", "mufc", "manchester utd"],
    "manchester_city": ["manchester city", "man city", "mcfc", "city"],
    "liverpool": ["liverpool", "liverpool fc", "lfc"],
    "arsenal": ["arsenal", "arsenal fc", "gunners"],
    "chelsea": ["chelsea", "chelsea fc", "blues"],
    "tottenham": ["tottenham", "tottenham hotspur", "spurs", "thfc"],
    "newcastle": ["newcastle", "newcastle united", "newcastle utd", "nufc", "magpies"],
    "west_ham": ["west ham", "west ham united", "west ham utd", "hammers"],
    "aston_villa": ["aston villa", "villa", "avfc"],
    "brighton": ["brighton", "brighton & hove albion", "brighton hove albion", "seagulls"],

    # La Liga (Spain)
    "barcelona": ["barcelona", "barca", "fc barcelona", "fcb"],
    "real_madrid": ["real madrid", "real", "madrid", "real madrid cf", "rmcf"],
    "atletico_madrid": ["atletico madrid", "atletico", "atleti", "atm", "atletico de madrid"],
    "sevilla": ["sevilla", "sevilla fc"],
    "valencia": ["valencia", "valencia cf"],
    "real_sociedad": ["real sociedad", "sociedad", "la real"],
    "villarreal": ["villarreal", "villarreal cf", "yellow submarine"],
    "real_betis": ["real betis", "betis", "real betis balompie"],

    # Bundesliga (Germany)
    "bayern_munich": ["bayern munich", "bayern", "bayern munchen", "fc bayern", "bayern münchen"],
    "borussia_dortmund": ["borussia dortmund", "dortmund", "bvb"],
    "rb_leipzig": ["rb leipzig", "leipzig", "rasenballsport leipzig"],
    "bayer_leverkusen": ["bayer leverkusen", "leverkusen", "bayer 04"],
    "eintracht_frankfurt": ["eintracht frankfurt", "frankfurt", "eintracht"],
    "wolfsburg": ["wolfsburg", "vfl wolfsburg"],
    "borussia_monchengladbach": ["borussia monchengladbach", "gladbach", "monchengladbach", "bmg"],

    # Ligue 1 (France)
    "psg": ["psg", "paris saint-germain", "paris saint germain", "paris sg", "paris"],
    "marseille": ["marseille", "olympique marseille", "om", "olympique de marseille"],
    "lyon": ["lyon", "olympique lyon", "olympique lyonnais", "ol"],
    "monaco": ["monaco", "as monaco", "asm"],
    "lille": ["lille", "losc", "losc lille"],

    # Other major teams
    "ajax": ["ajax", "afc ajax", "ajax amsterdam"],
    "psv": ["psv", "psv eindhoven"],
    "benfica": ["benfica", "sl benfica", "sport lisboa benfica"],
    "porto": ["porto", "fc porto"],
    "sporting_cp": ["sporting", "sporting cp", "sporting lisbon", "sporting clube de portugal"],
    "galatasaray": ["galatasaray", "galatasaray sk", "gala"],
    "fenerbahce": ["fenerbahce", "fenerbahce sk", "fener"],

    # NBA Teams
    "lakers": ["los angeles lakers", "la lakers", "lakers"],
    "celtics": ["boston celtics", "celtics"],
    "warriors": ["golden state warriors", "warriors", "gsw"],
    "heat": ["miami heat", "heat"],
    "bucks": ["milwaukee bucks", "bucks"],
    "suns": ["phoenix suns", "suns"],
    "nuggets": ["denver nuggets", "nuggets"],
    "sixers": ["philadelphia 76ers", "76ers", "sixers", "philadelphia sixers"],
}


class EventMatcher:
    """
    Matches sporting events across multiple platforms.

    Uses team name normalization and fuzzy matching to identify
    the same event listed on different betting platforms.
    """

    # Minimum fuzzy match score (0-100)
    DEFAULT_FUZZY_THRESHOLD = 85

    # Maximum time difference for events to be considered the same
    DEFAULT_TIME_TOLERANCE_HOURS = 2

    def __init__(
        self,
        fuzzy_threshold: int = DEFAULT_FUZZY_THRESHOLD,
        time_tolerance_hours: int = DEFAULT_TIME_TOLERANCE_HOURS,
        custom_aliases: Optional[Dict[str, List[str]]] = None,
    ):
        """
        Initialize the event matcher.

        Args:
            fuzzy_threshold: Minimum score for fuzzy matching (0-100)
            time_tolerance_hours: Maximum hours difference for time matching
            custom_aliases: Additional team name aliases
        """
        self.fuzzy_threshold = fuzzy_threshold
        self.time_tolerance = timedelta(hours=time_tolerance_hours)

        # Build alias lookup table
        self.team_aliases = self._build_alias_lookup(custom_aliases)

        self.logger = logging.getLogger(f"{__name__}.EventMatcher")

    def _build_alias_lookup(
        self,
        custom_aliases: Optional[Dict[str, List[str]]] = None
    ) -> Dict[str, str]:
        """
        Build a reverse lookup table from alias to canonical name.

        Args:
            custom_aliases: Additional aliases to include

        Returns:
            Dict mapping each alias to its canonical team name
        """
        lookup = {}

        # Add default aliases
        for canonical, aliases in TEAM_ALIASES.items():
            for alias in aliases:
                normalized = self._normalize_name(alias)
                lookup[normalized] = canonical

        # Add custom aliases
        if custom_aliases:
            for canonical, aliases in custom_aliases.items():
                for alias in aliases:
                    normalized = self._normalize_name(alias)
                    lookup[normalized] = canonical

        return lookup

    def _normalize_name(self, name: str) -> str:
        """
        Normalize a team name for matching.

        Args:
            name: Raw team name

        Returns:
            Normalized lowercase name
        """
        if not name:
            return ""

        # Lowercase
        normalized = name.lower().strip()

        # Remove common suffixes/prefixes
        patterns_to_remove = [
            r'\bfc\b', r'\bsc\b', r'\bac\b', r'\bss\b', r'\bsk\b',
            r'\bafc\b', r'\bcfc\b', r'\bssc\b', r'\bcf\b',
            r'\bunited\b', r'\bcity\b', r'\btown\b', r'\butd\b',
            r'\b1899\b', r'\b1909\b', r'\b1904\b', r'\b1906\b',  # Years
        ]

        for pattern in patterns_to_remove:
            normalized = re.sub(pattern, '', normalized)

        # Remove punctuation
        normalized = re.sub(r'[^\w\s]', '', normalized)

        # Collapse whitespace
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        return normalized

    def get_canonical_name(self, name: str) -> str:
        """
        Get the canonical team name using aliases.

        Args:
            name: Team name to look up

        Returns:
            Canonical name if found, otherwise normalized input
        """
        normalized = self._normalize_name(name)

        # Check direct alias match
        if normalized in self.team_aliases:
            return self.team_aliases[normalized]

        # Check partial matches in aliases
        for alias, canonical in self.team_aliases.items():
            if alias in normalized or normalized in alias:
                return canonical

        return normalized

    def match_all(
        self,
        events_by_platform: Dict[str, List[Dict[str, Any]]]
    ) -> List[MatchedEvent]:
        """
        Match events across all platforms.

        Args:
            events_by_platform: Dict mapping platform name to list of events

        Returns:
            List of matched events found on multiple platforms
        """
        matched_events: List[MatchedEvent] = []
        processed_keys: set = set()

        platforms = list(events_by_platform.keys())

        if len(platforms) < 2:
            self.logger.warning("Need at least 2 platforms to match events")
            return []

        # Use first platform as base
        base_platform = platforms[0]
        base_events = events_by_platform[base_platform]

        self.logger.info(
            f"Matching {len(base_events)} events from {base_platform} "
            f"against {len(platforms) - 1} other platforms"
        )

        for base_event in base_events:
            # Generate match key to avoid duplicates
            match_key = self._generate_match_key(base_event)

            if match_key in processed_keys:
                continue

            # Try to match with events from other platforms
            matched = self._find_matches(base_event, events_by_platform, platforms[1:])

            if matched:
                # Create MatchedEvent with base event
                matched_event = self._create_matched_event(base_event)

                # Add base platform event
                matched_event.add_platform_event(self._dict_to_event(base_event))

                # Add matched events from other platforms
                for platform_event in matched:
                    matched_event.add_platform_event(self._dict_to_event(platform_event))

                matched_events.append(matched_event)
                processed_keys.add(match_key)

                self.logger.debug(
                    f"Matched: {base_event['home_team']} vs {base_event['away_team']} "
                    f"across {len(matched_event.get_platforms())} platforms"
                )

        self.logger.info(f"Found {len(matched_events)} matched events across platforms")
        return matched_events

    def _find_matches(
        self,
        base_event: Dict[str, Any],
        events_by_platform: Dict[str, List[Dict[str, Any]]],
        other_platforms: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Find matching events from other platforms.

        Args:
            base_event: Event to match
            events_by_platform: All events by platform
            other_platforms: Platforms to search

        Returns:
            List of matching events from other platforms
        """
        matches = []

        base_home = self.get_canonical_name(base_event.get("home_team", ""))
        base_away = self.get_canonical_name(base_event.get("away_team", ""))
        base_time = base_event.get("start_time")
        base_sport = base_event.get("sport", "").lower()

        for platform in other_platforms:
            platform_events = events_by_platform.get(platform, [])

            for candidate in platform_events:
                # Must be same sport
                if candidate.get("sport", "").lower() != base_sport:
                    continue

                # Check time match
                if not self._times_match(base_time, candidate.get("start_time")):
                    continue

                # Check team names match
                cand_home = self.get_canonical_name(candidate.get("home_team", ""))
                cand_away = self.get_canonical_name(candidate.get("away_team", ""))

                match_result = self._teams_match(
                    base_home, base_away, cand_home, cand_away
                )

                if match_result[0]:
                    matches.append(candidate)
                    break  # Only one match per platform

        return matches

    def _teams_match(
        self,
        home_a: str,
        away_a: str,
        home_b: str,
        away_b: str,
    ) -> Tuple[bool, float]:
        """
        Check if two sets of teams represent the same match.

        Args:
            home_a, away_a: Team names from event A
            home_b, away_b: Team names from event B

        Returns:
            Tuple of (is_match, average_score)
        """
        # Try exact match first
        if home_a == home_b and away_a == away_b:
            return True, 100.0

        # Fuzzy match
        home_score = fuzz.ratio(home_a, home_b)
        away_score = fuzz.ratio(away_a, away_b)

        # Both teams must exceed threshold
        if home_score >= self.fuzzy_threshold and away_score >= self.fuzzy_threshold:
            avg_score = (home_score + away_score) / 2
            return True, avg_score

        # Try token set ratio for more flexible matching
        home_score_token = fuzz.token_set_ratio(home_a, home_b)
        away_score_token = fuzz.token_set_ratio(away_a, away_b)

        if home_score_token >= self.fuzzy_threshold and away_score_token >= self.fuzzy_threshold:
            avg_score = (home_score_token + away_score_token) / 2
            return True, avg_score

        return False, 0.0

    def _times_match(
        self,
        time_a: Optional[datetime],
        time_b: Optional[datetime],
    ) -> bool:
        """
        Check if two event times are within tolerance.

        Args:
            time_a: First event time
            time_b: Second event time

        Returns:
            True if times are within tolerance
        """
        if time_a is None or time_b is None:
            return False

        # Handle timezone-naive datetimes
        if time_a.tzinfo is None or time_b.tzinfo is None:
            # Compare as-is for naive datetimes
            diff = abs(time_a.replace(tzinfo=None) - time_b.replace(tzinfo=None))
        else:
            diff = abs(time_a - time_b)

        return diff <= self.time_tolerance

    def _generate_match_key(self, event: Dict[str, Any]) -> str:
        """
        Generate a unique key for deduplication.

        Args:
            event: Event dict

        Returns:
            Hash string for the event
        """
        home = self.get_canonical_name(event.get("home_team", ""))
        away = self.get_canonical_name(event.get("away_team", ""))
        sport = event.get("sport", "").lower()

        start_time = event.get("start_time")
        if start_time:
            # Round to nearest hour for grouping
            time_key = start_time.strftime("%Y%m%d%H")
        else:
            time_key = "unknown"

        key_str = f"{sport}:{home}:{away}:{time_key}"
        return hashlib.md5(key_str.encode()).hexdigest()[:16]

    def _create_matched_event(self, base_event: Dict[str, Any]) -> MatchedEvent:
        """
        Create a MatchedEvent from a base event.

        Args:
            base_event: Event dict to use as base

        Returns:
            New MatchedEvent instance
        """
        match_id = self._generate_match_key(base_event)

        return MatchedEvent(
            match_id=match_id,
            sport=base_event.get("sport", "unknown"),
            league=base_event.get("league", "Unknown League"),
            home_team=base_event.get("home_team", "Unknown"),
            away_team=base_event.get("away_team", "Unknown"),
            start_time=base_event.get("start_time", datetime.utcnow()),
        )

    def _dict_to_event(self, event_dict: Dict[str, Any]) -> Event:
        """
        Convert an event dict to an Event dataclass.

        Args:
            event_dict: Event dictionary

        Returns:
            Event instance
        """
        return Event(
            event_id=event_dict.get("event_id", ""),
            platform=event_dict.get("platform", "unknown"),
            sport=event_dict.get("sport", "unknown"),
            league=event_dict.get("league", "Unknown"),
            home_team=event_dict.get("home_team", "Unknown"),
            away_team=event_dict.get("away_team", "Unknown"),
            home_team_normalized=event_dict.get(
                "home_team_normalized",
                self._normalize_name(event_dict.get("home_team", ""))
            ),
            away_team_normalized=event_dict.get(
                "away_team_normalized",
                self._normalize_name(event_dict.get("away_team", ""))
            ),
            start_time=event_dict.get("start_time", datetime.utcnow()),
            markets=event_dict.get("markets", {}),
            url=event_dict.get("url"),
            raw_data=event_dict.get("raw_data"),
        )

    def match_events(
        self,
        events_a: List[Dict[str, Any]],
        events_b: List[Dict[str, Any]],
    ) -> List[MatchedEvent]:
        """
        Match events between two platforms (convenience method).

        Args:
            events_a: Events from platform A
            events_b: Events from platform B

        Returns:
            List of matched events
        """
        return self.match_all({
            "platform_a": events_a,
            "platform_b": events_b,
        })
