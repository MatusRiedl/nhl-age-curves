"""
nhl.constants — Shared configuration constants for the NHL Age Curves app.

All URL strings, lookup tables, rate-stat sets, NHLe multipliers, stat caps/floors,
and the dynamic current-season year live here.  Nothing in this module imports from
any other project module, making it safe to import from every other module without
risk of circular dependencies.
"""

from datetime import datetime

# ---------------------------------------------------------------------------
# API endpoint templates
# ---------------------------------------------------------------------------

SEARCH_URL    = "https://search.d3.nhle.com/api/v1/search/player"
"""D3 player-search endpoint — full-name prefix matching, returns up to 40 results."""

STATS_URL     = "https://api-web.nhle.com/v1/player/{}/landing"
"""Per-player stats endpoint; format with player_id to get seasonTotals."""

ROSTER_URL    = "https://api-web.nhle.com/v1/roster/{}/current"
"""Current-roster endpoint; format with team abbreviation (e.g. 'EDM')."""

TEAM_STATS_URL = "https://api.nhle.com/stats/rest/en/team/summary"
"""Team-season summary endpoint; returns all team-season rows with limit=-1."""

TEAM_LIST_URL  = "https://api.nhle.com/stats/rest/en/team"
"""Team-list endpoint; used to build teamId -> triCode lookup map."""

# ---------------------------------------------------------------------------
# Active NHL franchises (as of 2024-25 season)
# ---------------------------------------------------------------------------

ACTIVE_TEAMS = {
    "ANA": "Anaheim Ducks",       "BOS": "Boston Bruins",
    "BUF": "Buffalo Sabres",      "CGY": "Calgary Flames",
    "CAR": "Carolina Hurricanes", "CHI": "Chicago Blackhawks",
    "COL": "Colorado Avalanche",  "CBJ": "Columbus Blue Jackets",
    "DAL": "Dallas Stars",        "DET": "Detroit Red Wings",
    "EDM": "Edmonton Oilers",     "FLA": "Florida Panthers",
    "LAK": "Los Angeles Kings",   "MIN": "Minnesota Wild",
    "MTL": "Montreal Canadiens",  "NSH": "Nashville Predators",
    "NJD": "New Jersey Devils",   "NYI": "New York Islanders",
    "NYR": "New York Rangers",    "OTT": "Ottawa Senators",
    "PHI": "Philadelphia Flyers", "PIT": "Pittsburgh Penguins",
    "SJS": "San Jose Sharks",     "SEA": "Seattle Kraken",
    "STL": "St. Louis Blues",     "TBL": "Tampa Bay Lightning",
    "TOR": "Toronto Maple Leafs", "UTA": "Utah Hockey Club",
    "VAN": "Vancouver Canucks",   "VGK": "Vegas Golden Knights",
    "WSH": "Washington Capitals", "WPG": "Winnipeg Jets",
}
"""32-team abbreviation -> full name mapping used across sidebar and pipeline."""

TEAM_FOUNDED: dict[str, int] = {
    "ANA": 1993, "BOS": 1924, "BUF": 1970, "CGY": 1972,
    "CAR": 1979, "CHI": 1926, "COL": 1972, "CBJ": 2000,
    "DAL": 1967, "DET": 1926, "EDM": 1979, "FLA": 1993,
    "LAK": 1967, "MIN": 2000, "MTL": 1917, "NSH": 1998,
    "NJD": 1974, "NYI": 1972, "NYR": 1926, "OTT": 1992,
    "PHI": 1967, "PIT": 1967, "SJS": 1991, "SEA": 2021,
    "STL": 1967, "TBL": 1992, "TOR": 1917, "UTA": 2024,
    "VAN": 1970, "VGK": 2017, "WSH": 1974, "WPG": 1999,
}
"""NHL franchise founding year (year the current org entered the NHL)."""

# ---------------------------------------------------------------------------
# Stat classification sets
# ---------------------------------------------------------------------------

RATE_STATS = {'PPG', 'Save %', 'GAA', 'SH%', 'TOI'}
"""
Stats that require *mean* (not sum) aggregation during pivot/groupby.
These are never cumulatively summed and their KNN uses mean aggfunc.
"""

TEAM_RATE_STATS = {'GF/G', 'GA/G', 'Win%', 'PP%', 'PPG'}
"""Team-mode rate stats — same semantics as RATE_STATS but for team pipeline."""

TEAM_METRICS = ["Points", "Wins", "Win%", "Goals", "GF/G", "GA/G", "PP%", "PPG"]
"""Ordered list of selectable metrics in team mode."""

ML_SUPPORTED_METRICS = [
    'Points', 'Goals', 'Assists', '+/-', 'PPG',
    'PIM', 'Wins', 'Shutouts', 'Saves', 'Save %', 'GAA',
]
"""
Metrics the KNN engine can project.
GP is intentionally excluded — survivorship bias makes KNN unreliable for games played.
GP projection uses the dedicated 4-phase durability curve instead.
"""

NO_PROJECTION_METRICS = {'GP', 'SH%', 'TOI'}
"""
Metrics for which the Forecast projection line is suppressed entirely.
Neither KNN nor the linear fallback runs for these metrics.
GP: survivorship bias corrupts both skater and goalie projections.
SH%/TOI: linear extrapolation yields implausible results for skaters.
"""

# ---------------------------------------------------------------------------
# NHLe (NHL Equivalency) multipliers — 2024 Bacon/Chatel model values
# ---------------------------------------------------------------------------

NHLE_MULTIPLIERS = {
    'NHL':   1.0,
    'KHL':   0.77,
    'SHL':   0.57,
    'AHL':   0.39,
    'NLA':   0.46,
    'LIIGA': 0.44,
    'NCAA':  0.19,
    'OHL':   0.14,
    'WHL':   0.14,
    'QMJHL': 0.11,
}
"""
League -> scoring-translation multiplier.  Applied to Points, Goals, Assists for
non-NHL rows.  Leagues not listed are dropped (noise filter).
Keys are uppercase to match the leagueAbbrev field returned by the NHL API.
"""

# ---------------------------------------------------------------------------
# Dynamic current season year
# ---------------------------------------------------------------------------

_now = datetime.now()
CURRENT_SEASON_YEAR: int = _now.year if _now.month >= 9 else _now.year - 1
"""
Start year of the current NHL season (e.g. 2024 for the 2024-25 season).
Computed once at import time from the system clock; NHL seasons start in October,
so January-August still belong to the season that started the prior calendar year.
"""

# ---------------------------------------------------------------------------
# Stat caps and floors (applied to every projected year)
# ---------------------------------------------------------------------------

STAT_CAPS: dict[str, float] = {
    "Points":  155,
    "Goals":    70,
    "Assists": 105,
    "+/-":      60,
    "GP":       82,   # skaters; goalie cap overridden to 65 inline in knn_engine
    "PPG":       1.9,
    "SH%":      25,
    "PIM":     150,
    "TOI":      28,
    "Save %":   93.5,
    "GAA":       1.8,  # NOTE: GAA cap is a *floor* — no projection below 1.8
    "Wins":     45,
    "Shutouts": 10,
    "Saves":  2000,
}
"""
Per-metric upper bounds applied during projection.
GAA is special: its cap acts as a floor (no goalie can project below 1.8 GAA).
"""

STAT_FLOORS: dict[str, float] = {
    "+/-": -60,
}
"""
Per-metric lower bounds applied during projection.
+/- has a symmetric floor (-60) to mirror its ceiling (60).
"""
