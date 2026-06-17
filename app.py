import streamlit as st
from datetime import datetime
from sqlalchemy import text

# --- DATABASE SETUP ---
conn = st.connection("supabase", type="sql")

def init_db():
    with conn.session as s:
        # Added date column back to the matches table
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
        match_date = st.date_input("Match Date") # Restored Date Picker
        if st.button("Schedule Match"):
            run_query("INSERT INTO matches (team_a, team_b, date, status) VALUES (:a, :b, :d, 'Scheduled')", 
                      {"a": ta, "b": tb, "d": match_date}, commit=True)
            st.success(f"Match scheduled for {match_date}!")
            st.rerun()

# --- PAGE 2: LIVE SCORING ---
elif choice == "Live Scoring":
    matches = run_query("SELECT id, team_a, team_b, date FROM matches WHERE status != 'Completed'")
    if not matches: st.info("No active matches found."); st.stop()
    
    match = st.selectbox("Select Match", matches, format_func=lambda x: f"{x[1]} vs {x[2]} ({x[3]})")
    m_id = match[0]
    
    st.write(f"Scoring: {match[1]} vs {match[2]}")
    if st.button("End Match"):
        run_query("UPDATE matches SET status='Completed' WHERE id=:id", {"id": m_id}, commit=True)
        st.rerun()

# --- PAGE 3: HISTORY ---
elif choice == "Match History":
    history = run_query("SELECT team_a, team_b, date FROM matches WHERE status = 'Completed'")
    for h in history:
        st.write(f"✅ {h[0]} vs {h[1]} on {h[2]}")
