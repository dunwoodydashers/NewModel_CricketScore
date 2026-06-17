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
        s.execute(text('''CREATE TABLE IF NOT EXISTS matches (id SERIAL PRIMARY KEY, team_a TEXT, team_b TEXT, date TEXT, status TEXT, toss_winner TEXT, toss_decision TEXT)'''))
        s.commit()

init_db()

def run_query(query, params=None, commit=False):
    with conn.session as s:
        result = s.execute(text(query), params or {})
        if commit: s.commit(); return None
        return result.fetchall()

st.set_page_config(page_title="Pro Cricket Scorer", layout="wide")
st.title("🏏 Pro Real-Time Cricket Scoring")

menu = ["Schedule & Rosters", "Live Scoring", "Match History"]
choice = st.sidebar.selectbox("Menu", menu)

# --- PAGE 1: SCHEDULE & ROSTERS ---
if choice == "Schedule & Rosters":
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Teams & Players")
        t_name = st.text_input("New Team Name")
        if st.button("Add Team"):
            run_query("INSERT INTO teams (name) VALUES (:n)", {"n": t_name}, commit=True)
            st.rerun()
        
        teams = [r[0] for r in run_query("SELECT name FROM teams")]
        sel_team = st.selectbox("Select Team for Roster", teams)
        p_name = st.text_input("Player Name")
        if st.button("Add Player"):
            run_query("INSERT INTO players (team_name, name) VALUES (:t, :p)", {"t": sel_team, "p": p_name}, commit=True)
            st.rerun()
            
    with col2:
        st.subheader("Schedule Match")
        teams = [r[0] for r in run_query("SELECT name FROM teams")]
        ta = st.selectbox("Team A", teams)
        tb = st.selectbox("Team B", teams)
        if st.button("Schedule Match"):
            run_query("INSERT INTO matches (team_a, team_b, status) VALUES (:a, :b, 'Scheduled')", {"a": ta, "b": tb}, commit=True)
            st.success("Match Scheduled!")

# --- PAGE 2: LIVE SCORING ---
elif choice == "Live Scoring":
    matches = run_query("SELECT id, team_a, team_b, toss_winner FROM matches WHERE status != 'Completed'")
    if not matches: st.info("No active matches found."); st.stop()
    
    match = st.selectbox("Select Match", matches, format_func=lambda x: f"{x[1]} vs {x[2]}")
    m_id = match[0]
    
    if not match[3]: # No toss yet
        st.subheader("The Toss")
        winner = st.radio("Winner", [match[1], match[2]])
        decision = st.radio("Decision", ["Bat", "Bowl"])
        if st.button("Confirm Toss"):
            run_query("UPDATE matches SET toss_winner=:tw, toss_decision=:td, status='Live' WHERE id=:id", 
                      {"tw": winner, "td": decision, "id": m_id}, commit=True)
            st.rerun()
    else:
        st.success(f"Match Active: {match[1]} vs {match[2]}")
        # Scoring logic here...
        if st.button("End Match"):
            run_query("UPDATE matches SET status='Completed' WHERE id=:id", {"id": m_id}, commit=True)
            st.rerun()

# --- PAGE 3: HISTORY ---
elif choice == "Match History":
    history = run_query("SELECT team_a, team_b FROM matches WHERE status = 'Completed'")
    for h in history:
        st.write(f"✅ {h[0]} vs {h[1]}")
