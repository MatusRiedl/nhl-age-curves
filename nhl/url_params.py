"""
nhl.url_params — Shareable URL encoding and decoding for the NHL Age Curves app.

Provides two public functions:
    encode_state_to_params(ss) -> dict
        Converts the current st.session_state into a flat dict suitable for
        writing to st.query_params.
    apply_params_to_state(params, ss) -> None
        Reads a dict of URL params and populates st.session_state accordingly,
        leaving any missing keys untouched so session-state defaults still apply.

Player entries are encoded as semicolon-separated "id|name" pairs.
Team entries use the same format with abbreviation instead of numeric id.
Setting st.query_params does not trigger a Streamlit rerun (Streamlit 1.30+).
"""

_VALID_SKATER_METRICS = {"Points", "Goals", "Assists", "+/-", "GP", "PPG", "SH%", "PIM", "TOI"}
_VALID_GOALIE_METRICS = {"Save %", "GAA", "Shutouts", "Wins", "GP", "Saves"}
_VALID_TEAM_METRICS   = {"Points", "Wins", "Win%", "Goals", "GF/G", "GA/G", "PP%", "PPG"}

_CAT_ENCODE = {"Skater": "S", "Goalie": "G", "Team": "T"}
_CAT_DECODE = {v: k for k, v in _CAT_ENCODE.items()}

_XM_ENCODE  = {"Age": "A", "Games Played": "GP", "Season Year": "SY"}
_XM_DECODE  = {v: k for k, v in _XM_ENCODE.items()}

_BOOL_PARAMS = {
    "sm":  "do_smooth",
    "pr":  "do_predict",
    "era": "do_era",
    "cu":  "do_cumul_toggle",
    "bl":  "do_base",
}


def encode_state_to_params(ss) -> dict:
    """Convert current session state into a flat URL params dict.

    Args:
        ss: st.session_state (or any dict-like mapping) containing app state.

    Returns:
        dict mapping URL param keys to encoded string values. Player and team
        keys are omitted entirely when their corresponding dicts are empty.
    """
    params = {}

    params["cat"] = _CAT_ENCODE.get(ss.get("stat_category", "Skater"), "S")

    if "skater_metric" in ss:
        params["sk_m"] = ss["skater_metric"]
    if "goalie_metric" in ss:
        params["go_m"] = ss["goalie_metric"]
    if "team_metric" in ss:
        params["tm_m"] = ss["team_metric"]

    params["sp"]  = ss.get("season_type", "Regular")
    params["xm"]  = _XM_ENCODE.get(ss.get("x_axis_mode", "Age"), "A")
    params["lg"]  = ",".join(ss.get("league_filter") or ["NHL"])

    for url_key, ss_key in _BOOL_PARAMS.items():
        params[url_key] = "1" if ss.get(ss_key) else "0"

    pl = ss.get("players") or {}
    if pl:
        params["pl"] = ";".join(f"{pid}|{name}" for pid, name in pl.items())

    tm = ss.get("teams") or {}
    if tm:
        params["tm"] = ";".join(f"{abbr}|{name}" for abbr, name in tm.items())

    return params


def apply_params_to_state(params: dict, ss) -> None:
    """Populate session state from a URL params dict.

    Only keys present in params are written; absent keys leave session state
    untouched so app.py default values still apply normally.

    Args:
        params: dict of URL param key to value string (from dict(st.query_params)).
        ss: st.session_state (or any dict-like mapping) to write into.

    Returns:
        None
    """
    if not params:
        return

    if "cat" in params:
        ss["stat_category"] = _CAT_DECODE.get(params["cat"], "Skater")

    if "sk_m" in params and params["sk_m"] in _VALID_SKATER_METRICS:
        ss["skater_metric"] = params["sk_m"]
    if "go_m" in params and params["go_m"] in _VALID_GOALIE_METRICS:
        ss["goalie_metric"] = params["go_m"]
    if "tm_m" in params and params["tm_m"] in _VALID_TEAM_METRICS:
        ss["team_metric"] = params["tm_m"]

    if "sp" in params and params["sp"] in ("Regular", "Playoffs", "Both"):
        ss["season_type"] = params["sp"]

    if "xm" in params:
        ss["x_axis_mode"] = _XM_DECODE.get(params["xm"], "Age")

    if "lg" in params and params["lg"]:
        from nhl.constants import NHLE_MULTIPLIERS
        leagues = [lg for lg in params["lg"].split(",") if lg in NHLE_MULTIPLIERS]
        if leagues:
            ss["league_filter"] = leagues

    for url_key, ss_key in _BOOL_PARAMS.items():
        if url_key in params:
            ss[ss_key] = params[url_key] == "1"

    # Decode unified players param; also accept legacy sk/go params for backward compat.
    _players = {}
    for _key in ("sk", "go", "pl"):
        if _key in params and params[_key]:
            for entry in params[_key].split(";"):
                if "|" in entry:
                    pid, name = entry.split("|", 1)
                    if pid.strip():
                        _players[pid.strip()] = name.strip()
    if _players:
        ss["players"] = _players

    if "tm" in params and params["tm"]:
        teams = {}
        for entry in params["tm"].split(";"):
            if "|" in entry:
                abbr, name = entry.split("|", 1)
                if abbr.strip():
                    teams[abbr.strip()] = name.strip()
        if teams:
            ss["teams"] = teams
