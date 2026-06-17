import streamlit as st
from datetime import datetime
import json
from sqlalchemy import text

# --- DATABASE SETUP ---
conn = st.connection("supabase", type="sql")

def init_db():
    with conn.session as s:
        s.execute(text('''CREATE TABLE IF NOT EXISTS teams (id SERIAL PRIMARY KEY, name TEXT UNIQUE)'''))
        s.execute(text('''CREATE TABLE IF NOT EXISTS players (id SERIAL PRIMARY KEY, team_name TEXT, name TEXT)'''))
        s.execute(text('''CREATE TABLE IF NOT EXISTS matches (id SERIAL PRIMARY KEY, team_a TEXT, team_b TEXT, date TEXT, status TEXT, report JSONB, toss_winner TEXT, toss_decision TEXT)'''))
        s.commit()

init_db()

def run_query(query, params=None, commit=False):
    with conn.session as s:
        result = s.execute(text(query), params or {})
        if commit: s.commit(); return None
        return result.fetchall()

st.set_page_config(page_title="Pro Cricket Scorer", layout="wide")
st.title("🏏 Pro Real-Time Cricket Scoring")

# --- CORE LOGIC ---
def get_match_state(match_id):
    if 'match_data' not in st.session_state or st.session_state.match_id != match_id:
        st.session_state.match_id = match_id
        st.session_state.runs = 0
        st.session_state.wickets = 0
        st.session_state.balls = 0
        st.session_state.extras = 0
        st.session_state.history = []
    return st.session_state

# --- NAVIGATION ---
menu = ["Teams & Squads", "Live Scoring", "Match History"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Teams & Squads":
    st.header("Register Teams & Players")
    t_name = st.text_input("New Team Name")
    if st.button("Add Team"):
        run_query("INSERT INTO teams (name) VALUES (:n)", {"n": t_name}, commit=True)
    
    teams = [r[0] for r in run_query("SELECT name FROM teams")]
    sel_team = st.selectbox("Select Team to add player", teams)
    p_name = st.text_input("Player Name")
    if st.button("Add Player"):
        run_query("INSERT INTO players (team_name, name) VALUES (:t, :p)", {"t": sel_team, "p": p_name}, commit=True)

elif choice == "Live Scoring":
    # 1. Match Selection
    matches = run_query("SELECT id, team_a, team_b, toss_winner FROM matches WHERE status != 'Completed'")
    if not matches: st.info("No active matches."); st.stop()
    
    match = st.selectbox("Select Match", matches, format_func=lambda x: f"{x[1]} vs {x[2]}")
    m_id = match[0]
    
    # 2. If no toss, do toss
    if not match[3]:
        st.subheader("The Toss")
        winner = st.radio("Winner", [match[1], match[2]])
        decision = st.radio("Decision", ["Bat", "Bowl"])
        if st.button("Start Match"):
            run_query("UPDATE matches SET toss_winner=:tw, toss_decision=:td, status='Live' WHERE id=:id", 
                      {"tw": winner, "td": decision, "id": m_id}, commit=True)
            st.rerun()
    else:
        # 3. Game Loop
        state = get_match_state(m_id)
        
        # Scoring Console
        col1, col2 = st.columns([2, 1])
        with col1:
            st.metric(f"Score", f"{state.runs}/{state.wickets}", f"Overs: {state.balls // 6}.{state.balls % 6}")
            
            # Action Buttons
            row = st.columns(6)
            if row[0].button("0"): state.runs += 0; state.balls += 1
            if row[1].button("1"): state.runs += 1; state.balls += 1
            if row[2].button("4"): state.runs += 4; state.balls += 1
            if row[3].button("6"): state.runs += 6; state.balls += 1
            if row[4].button("Wide"): state.runs += 1; state.extras += 1
            if row[5].button("Wicket", type="primary"): 
                state.wickets += 1; state.balls += 1
                st.warning("Wicket fell!")
        
        with col2:
            st.subheader("Game Control")
            if st.button("End Match"):
                run_query("UPDATE matches SET status='Completed' WHERE id=:id", {"id": m_id}, commit=True)
                st.success("Match Saved!")

elif choice == "Match History":
    history = run_query("SELECT team_a, team_b, report FROM matches WHERE status = 'Completed'")
    for h in history:
        st.write(f"Match: {h[0]} vs {h[1]} | Result: {h[2]}")
