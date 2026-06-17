import streamlit as st
import sqlite3
from datetime import datetime
import json

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    # Create Teams table
    c.execute('''CREATE TABLE IF NOT EXISTS teams (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    name TEXT UNIQUE)''')
    # Create Matches table
    c.execute('''CREATE TABLE IF NOT EXISTS matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    team_a TEXT, team_b TEXT, date TEXT, 
                    status TEXT, report TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- HELPER FUNCTIONS ---
def run_query(query, params=(), commit=False):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute(query, params)
    if commit:
        conn.commit()
        data = None
    else:
        data = c.fetchall()
    conn.close()
    return data

# --- APP NAVIGATION ---
st.set_page_config(page_title="Bulletproof Cricket Scorer", layout="wide")
st.title("🏏 Real-Time Cricket Scoring Engine")

menu = ["Schedule & Teams", "Live Scoring", "Match History & Reports"]
choice = st.sidebar.selectbox("Navigation Menu", menu)

# ----------------------------------------------------
# PAGE 1: SCHEDULE & TEAMS
# ----------------------------------------------------
if choice == "Schedule & Teams":
    st.header("Manage Teams & Schedules")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Add New Team")
        team_name = st.text_input("Team Name")
        if st.button("Register Team"):
            if team_name:
                try:
                    run_query("INSERT INTO teams (name) VALUES (?)", (team_name,), commit=True)
                    st.success(f"Team '{team_name}' registered successfully!")
                except sqlite3.IntegrityError:
                    st.error("Team already exists!")
    
    with col2:
        st.subheader("Schedule a Match")
        teams_list = [row[0] for row in run_query("SELECT name FROM teams")]
        
        if len(teams_list) < 2:
            st.warning("Please register at least 2 teams to schedule a match.")
        else:
            team_a = st.selectbox("Team A (Batting first)", teams_list, key="ta")
            team_b = st.selectbox("Team B (Bowling first)", teams_list, key="tb")
            match_date = st.date_input("Match Date", datetime.now())
            
            if team_a == team_b:
                st.error("A team cannot play against itself.")
            elif st.button("Schedule Match"):
                run_query("INSERT INTO matches (team_a, team_b, date, status) VALUES (?, ?, ?, ?)",
                          (team_a, team_b, str(match_date), "Scheduled"), commit=True)
                st.success(f"Scheduled: {team_a} vs {team_b} on {match_date}")

# ----------------------------------------------------
# PAGE 2: LIVE SCORING
# ----------------------------------------------------
elif choice == "Live Scoring":
    st.header("Live Scoring Console")
    
    # Select from active or scheduled matches
    scheduled_matches = run_query("SELECT id, team_a, team_b, date FROM matches WHERE status != 'Completed'")
    
    if not scheduled_matches:
        st.info("No active or scheduled matches found. Go to 'Schedule & Teams' to start.")
    else:
        match_options = {f"{row[1]} vs {row[2]} ({row[3]})": row[0] for row in scheduled_matches}
        selected_match_str = st.selectbox("Select Match to Score", list(match_options.keys()))
        match_id = match_options[selected_match_str]
        
        # Fetch match details
        match_data = run_query("SELECT team_a, team_b FROM matches WHERE id = ?", (match_id,))[0]
        team_a, team_b = match_data[0], match_data[1]
        
        # Initialize Scoring Session State if not present
        if 'runs' not in st.session_state or st.session_state.get('current_match_id') != match_id:
            st.session_state.current_match_id = match_id
            st.session_state.runs = 0
            st.session_state.wickets = 0
            st.session_state.balls = 0
            st.session_state.striker = "Batsman 1"
            st.session_state.non_striker = "Batsman 2"
            st.session_state.ball_history = []

        # --- SCOREBOARD DISPLAY ---
        overs = f"{st.session_state.balls // 6}.{st.session_state.balls % 6}"
        
        st.metric(label=f"{team_a} Innings", value=f"{st.session_state.runs} / {st.session_state.wickets}", delta=f"Overs: {overs}")
        
        st.write(f"**🏏 On Strike:** {st.session_state.striker} | **👤 Non-Strike:** {st.session_state.non_striker}")
        
        # --- SCORING BUTTONS ---
        st.subheader("Update Score")
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        
        def add_ball(runs_scored, is_extra=False, wicket=False):
            if not is_extra:
                st.session_state.balls += 1
            st.session_state.runs += runs_scored
            if wicket:
                st.session_state.wickets += 1
            
            # Strike rotation for single/three runs
            if runs_scored in [1, 3]:
                st.session_state.striker, st.session_state.non_striker = st.session_state.non_striker, st.session_state.striker
                
            # Over completed rotation
            if st.session_state.balls > 0 and st.session_state.balls % 6 == 0 and not is_extra:
                st.session_state.striker, st.session_state.non_striker = st.session_state.non_striker, st.session_state.striker
                st.toast("End of over! Strike rotated.")

        if c1.button("0 Run"): add_ball(0)
        if c2.button("1 Run"): add_ball(1)
        if c3.button("2 Runs"): add_ball(2)
        if c4.button("4 Runs"): add_ball(4)
        if c5.button("6 Runs"): add_ball(6)
        if c6.button("🔴 Wicket", type="primary"): add_ball(0, wicket=True)
        
        st.write("---")
        # Save Report
        if st.button("End Match & Save Report", use_container_width=True):
            report_data = {
                "total_runs": st.session_state.runs,
                "total_wickets": st.session_state.wickets,
                "overs_played": overs,
                "date_completed": str(datetime.now().strftime("%Y-%m-%d %H:%M"))
            }
            report_json = json.dumps(report_data)
            
            run_query("UPDATE matches SET status = 'Completed', report = ? WHERE id = ?", 
                      (report_json, match_id), commit=True)
            st.success("Match finalized! Report compiled and archived.")

# ----------------------------------------------------
# PAGE 3: MATCH HISTORY & REPORTS
# ----------------------------------------------------
elif choice == "Match History & Reports":
    st.header("Archived Match Reports")
    
    completed_matches = run_query("SELECT team_a, team_b, date, report FROM matches WHERE status = 'Completed'")
    
    if not completed_matches:
        st.info("No historical records found yet. Complete a match in the Scoring console.")
    else:
        for row in completed_matches:
            t_a, t_b, m_date, raw_report = row[0], row[1], row[2], row[3]
            report = json.loads(raw_report)
            
            with st.expander(f"📋 {t_a} vs {t_b} — Played on {m_date}"):
                st.subheader("Match Summary")
                st.write(f"**Date Logged:** {report['date_completed']}")
                st.write(f"**Final Score:** {t_a} scored **{report['total_runs']}/{report['total_wickets']}** in **{report['overs_played']}** overs.")
