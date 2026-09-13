import streamlit as st
import pandas as pd
import statsapi
import datetime

# Set page config
st.set_page_config(
    page_title="MLB Batting Lineup Optimizer",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="expanded"
)


def parse_batting_stat(stat, key):
    """Safely parse a batting stat field (may be a '.XXX' string or a number)."""
    v = stat.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


@st.cache_data(ttl=1800, show_spinner="Retrieving latest starting lineup...")
def get_latest_lineup(team_id):
    """Return the starting batting order for a team's most recent game.

    Each row is built entirely from the boxscore (team data) keyed by player ID:
    {id, name, pos, bat_hand, obp, avg, slg, ops, hits, hr}. No name matching involved.

    Returns (lineup_rows, game_summary). lineup_rows is a list of dicts.
    """
    try:
        today = datetime.date.today()
        start_date = (today - datetime.timedelta(days=14)).strftime('%m/%d/%Y')
        end_date = today.strftime('%m/%d/%Y')

        sched = statsapi.schedule(team=team_id, start_date=start_date, end_date=end_date)
        if not sched:
            return [], "No games scheduled in the last 14 days."

        played_games = [g for g in sched if g.get('status') in ('Final', 'Live', 'In Progress', 'Completed Early', 'Warmup')]
        candidates = list(reversed(played_games)) or list(reversed(sched))

        for game in candidates:
            game_pk = game['game_id']
            game_date = game.get('game_date', 'Unknown Date')
            summary = game.get('summary', f"Game {game_pk}")

            box = statsapi.boxscore_data(game_pk)
            is_home = game.get('home_id') == team_id
            team_box = box['home'] if is_home else box['away']

            batting_order_ids = team_box.get('battingOrder', [])
            if not batting_order_ids:
                continue

            players_dict = team_box.get('players', {})
            rows = []
            for player_id in batting_order_ids:
                key = f"ID{player_id}"
                if key not in players_dict:
                    continue
                p_info = players_dict[key]
                stat = (p_info.get('seasonStats') or {}).get('batting') or {}
                rows.append({
                    'id': player_id,
                    'name': p_info['person']['fullName'],
                    'pos': p_info['position']['abbreviation'],
                    'obp': parse_batting_stat(stat, 'obp'),
                    'avg': parse_batting_stat(stat, 'avg'),
                    'slg': parse_batting_stat(stat, 'slg'),
                    'ops': parse_batting_stat(stat, 'ops'),
                    'hits': parse_batting_stat(stat, 'hits'),
                    'hr': parse_batting_stat(stat, 'homeRuns'),
                })

            if rows:
                bat_hands = get_batting_hands([r['id'] for r in rows])
                for r in rows:
                    r['bat_hand'] = bat_hands.get(r['id'], 'N/A')
                return rows, f"{summary} ({game_date})"

        return [], "No games with starting lineups found in the last 14 days."
    except Exception as e:
        return [], f"Error fetching lineup: {e}"
@st.cache_data(ttl=3600, show_spinner="Fetching active roster...")
def get_active_roster(team_id):
    """Fetch the active roster for a given team, mapping player ID -> (name, position)."""
    try:
        roster_data = statsapi.get("team_roster", {"teamId": team_id})
        return {
            p["person"]["id"]: {
                "name": p["person"]["fullName"],
                "pos": p["position"]["abbreviation"],
            }
            for p in roster_data.get("roster", [])
        }
    except Exception as e:
        st.warning(f"Could not fetch active roster from StatsAPI: {e}")
        return {}


@st.cache_data(ttl=86400, show_spinner="Fetching batting hands...")
def get_batting_hands(player_ids):
    """Return a dict mapping player ID -> batting side description (e.g. 'Left', 'Right', 'Switch')."""
    if not player_ids:
        return {}
    try:
        ids = ",".join(str(i) for i in player_ids)
        data = statsapi.get("people", {"personIds": ids})
        people = data.get("people", [])
        return {p["id"]: p.get("batSide", {}).get("description", "N/A") for p in people}
    except Exception as e:
        st.warning(f"Could not fetch batting hands: {e}")
        return {}


@st.cache_data(ttl=86400, show_spinner="Loading MLB teams...")
def get_mlb_teams():
    """Fetch all active MLB teams for the current season."""
    teams_raw = statsapi.lookup_team("", activeStatus="Y", season=datetime.date.today().year)
    teams_raw.sort(key=lambda t: t["name"])
    return teams_raw


@st.cache_data(ttl=3600, show_spinner="Calculating league averages...")
def get_league_totals(season):
    """Get league-wide hitting totals for wRC+ calculation."""
    data = statsapi.get("stats", {
        "statGroup": "hitting", "season": season,
        "sportIds": 1, "group": "hitting",
        "stats": "season", "limit": 10000,
    })
    splits = data["stats"][0]["splits"] if data.get("stats") else []

    lg = {
        "atBats": 0, "hits": 0, "doubles": 0, "triples": 0, "homeRuns": 0,
        "baseOnBalls": 0, "intentionalWalks": 0, "hitByPitch": 0,
        "sacFlies": 0, "plateAppearances": 0, "runs": 0,
    }
    for player in splits:
        s = player.get("stat", {})
        for key in lg:
            if key in s and s[key] is not None:
                lg[key] += int(s[key])
    return lg


def compute_wrc_plus(stat, lg_totals):
    """Compute wRC+ for a player from their hitting season stat dict + league totals.

    Formula mirrors app.py (weighted runs created plus, park-factor adjusted
    without park factor). Returns a float, or None if no plate appearances.
    """
    def num(key):
        v = stat.get(key)
        return int(v) if v not in (None, '') else 0

    pa = num('plateAppearances')
    ab = num('atBats')
    h = num('hits')
    dbl = num('doubles')
    triple = num('triples')
    hr = num('homeRuns')
    bb = num('baseOnBalls')
    ibb = num('intentionalWalks')
    hbp = num('hitByPitch')
    sf = num('sacFlies')

    if pa <= 0:
        return None

    wOBA_scale = 1.18

    # League constants
    lg = lg_totals
    lg_wOBA_num = (0.69 * (lg["baseOnBalls"] - lg["intentionalWalks"])
                   + 0.72 * lg["hitByPitch"]
                   + 0.89 * (lg["hits"] - lg["doubles"] - lg["triples"] - lg["homeRuns"])
                   + 1.27 * lg["doubles"] + 1.62 * lg["triples"] + 2.10 * lg["homeRuns"])
    lg_wOBA_den = (lg["atBats"] + lg["baseOnBalls"] - lg["intentionalWalks"]
                   + lg["sacFlies"] + lg["hitByPitch"])
    lg_wOBA = lg_wOBA_num / lg_wOBA_den if lg_wOBA_den > 0 else 0
    lg_R_per_PA = lg["runs"] / lg["plateAppearances"] if lg["plateAppearances"] > 0 else 0

    # Player wOBA
    player_wOBA_num = (0.69 * (bb - ibb) + 0.72 * hbp
                       + 0.89 * (h - dbl - triple - hr)
                       + 1.27 * dbl + 1.62 * triple + 2.10 * hr)
    player_wOBA_den = ab + bb - ibb + sf + hbp
    wOBA = player_wOBA_num / player_wOBA_den if player_wOBA_den > 0 else 0

    wRAA = ((wOBA - lg_wOBA) / wOBA_scale) * pa
    wRC = wRAA + (lg_R_per_PA * pa)

    if lg_R_per_PA > 0:
        wrc_plus = (((wRC / pa) / lg_R_per_PA) * (1 / wOBA_scale)
                    + (1 - (1 / wOBA_scale))) * 100
        return round(wrc_plus, 1)
    return None


@st.cache_data(ttl=3600, show_spinner="Fetching team batting stats...")
def get_team_batting_stats(team_id, season, player_ids):
    """Fetch season batting stats for the given player IDs via the people endpoint.

    Returns a dict {player_id: {name, pos, bat_hand, obp, avg, slg, ops, hits, hr, wrc_plus}},
    keyed by player ID so no name matching is ever needed. wRC+ is computed from the
    raw hitting season stats (statsapi does not expose wRC+ directly).
    """
    if not player_ids:
        return {}
    results = {}
    try:
        lg_totals = get_league_totals(season)
        ids = ",".join(str(i) for i in player_ids)
        data = statsapi.get("people", {
            "personIds": ids,
            "hydrate": f"stats(group=hitting,type=season,season={season},sportId=1)",
        })
        for p in data.get("people", []):
            pid = p["id"]
            stat = {}
            for group in p.get("stats", []):
                if group.get("group", {}).get("displayName") == "hitting":
                    splits = group.get("splits", [])
                    if splits:
                        stat = splits[0].get("stat", {})
            results[pid] = {
                'name': p.get('fullName', 'Unknown'),
                'pos': p.get('primaryPosition', {}).get('abbreviation', ''),
                'bat_hand': p.get('batSide', {}).get('description', 'N/A'),
                'obp': parse_batting_stat(stat, 'obp'),
                'avg': parse_batting_stat(stat, 'avg'),
                'slg': parse_batting_stat(stat, 'slg'),
                'ops': parse_batting_stat(stat, 'ops'),
                'hits': parse_batting_stat(stat, 'hits'),
                'hr': parse_batting_stat(stat, 'homeRuns'),
                'wrc_plus': compute_wrc_plus(stat, lg_totals),
            }
    except Exception as e:
        st.warning(f"Could not fetch team batting stats: {e}")
    return {pid: results.get(pid) for pid in player_ids if pid in results}


@st.cache_data
def convert_df_to_csv(df):
    """Convert dataframe to CSV format for download button."""
    return df.to_csv(index=False).encode('utf-8')
def build_hybrid_lineup(lineup_rows):
    """Build the hybrid optimized batting order.

    Rules:
      1. Batter with the highest OBP leads off (slot 1).
      2. Batter with the best wRC+ hits 2nd.
      3. Slots 3-9 are ranked by wRC+ descending.
      4. Handedness constraint (slots 3-9): if the two most recently placed
         batters share the same handedness, the next batter must be of a
         different handedness, to avoid stacking same-handed hitters and
         conceding an advantage to the pitcher.

    Returns a new list of row dicts in optimized order.
    """
    if not lineup_rows:
        return []

    def wrc_key(row):
        return (row.get('wrc_plus') is None, -(row.get('wrc_plus') or 0.0))

    def obp_key(row):
        return (row.get('obp') is None, -(row.get('obp') or 0.0))

    remaining = list(lineup_rows)

    # Slot 1: highest OBP leads off.
    lead = min(remaining, key=obp_key)
    order = [lead]
    remaining = [r for r in remaining if r is not lead]

    # Slot 2: best wRC+ hits 2nd.
    second = min(remaining, key=wrc_key)
    order.append(second)
    remaining = [r for r in remaining if r is not second]

    # Slots 3-9: rank by wRC+ desc, alternating handedness when needed.
    placed_hands = []  # handedness of batters already placed in slots 3+.
    while remaining:
        need_opposite = False
        if len(placed_hands) >= 2:
            last, prev = placed_hands[-1], placed_hands[-2]
            if last == prev and last not in (None, '', 'N/A'):
                need_opposite = True

        candidates = remaining
        if need_opposite:
            oppo = [r for r in remaining if r.get('bat_hand') != placed_hands[-1]]
            if oppo:
                candidates = oppo

        pick = min(candidates, key=wrc_key)
        order.append(pick)
        remaining = [r for r in remaining if r is not pick]
        placed_hands.append(pick.get('bat_hand'))

    return order


def build_tango_lineup(lineup_rows):
    """Build the batting order from the Bluebird Banter / 'The Book' article.

    Sherman's template from 'Optimizing Order, Part 1' (Bluebird Banter, based on
    Tango's The Book), ranking batters by quality where quality = wRC+:
      - The three best hitters (ranks 1-3) bat in slots #1, #2, #4.
      - The 4th- and 5th-best hitters bat in slots #3 and #5.
      - Slots #6 through #9 take the remaining players in descending quality.

    Equivalent to a rank->slot map of {1:1, 2:2, 3:4, 4:3, 5:5, k:k for k>=6},
    i.e. the only shuffle is the deliberate #3 / #4 swap. Handedness is ignored.

    Players without wRC+ (No Stats) rank as worst and fall to the tail.

    Returns a new list of row dicts in optimized order.
    """
    if not lineup_rows:
        return []

    def wrc_key(row):
        return (row.get('wrc_plus') is None, -(row.get('wrc_plus') or 0.0))

    ranked = sorted(lineup_rows, key=wrc_key)  # best wRC+ first

    by_slot = {}
    for rank, row in enumerate(ranked, start=1):
        slot = {1: 1, 2: 2, 3: 4, 4: 3, 5: 5}.get(rank, rank)
        by_slot[slot] = row

    return [by_slot[s] for s in sorted(by_slot)]


def prepare_optimized_lineups(lineup_rows):
    """Assign actual batting-order slots and build the optimized orders.

    Mutates each row dict in-place by adding 'actual_slot', 'has_stats', 'has_wrc',
    'opt_slot', 'wrc_slot', 'hybrid_slot' and 'tango_slot'. Returns
    (obp_optimized_lineup, wrc_optimized_lineup, hybrid_lineup, tango_lineup).
    """
    for idx, row in enumerate(lineup_rows, 1):
        row['actual_slot'] = idx
        row['has_stats'] = row['obp'] is not None
        row.setdefault('wrc_plus', None)
        row.setdefault('has_wrc', row['wrc_plus'] is not None)

    # OBP-optimized order: sort descending by OBP (None handled as worst).
    obp_optimized_lineup = sorted(lineup_rows, key=lambda x: (x['obp'] is None, -(x['obp'] or 0.0)))
    for idx, row in enumerate(obp_optimized_lineup, 1):
        row['opt_slot'] = idx

    # wRC+-optimized order: sort descending by wRC+ (None handled as worst).
    wrc_optimized_lineup = sorted(lineup_rows, key=lambda x: (x['wrc_plus'] is None, -(x['wrc_plus'] or 0.0)))
    for idx, row in enumerate(wrc_optimized_lineup, 1):
        row['wrc_slot'] = idx

    # Hybrid optimized order: OBP leader first, best wRC+ second,
    # then wRC+ ranking with handedness alternation for slots 3-9.
    hybrid_lineup = build_hybrid_lineup(lineup_rows)
    for idx, row in enumerate(hybrid_lineup, 1):
        row['hybrid_slot'] = idx

    # The Book (Sherman) order: fixed slot template by wRC+ quality.
    tango_lineup = build_tango_lineup(lineup_rows)
    for idx, row in enumerate(tango_lineup, 1):
        row['tango_slot'] = idx

    return obp_optimized_lineup, wrc_optimized_lineup, hybrid_lineup, tango_lineup


def build_display_df(optimized_lineup, slot_key, stats):
    """Build a display DataFrame for an optimized lineup.

    stats is a list of stat keys to include as columns, where each key is either
    'obp' (rendered as "OBP", 3 decimals) or 'wrc_plus' (rendered as "wRC+", 1 decimal).
    """
    display_rows = []
    for row in optimized_lineup:
        entry = {
            "Spot": f"#{row[slot_key]}",
            "Player": row['name'],
            "Bat Hand": row['bat_hand'],
            "Position": row['pos'],
        }
        for stat in stats:
            if stat == 'obp':
                entry["OBP"] = f"{row['obp']:.3f}" if row['has_stats'] else "No Stats"
            elif stat == 'wrc_plus':
                entry["wRC+"] = f"{row['wrc_plus']:.1f}" if row['has_wrc'] else "No Stats"
        display_rows.append(entry)
    return pd.DataFrame(display_rows)


def build_combined_df(optimized_lineup, slot_key, stats):
    """Combine an optimized lineup and its shift diff into a single table.

    Each player's Actual Slot and shift direction (Movement) are placed to the
    right of the optimized metric column(s). stats is a list of stat keys where
    each key is either 'obp' (rendered as "OBP", 3 decimals) or 'wrc_plus'
    (rendered as "wRC+", 1 decimal).
    """
    combined_rows = []
    for row in optimized_lineup:
        actual = row['actual_slot']
        opt = row[slot_key]

        diff = actual - opt
        if diff == 0:
            direction, change_str = "➡️", "Unchanged"
        elif diff > 0:
            direction, change_str = "📈", f"+{diff}"
        else:
            direction, change_str = "📉", f"{diff}"

        entry = {
            "Spot": f"#{opt}",
            "Player": row['name'],
            "Bat Hand": row['bat_hand'],
            "Position": row['pos'],
        }
        for stat in stats:
            if stat == 'obp':
                entry["OBP"] = f"{row['obp']:.3f}" if row['has_stats'] else "No Stats"
            elif stat == 'wrc_plus':
                entry["wRC+"] = f"{row['wrc_plus']:.1f}" if row['has_wrc'] else "No Stats"
        entry["Actual Slot"] = f"#{actual}"
        entry["Movement"] = f"{direction} {change_str}"
        combined_rows.append(entry)

    return pd.DataFrame(combined_rows)


def render_optimized_tab(optimized_lineup, slot_key, title, stats, file_prefix):
    """Render one optimized-lineup tab with the table and its shift diff combined."""
    combined_df = build_combined_df(optimized_lineup, slot_key, stats)
    st.markdown(f"## {title}")
    st.dataframe(
        combined_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Movement": st.column_config.TextColumn("Shift Direction", width="small"),
        }
    )

    csv_data = convert_df_to_csv(combined_df)
    st.download_button(
        label="📥 Download Lineup Comparison (CSV)",
        data=csv_data,
        file_name=f"{file_prefix}_diff.csv",
        mime="text/csv",
    )


def main():
    st.markdown("""
        <div style='background-color:#005A9C;padding:15px;border-radius:10px;margin-bottom:20px'>
            <h1 style='color:white;text-align:center;margin:0;'>⚾ MLB Batting Lineup Optimizer</h1>
            <p style='color:#A5C9EB;text-align:center;font-size:1.1rem;margin:5px 0 0 0;'>
                Comparing actual starting lineups against Sabermetric OBP-optimized batting orders.
            </p>
        </div>
    """, unsafe_allow_html=True)

    st.sidebar.header("Interactive Controls")

    season_options = [2026, 2025, 2024, 2023]
    selected_season = st.sidebar.selectbox("Select Stats Season", season_options, index=0)

    # MLB Team Selector (defaults to the Los Angeles Dodgers), resolved via name + id.
    teams_raw = get_mlb_teams()
    teams_raw.sort(key=lambda t: t["name"])
    team_names = [t["name"] for t in teams_raw]
    team_id_map = {t["name"]: t["id"] for t in teams_raw}

    default_team = "Los Angeles Dodgers"
    default_index = team_names.index(default_team) if default_team in team_names else 0
    selected_team = st.sidebar.selectbox("Select MLB Team", team_names, index=default_index)
    selected_team_id = team_id_map[selected_team]

    with st.spinner(f"Preparing application data for {selected_team}..."):
        lineup_rows, game_summary = get_latest_lineup(selected_team_id)

        # Build the full active roster's batting stats, keyed by player ID.
        active_roster = get_active_roster(selected_team_id)
        lineup_ids = [r['id'] for r in lineup_rows]

        # Union of lineup players + all active non-pitchers on the roster.
        all_ids = set(lineup_ids)
        for pid, info in active_roster.items():
            if info['pos'] not in ("P", "SP", "RP"):
                all_ids.add(pid)

        team_stats = get_team_batting_stats(selected_team_id, selected_season, sorted(all_ids))

    # Augment each lineup row with its wRC+ (from the people endpoint, keyed by ID).
    wrc_map = {pid: info.get('wrc_plus') for pid, info in team_stats.items()}
    for row in lineup_rows:
        row['wrc_plus'] = wrc_map.get(row['id'])

    if not lineup_rows:
        st.warning(f"⚠️ Could not automatically fetch starting lineup: {game_summary or 'No game data available.'}")
        st.info("Ensure that there are active games played within the last 14 days or that MLB StatsAPI service is available.")
        return

    st.header(f"⚾ {selected_team} Batting Lineup")
    st.success(f"📌 **Latest Starting Lineup Loaded:** {game_summary}")

    # Build all four optimized orders: OBP, wRC+, Hybrid, and The Book (Tango).
    (obp_optimized_lineup, wrc_optimized_lineup,
     hybrid_lineup, tango_lineup) = prepare_optimized_lineups(lineup_rows)

    # Show the actual batting lineup once, as the shared reference every diff compares against.
    st.markdown(f"## 📋 Actual Batting Lineup")
    st.dataframe(
        build_display_df(sorted(lineup_rows, key=lambda x: x['actual_slot']), 'actual_slot', ['obp']),
        use_container_width=True,
        hide_index=True,
    )

    tab_obp, tab_wrc, tab_hybrid, tab_tango = st.tabs(
        ["⬜ OBP Optimized", "⚾ WRC+ Optimized", "🚀 Hybrid Optimized", "📕 The Book"]
    )

    with tab_obp:
        render_optimized_tab(obp_optimized_lineup, 'opt_slot',
                             "OBP Optimized Lineup", ['obp'], "obp_optimization")
        st.markdown(
            "**What is OBP?** OBP stands for **On Base Percentage** — how often a batter "
            "reaches base safely per plate appearance. Theoretically, if you get on base, you "
            "score more runs, which is why the early-2000s Oakland Athletics built their "
            "famous Moneyball rosters around OBP.\n\n"
            "This tab sorts the lineup by OBP."
        )
    with tab_wrc:
        render_optimized_tab(wrc_optimized_lineup, 'wrc_slot',
                             "wRC+ Optimized Lineup", ['wrc_plus'], "wrc_optimization")
        st.markdown(
            "**What is wRC+?** wRC+ (**Weighted Runs Created Plus**) is one number that tells you "
            "how good a hitter is, adjusted for ballpark and league. **100 is the league average** — "
            "every point above 100 is one percent better than average. A 120 hitter creates about "
            "20% more runs than average; an 80 hitter about 20% worse.\n\n"
            "This tab sorts the lineup by wRC+. To learn more about the formula for "
            "wRC+, check out this [FanGraphs article](https://www.fangraphs.com/library/offense/wrc/)."
        )
    with tab_hybrid:
        render_optimized_tab(hybrid_lineup, 'hybrid_slot',
                             "Hybrid Optimized Lineup",
                             ['obp', 'wrc_plus'], "hybrid_optimization")
        st.markdown(
            "**Hybrid Optimized** blends OBP, wRC+, and handedness into one lineup, adapted from "
            "the heuristic in the video "
            "[*Mario Super Sluggers' Anti-Analytics Lineups*](https://www.youtube.com/watch?v=SY7hUFzVijw&list=LL&index=2&t=526s). "
            "The rules:\n\n"
            "1. Highest OBP leads off — sets the table at the top.\n"
            "2. Best wRC+ bats 2nd.\n"
            "3. Slots 3–9 are ranked by wRC+, descending.\n"
            "4. Avoid stacking same-handed hitters: if the last two batters bat from the same "
            "side, the next pick must come from the opposite hand.\n"
        )
    with tab_tango:
        render_optimized_tab(tango_lineup, 'tango_slot',
                             "The Book Lineup",
                             ['wrc_plus'], "thebook_optimization")
        st.markdown(
            "**The Book — Sherman template** follows the slot template from based on Tom Tango's "
            "*The Book: Playing the Percentages in Baseball*"
            ". Here, we use **wRC+** to rank our hitters. The rules:\n\n"
            "1. Your **three best** hitters bat in slots **#1, #2, #4**.\n"
            "2. Your **4th- and 5th-best** hitters bat in slots **#3 and #5**.\n"
            "3. Slots **#6 through #9** take the rest in descending order of quality.\n\n"
            "Handedness is not considered as part of Tango's formula."
        )


if __name__ == "__main__":
    main()