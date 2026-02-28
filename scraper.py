import requests
import pandas as pd
import concurrent.futures
import time
from datetime import datetime

SKATER_RECORDS_URL  = "https://records.nhl.com/site/api/skater-career-scoring-regular-season"
GOALIE_RECORDS_URL  = "https://records.nhl.com/site/api/goalie-career-stats"
PLAYER_API_URL      = "https://api-web.nhle.com/v1/player/{}/landing"

# NHL stats REST API — returns all players for a specific season (limit=-1 = no cap).
# seasonId format: start_year + end_year, e.g. 20242025 for 2024-25.
SEASON_SKATER_URL   = "https://api.nhle.com/stats/rest/en/skater/summary?limit=-1&start=0&sort=points&cayenneExp=seasonId={sid}"
SEASON_GOALIE_URL   = "https://api.nhle.com/stats/rest/en/goalie/summary?limit=-1&start=0&sort=wins&cayenneExp=seasonId={sid}"


def get_all_season_ids():
    """Return all NHL season IDs from 1917-18 through the most recently completed season."""
    now = datetime.now()
    end_year = now.year if now.month >= 9 else now.year - 1
    return [f"{y}{y + 1}" for y in range(1917, end_year + 1)]


def _fetch_all_records(base_url):
    """Paginate through an NHL records endpoint until all results are collected.
    The API defaults to ~25 results per call; without pagination the scraper would
    only capture the first page — that's why historical seasons showed 9 players."""
    ids = set()
    start = 0
    page_size = 500   # large page to minimise round-trips
    while True:
        try:
            url  = f"{base_url}?start={start}&limit={page_size}"
            resp = requests.get(url, timeout=15).json()
            page = resp.get('data', [])
            for p in page:
                ids.add(int(p['playerId']))
            # Stop when this page is smaller than the requested limit (last page).
            if len(page) < page_size:
                break
            start += page_size
        except Exception as e:
            print(f"  Warning: records page failed (start={start}): {e}")
            break
    return ids


def get_all_player_ids():
    """Collect all NHL player IDs from two sources:
    1. Career records endpoints (all-time historical players) — paginated.
    2. Season summary endpoints for the last 3 completed seasons (catches
       first-year / second-year players not yet in career records).
    """
    print("Fetching master list of all NHL players in history...")
    ids = set()

    # --- Source 1: all-time career records (paginated) ---
    for url in [SKATER_RECORDS_URL, GOALIE_RECORDS_URL]:
        ids |= _fetch_all_records(url)

    print(f"  Career records: {len(ids)} players")

    # --- Source 2: all historical season summaries (catches players missing from career records) ---
    # The career records endpoint is a scoring leaderboard — role players with modest career
    # totals may be absent. Sweeping every season ensures complete roster coverage.
    recent_ids = set()
    all_sids = get_all_season_ids()
    print(f"  Sweeping {len(all_sids)} seasons for additional player IDs...")
    for sid in all_sids:
        for url_tpl in [SEASON_SKATER_URL, SEASON_GOALIE_URL]:
            try:
                url = url_tpl.format(sid=sid)
                data = requests.get(url, timeout=15).json().get('data', [])
                for p in data:
                    pid = p.get('playerId')
                    if pid:
                        recent_ids.add(int(pid))
            except Exception as e:
                print(f"  Warning: season {sid} fetch failed: {e}")

    print(f"  Season-sweep additions: {len(recent_ids - ids)} new players")
    ids |= recent_ids
    print(f"  Total unique player IDs: {len(ids)}")
    return list(ids)


def fetch_player_data(player_id):
    try:
        res = requests.get(PLAYER_API_URL.format(player_id), timeout=5).json()
        birth_date = str(res.get('birthDate', '2000'))
        birth_year = int(birth_date[:4]) if len(birth_date) >= 4 else 2000
        position = res.get('positionCode', 'S')
        is_goalie = position == 'G'

        seasons = []
        for s in res.get('seasonTotals', []):
            league    = str(s.get('leagueAbbrev', '')).strip().upper()
            game_type = str(s.get('gameTypeId', ''))

            # Only NHL Regular Season data for the baseline model
            if league == 'NHL' and game_type == '2':
                season_str  = str(s.get('season', ''))
                season_year = int(season_str[:4]) if len(season_str) >= 4 else 2000
                age         = season_year - birth_year
                gp          = max(s.get('gamesPlayed', 1), 1)

                # Store RAW Points — no era adjustment baked in.
                # The app applies era adjustment on demand using its 8-period multiplier.
                raw_pts = s.get('points', 0)

                seasons.append({
                    "PlayerID":   player_id,
                    "Age":        age,
                    "SeasonYear": season_year,
                    "Position":   position,
                    "GP":         gp,
                    "Points":     raw_pts,           # RAW (no era adjustment)
                    "Goals":      s.get('goals', 0),
                    "Assists":    s.get('assists', 0),
                    "PIM":        s.get('pim', 0) or s.get('penaltyMinutes', 0),
                    "+/-":        s.get('plusMinus', 0),
                    "Wins":       s.get('wins', 0),
                    "Shutouts":   s.get('shutouts', 0),
                    "Saves":      s.get('saves', s.get('shotsAgainst', 0) - s.get('goalsAgainst', 0)),
                    "SavePct":    float(s.get('savePctg', 0.0)),
                    "GAA":        float(s.get('goalsAgainstAvg', 0.0)),
                })
        return seasons
    except Exception:
        return []


def main():
    player_ids = get_all_player_ids()
    all_seasons_data = []

    print("Initiating multi-threaded scraping... This will take a couple of minutes.")
    start_time = time.time()

    # Fire 20 requests at a time to strip-mine the API
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(fetch_player_data, player_ids))

    for res in results:
        if res:
            all_seasons_data.extend(res)

    df = pd.DataFrame(all_seasons_data)

    # Collapse traded-player duplicates (same player, same season, same age) into one row.
    # SeasonYear is now part of the key so it is preserved correctly — previously it was
    # excluded, causing SeasonYear to be summed (2022+2022=4044) for traded players.
    df = df.groupby(['PlayerID', 'SeasonYear', 'Age', 'Position']).sum(numeric_only=True).reset_index()

    elapsed = round(time.time() - start_time, 1)
    print(f"Scraping complete in {elapsed} seconds.")
    print(f"Total valid NHL season-rows recorded: {len(df)}")
    print(f"Unique players: {df['PlayerID'].nunique()}")
    print(f"Season range: {df['SeasonYear'].min()} – {df['SeasonYear'].max()}")

    # Save as highly-compressed Parquet
    df.to_parquet("nhl_historical_seasons.parquet", index=False, compression="snappy")
    print("✅ Saved to nhl_historical_seasons.parquet")


if __name__ == "__main__":
    main()
