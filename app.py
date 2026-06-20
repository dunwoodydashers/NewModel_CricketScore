import streamlit as st
import json
from sqlalchemy import text

# --- 1. CONFIGURATION ---
conn = st.connection("supabase", type="sql", connect_args={"sslmode": "require"})

st.set_page_config(page_title="Pro Cricket Scorer", layout="wide")
st.title("🏏 Pro Cricket Scoring System")

# --- 2. HELPER FUNCTIONS ---
def get_teams():
    try:
        with conn.session as s:
            return [r[0] for r in s.execute(text("SELECT name FROM teams")).fetchall()]
    except: return []

def upgrade_to_pro_state(state, striker, non_striker, bowler):
    """Initializes/Upgrades state to support full professional stats."""
    if "batting" not in state:
        state = {
            "runs": 0, "wickets": 0, "balls": 0,
            "batting": {striker: {"r": 0, "b": 0, "4s": 0, "6s": 0}, non_striker: {"r": 0, "b": 0, "4s": 0, "6s": 0}},
            "bowling": {bowler: {"o": 0, "r": 0, "w": 0, "wd": 0, "nb": 0}},
            "extras": {"wd": 0, "nb": 0, "bye": 0, "lb": 0}
        }
    return state
    # Ensure batting/bowling structures exist
    if "batting" not in state:
        state["batting"] = {striker: {"runs": 0, "balls": 0}, non_striker: {"runs": 0, "balls": 0}}
        state["bowling"] = {bowler: {"runs": 0, "wickets": 0, "balls": 0}}
    return state

# --- 3. UI LAYOUT ---
menu = ["Schedule & Rosters", "Live Scoring"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Schedule & Rosters":
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Manage Teams & Players")
        t_name = st.text_input("New Team Name")
        if st.button("Add Team") and t_name.strip():
            with conn.session as s:
                s.execute(text("INSERT INTO teams (name) VALUES (:n)"), {"n": t_name.strip()})
                s.commit()
            st.rerun()
        
        teams = get_teams()
        sel_t = st.selectbox("Select Team", teams if teams else ["Add a team first"])
        p_name = st.text_input("Player Name")
        if st.button("Add Player") and p_name.strip():
            with conn.session as s:
                s.execute(text("INSERT INTO players (team_name, name) VALUES (:t, :p)"), {"t": sel_t, "p": p_name})
                s.commit()
            st.rerun()

    with c2:
        st.subheader("Schedule Match")
        ta = st.selectbox("Team A", teams)
        tb = st.selectbox("Team B", teams)
        if st.button("Schedule Match") and ta and tb:
            with conn.session as s:
                s.execute(text("INSERT INTO matches (team_a, team_b, status) VALUES (:a, :b, 'Scheduled')"), {"a": ta, "b": tb})
                s.commit()
            st.success("Match Scheduled!"); st.rerun()

elif choice == "Live Scoring":
    st.subheader("Live Match Tracker")
    with conn.session as s:
        matches = s.execute(text("SELECT * FROM matches WHERE status != 'Completed'")).mappings().all()
    
    if not matches:
        st.info("No active matches found.")
    else:
        m = st.selectbox("Select Match", matches, format_func=lambda x: f"{x['team_a']} vs {x['team_b']} ({x['status']})")
        
        # --- PHASE 1: TOSS (Scheduled) ---
        if m['status'] == 'Scheduled':
            with st.form("toss_form"):
                overs = st.number_input("Total Overs", 1, 50, 20)
                tw = st.radio("Toss Winner", [m['team_a'], m['team_b']])
                td = st.radio("Decision", ["Bat", "Bowl"])
                if st.form_submit_button("Start Match"):
                    with conn.session as s:
                        s.execute(text("UPDATE matches SET total_overs=:o, toss_winner=:tw, toss_decision=:td, status='Lineup' WHERE id=:id"), 
                                  {"o": overs, "tw": tw, "td": td, "id": m['id']})
                        s.commit()
                    st.rerun()

        # --- PHASE 2: LINEUP (Select Players) ---
        elif m['status'] == 'Lineup':
            if m['toss_decision'] == 'Bat':
                batting_team, bowling_team = m['toss_winner'], (m['team_a'] if m['toss_winner'] == m['team_b'] else m['team_b'])
            else:
                bowling_team, batting_team = m['toss_winner'], (m['team_a'] if m['toss_winner'] == m['team_b'] else m['team_b'])

            with conn.session as s:
                batting_players = s.execute(text("SELECT name FROM players WHERE team_name = :t"), {"t": batting_team}).fetchall()
                bowling_players = s.execute(text("SELECT name FROM players WHERE team_name = :t"), {"t": bowling_team}).fetchall()
            
            bat_list, bowl_list = [p[0] for p in batting_players], [p[0] for p in bowling_players]
            
            s1 = st.selectbox("Striker", bat_list)
            s2 = st.selectbox("Non-Striker", [p for p in bat_list if p != s1])
            b = st.selectbox("Bowler", bowl_list)
            
            if st.button("Start Ball-by-Ball"):
                with conn.session as s:
                    s.execute(text("""
                        UPDATE matches 
                        SET striker_id=:s1, non_striker_id=:s2, bowler_id=:b, status='Live', 
                            batting_team=:bt, bowling_team=:bowlt, score_state=:ss 
                        WHERE id=:id
                    """), {"s1": s1, "s2": s2, "b": b, "bt": batting_team, "bowlt": bowling_team, 
                           "ss": json.dumps({"runs":0, "wickets":0, "balls":0}), "id": m['id']})
                    s.commit()
                st.rerun()
        def process_ball(state, action, striker, bowler):
    # action example: {'type': 'run', 'val': 4} or {'type': 'wide', 'val': 1}
    t = action['type']
    v = action['val']
    
    if t == 'run':
        state['runs'] += v
        state['batting'][striker]['r'] += v
        state['batting'][striker]['b'] += 1
        state['bowling'][bowler]['r'] += v
        state['bowling'][bowler]['b'] += 1
        if v == 4: state['batting'][striker]['4s'] += 1
        if v == 6: state['batting'][striker]['6s'] += 1
    elif t == 'wkt':
        state['wickets'] += 1
        state['bowling'][bowler]['w'] += 1
        state['balls'] += 1
    elif t == 'wd':
        state['runs'] += v
        state['bowling'][bowler]['wd'] += 1
    # Add extra logic (bye, lb, nb) here...
    return state
        # --- PHASE 3: LIVE SCORING ---
        # --- PHASE 3: PRO SCORING INTERFACE ---
        elif m['status'] == 'Live':
            state = upgrade_to_pro_state(state, m['striker_id'], m['non_striker_id'], m['bowler_id'])
            
            # --- DASHBOARD ---
            st.metric("Score", f"{state['runs']}/{state['wickets']}", f"Overs: {state['balls'] // 6}.{state['balls'] % 6}")
            
            # --- ACTION GRID ---
            st.write("### Scoring Actions")
            cols = st.columns(6)
            actions = [1, 2, 3, 4, 5, 6]
            for i, val in enumerate(actions):
                if cols[i].button(str(val)):
                    state = process_ball(state, {'type': 'run', 'val': val}, m['striker_id'], m['bowler_id'])
                    # Save and rerun...
            
            # Extra Buttons
            cols2 = st.columns(4)
            if cols2[0].button("Wide"): ...
            if cols2[1].button("Wicket"): ...
            if cols2[2].button("Swap Strike"): 
                # Logic to swap striker/non-striker IDs in database
                ...

            # --- PRO SCORECARD ---
            st.write("### Batting Scorecard")
            import pandas as pd
            bat_df = pd.DataFrame.from_dict(state['batting'], orient='index')
            bat_df['SR'] = (bat_df['r'] / bat_df['b'] * 100).fillna(0).round(2)
            st.dataframe(bat_df)
            
            st.write("### Bowling Scorecard")
            bowl_df = pd.DataFrame.from_dict(state['bowling'], orient='index')
            bowl_df['Econ'] = (bowl_df['r'] / (bowl_df['b']/6)).fillna(0).round(2)
            st.dataframe(bowl_df)
# 4. Pro Scorecard View
            st.write("---")
            col_a, col_b = st.columns(2)
            
            with col_a:
                st.write("### Batters")
                batting_data = [
                    {"Name": name, "Runs": stats['runs'], "Balls": stats['balls']} 
                    for name, stats in state['batting'].items()
                ]
                st.table(batting_data)
                
            with col_b:
                st.write("### Bowler")
                bowling_data = [
                    {"Name": name, "Wickets": stats['wickets'], "Runs": stats['runs']} 
                    for name, stats in state['bowling'].items()
                ]
                st.table(bowling_data)
