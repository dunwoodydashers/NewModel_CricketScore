import streamlit as st
import json
import pandas as pd
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
    if "batting" not in state:
        state = {
            "runs": state.get("runs", 0),
            "wickets": state.get("wickets", 0),
            "balls": state.get("balls", 0),
            "batting": {
                striker: {"r": 0, "b": 0, "4s": 0, "6s": 0},
                non_striker: {"r": 0, "b": 0, "4s": 0, "6s": 0}
            },
            "bowling": {bowler: {"r": 0, "b": 0, "w": 0, "wd": 0, "nb": 0}},
            "extras": {"wd": 0, "nb": 0, "bye": 0, "lb": 0}
        }
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
    # ... (Live Scoring logic remains the same as provided previously)
    with conn.session as s:
        matches = s.execute(text("SELECT * FROM matches WHERE status != 'Completed'")).mappings().all()
    
    if not matches:
        st.info("No active matches found.")
    else:
        m = st.selectbox("Select Match", matches, format_func=lambda x: f"{x['team_a']} vs {x['team_b']} ({x['status']})")
        
        # --- PHASE 1: TOSS ---
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

        # --- PHASE 2: LINEUP ---
        elif m['status'] == 'Lineup':
            bat_team = m['toss_winner'] if m['toss_decision'] == 'Bat' else (m['team_a'] if m['toss_winner'] == m['team_b'] else m['team_b'])
            bowl_team = m['team_a'] if bat_team == m['team_b'] else m['team_b']
            
            with conn.session as s:
                bat_list = [p[0] for p in s.execute(text("SELECT name FROM players WHERE team_name = :t"), {"t": bat_team}).fetchall()]
                bowl_list = [p[0] for p in s.execute(text("SELECT name FROM players WHERE team_name = :t"), {"t": bowl_team}).fetchall()]
            
            s1 = st.selectbox("Striker", bat_list)
            s2 = st.selectbox("Non-Striker", [p for p in bat_list if p != s1])
            b = st.selectbox("Bowler", bowl_list)
            
            if st.button("Start Ball-by-Ball"):
                with conn.session as s:
                    s.execute(text("UPDATE matches SET striker_id=:s1, non_striker_id=:s2, bowler_id=:b, status='Live', score_state=:ss WHERE id=:id"), 
                              {"s1": s1, "s2": s2, "b": b, "ss": json.dumps({"runs":0, "wickets":0, "balls":0}), "id": m['id']})
                    s.commit()
                st.rerun()

        # --- PHASE 3: LIVE SCORING ---
        elif m['status'] == 'Live':
            state = json.loads(m['score_state']) if isinstance(m['score_state'], str) else m['score_state']
            state = upgrade_to_pro_state(state, m['striker_id'], m['non_striker_id'], m['bowler_id'])
            
            st.metric("Total Score", f"{state['runs']}/{state['wickets']}")
            
            # Action Grid
            cols = st.columns(6)
            for i in range(1, 7):
                if cols[i-1].button(str(i)):
                    # Logic here...
                    state['runs'] += i; state['balls'] += 1
                    with conn.session as s:
                        s.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), {"s": json.dumps(state), "id": m['id']}); s.commit(); st.rerun()
