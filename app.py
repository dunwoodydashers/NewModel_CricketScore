import streamlit as st
from datetime import datetime
import json
from sqlalchemy import text

# --- DATABASE SETUP ---
conn = st.connection("supabase", type="sql")

def init_db():
    with conn.session as s:
        # Tables remain the same
        s.execute(text('''CREATE TABLE IF NOT EXISTS teams (id SERIAL PRIMARY KEY, name TEXT UNIQUE)'''))
        s.execute(text('''CREATE TABLE IF NOT EXISTS players (id SERIAL PRIMARY KEY, team_name TEXT, name TEXT)'''))
        s.execute(text('''CREATE TABLE IF NOT EXISTS matches (id SERIAL PRIMARY KEY, team_a TEXT, team_b TEXT, date DATE, status TEXT, toss_winner TEXT, toss_decision TEXT)'''))
        s.commit()

init_db()

def run_query(query, params=None, commit=False):
    with conn.session as s:
        result = s.execute(text(query), params or {})
        if commit: s.commit(); return None
        return result.fetchall()

st.set_page_config(page_title="Pro Cricket Scorer", layout="wide")
st.title("🏏 Pro Real-Time Cricket Scoring")

# Initialize session state for scoring
if 'score' not in st.session_state:
    st.session_state.score = 0
    st.session_state.wickets = 0
    st.session_state.balls = 0

# --- NAVIGATION ---
menu = ["Schedule & Rosters", "Live Scoring", "Match History"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Schedule & Rosters":
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Teams & Players")
        t_name = st.text_input("New Team Name")
        if st.button("Add Team"):
            run_query("INSERT INTO teams (name) VALUES (:n)", {"n": t_name}, commit=True)
            st.rerun()
        
        teams = [r[0] for r in run_query("SELECT name FROM teams")]
        sel_team = st.selectbox("Select Team", teams)
        p_name = st.text_input("Player Name")
        if st.button("Add Player"):
            run_query("INSERT INTO players (team_name, name) VALUES (:t, :p)", {"t": sel_team, "p": p_name}, commit=True)
            st.rerun()
            
    with col2:
        st.subheader("Schedule Match")
        teams = [r[0] for r in run_query("SELECT name FROM teams")]
        ta = st.selectbox("Team A", teams)
        tb = st.selectbox("Team B", teams)
        m_date = st.date_input("Match Date")
        if st.button("Schedule Match"):
            run_query("INSERT INTO matches (team_a, team_b, date, status) VALUES (:a, :b, :d, 'Scheduled')", 
                      {"a": ta, "b": tb, "d": m_date}, commit=True)
            st.success("Match Scheduled!")
            st.rerun()

elif choice == "Live Scoring":
    st.header("Live Scoring Console")
    matches = run_query("SELECT id, team_a, team_b, date FROM matches WHERE status != 'Completed'")
    if not matches: st.info("No active matches found."); st.stop()
    
    match = st.selectbox("Select Match", matches, format_func=lambda x: f"{x[1]} vs {x[2]} ({x[3]})")
    m_id = match[0]
    
    # Professional Scorecard Display
    col1, col2 = st.columns([2, 1])
    with col1:
        st.metric("Total Score", f"{st.session_state.score}/{st.session_state.wickets}", f"Overs: {st.session_state.balls // 6}.{st.session_state.balls % 6}")
        
        st.subheader("Update Score")
        b1, b2, b3, b4, b5, b6 = st.columns(6)
        if b1.button("0 Run"): st.session_state.balls += 1
        if b2.button("1 Run"): st.session_state.score += 1; st.session_state.balls += 1
        if b3.button("2 Runs"): st.session_state.score += 2; st.session_state.balls += 1
        if b4.button("4 Runs"): st.session_state.score += 4; st.session_state.balls += 1
        if b5.button("6 Runs"): st.session_state.score += 6; st.session_state.balls += 1
        if b6.button("Wicket", type="primary"): st.session_state.wickets += 1; st.session_state.balls += 1
        
    with col2:
        if st.button("End Match"):
            run_query("UPDATE matches SET status='Completed' WHERE id=:id", {"id": m_id}, commit=True)
            st.session_state.score = 0
            st.session_state.wickets = 0
            st.session_state.balls = 0
            st.rerun()

elif choice == "Match History":
    history = run_query("SELECT team_a, team_b, date FROM matches WHERE status = 'Completed'")
    for h in history:
        st.write(f"✅ {h[0]} vs {h[1]} — {h[2]}")
