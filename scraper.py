import requests
import pandas as pd
import concurrent.futures
import time

SKATER_RECORDS_URL = "https://records.nhl.com/site/api/skater-career-scoring-regular-season"
GOALIE_RECORDS_URL = "https://records.nhl.com/site/api/goalie-career-stats"
PLAYER_API_URL = "https://api-web.nhle.com/v1/player/{}/landing"

def get_era_multiplier(year):
    if 1980 <= year <= 1992: return 0.80  
    if 1997 <= year <= 2004: return 1.15  
    if 2005 <= year <= 2017: return 1.05  
    return 1.0 

def get_all_player_ids():
    print("Fetching master list of all NHL players in history...")
    skaters = requests.get(SKATER_RECORDS_URL).json().get('data', [])
    goalies = requests.get(GOALIE_RECORDS_URL).json().get('data', [])
    
    ids = set()
    for p in skaters: ids.add(int(p['playerId']))
    for p in goalies: ids.add(int(p['playerId']))
    
    print(f"Found {len(ids)} total players.")
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
            league = str(s.get('leagueAbbrev', '')).strip().upper()
            game_type = str(s.get('gameTypeId', ''))
            
            # Only grab NHL Regular Season data for the baseline model
            if league == 'NHL' and game_type == '2':
                season_str = str(s.get('season', ''))
                season_year = int(season_str[:4]) if len(season_str) >= 4 else 2000
                age = season_year - birth_year
                
                gp = max(s.get('gamesPlayed', 1), 1)
                
                # Era-Adjust the points immediately so the database is pre-normalized
                raw_pts = s.get('points', 0)
                era_mult = get_era_multiplier(season_year) if not is_goalie else 1.0
                adj_pts = raw_pts * era_mult
                
                seasons.append({
                    "PlayerID": player_id,
                    "Age": age,
                    "SeasonYear": season_year,
                    "Position": position,
                    "GP": gp,
                    "Points": adj_pts,
                    "Goals": s.get('goals', 0),
                    "Assists": s.get('assists', 0),
                    "PIM": s.get('pim', 0) or s.get('penaltyMinutes', 0),
                    "+/-": s.get('plusMinus', 0),
                    "Wins": s.get('wins', 0),
                    "Shutouts": s.get('shutouts', 0),
                    "Saves": s.get('saves', s.get('shotsAgainst', 0) - s.get('goalsAgainst', 0)),
                    "SavePct": float(s.get('savePctg', 0.0)),
                    "GAA": float(s.get('goalsAgainstAvg', 0.0))
                })
        return seasons
    except:
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
    
    # Clean and optimize the dataframe to keep the file size tiny
    df = df.groupby(['PlayerID', 'Age', 'Position']).sum(numeric_only=True).reset_index()
    
    print(f"Scraping complete in {round(time.time() - start_time, 1)} seconds.")
    print(f"Total valid NHL seasons recorded: {len(df)}")
    
    # Save as highly-compressed Parquet
    df.to_parquet("nhl_historical_seasons.parquet", index=False)
    print("✅ Saved to nhl_historical_seasons.parquet")

if __name__ == "__main__":
    main()