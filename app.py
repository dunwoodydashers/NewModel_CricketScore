import streamlit as st
import sqlite3
from datetime import datetime
import json

# --- 1. DATABASE SETUP & UPGRADE ---
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    # Create Tables if they don't exist
    c.execute('''CREATE TABLE IF NOT EXISTS teams (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS players (id INTEGER PRIMARY KEY AUTOINCREMENT, team_name TEXT, name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS matches (id INTEGER PRIMARY KEY AUTOINCREMENT, team_a TEXT, team_b TEXT, date TEXT, status TEXT, report TEXT)''')
    conn.commit()
    conn.close()

def upgrade_db():
    # Safely adds new columns for the Toss without deleting existing matches
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE matches ADD COLUMN toss_winner TEXT")
        c.execute("ALTER TABLE matches ADD COLUMN toss_decision TEXT")
        conn.commit()
    except Exception:
        pass # Columns already exist, move on
    conn.close()

init_db()
upgrade_db()

# --- 2. HELPER FUNCTIONS ---
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

# --- 3. APP NAVIGATION ---
st.set_page_config(page_title="Pro Cricket Scorer", layout="wide")
st.title("🏏 Pro Real-Time Cricket Scoring")

menu = ["Schedule & Teams", "Roster Management", "Live Scoring", "Match History"]
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
            team_a = st.selectbox("Team A", teams_list, key="ta")
            team_b = st.selectbox("Team B", teams_list, key="tb")
            match_date = st.date_input("Match Date", datetime.now())
            if team_a == team_b:
                st.error("A team cannot play against itself.")
            elif st.button("Schedule Match"):
                run_query("INSERT INTO matches (team_a, team_b, date, status) VALUES (?, ?, ?, ?)",
                          (team_a, team_b, str(match_date), "Scheduled"), commit=True)
                st.success(f"Scheduled: {team_a} vs {team_b}")

# ----------------------------------------------------
# PAGE 2: ROSTER MANAGEMENT
# ----------------------------------------------------
elif choice == "Roster Management":
    st.header("Manage Team Squads")
    teams_list = [row[0] for row in run_query("SELECT name FROM teams")]
    
    if not teams_list:
        st.info("No teams available. Go to 'Schedule & Teams' to create one.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Add Player to Squad")
            selected_team = st.selectbox("Select Team", teams_list)
            player_name = st.text_input("Player Name")
            if st.button("Add Player"):
                if player_name:
                    run_query("INSERT INTO players (team_name, name) VALUES (?, ?)", (selected_team, player_name), commit=True)
                    st.success(f"Added {player_name} to {selected_team}!")
        with col2:
            st.subheader(f"Current Squad: {selected_team}")
            squad = run_query("SELECT name FROM players WHERE team_name = ?", (selected_team,))
            if squad:
                for idx, player in enumerate(squad):
                    st.write(f"{idx + 1}. {player[0]}")
            else:
                st.write("No players added yet.")

# ----------------------------------------------------
# PAGE 3: LIVE SCORING
# ----------------------------------------------------
elif choice == "Live Scoring":
    st.header("Live Scoring Console")
    
    scheduled_matches = run_query("SELECT id, team_a, team_b, date, toss_winner, toss_decision FROM matches WHERE status != 'Completed'")
    
    if not scheduled_matches:
        st.info("No active or scheduled matches found.")
    else:
        # Match Selection Dropdown
        match_options = {f"{row[1]} vs {row[2]} ({row[3]})": row for row in scheduled_matches}
        selected_match_str = st.selectbox("Select Match to Score", list(match_options.keys()))
        match_data = match_options[selected_match_str]
        
        match_id, team_a, team_b, m_date, toss_winner, toss_decision = match_data
        
        # ==========================================
        # STEP 1: THE TOSS
        # ==========================================
        if not toss_winner:
            st.markdown("---")
            st.subheader("🪙 Match Setup: The Toss")
            col1, col2 = st.columns(2)
            with col1:
                winner = st.radio("Who won the toss?", [team_a, team_b])
            with col2:
                decision = st.radio("Elected to?", ["Bat", "Bowl"])
            
            if st.button("Confirm Toss & Proceed", type="primary"):
                run_query("UPDATE matches SET toss_winner=?, toss_decision=?, status='Live' WHERE id=?", 
                          (winner, decision, match_id), commit=True)
                st.rerun()
                
        else:
            # Determine Batting and Bowling Teams based on Toss
            if (toss_winner == team_a and toss_decision == "Bat") or (toss_winner == team_b and toss_decision == "Bowl"):
                batting_team, bowling_team = team_a, team_b
            else:
                batting_team, bowling_team = team_b, team_a
                
            batting_squad = [row[0] for row in run_query("SELECT name FROM players WHERE team_name = ?", (batting_team,))]
            bowling_squad = [row[0] for row in run_query("SELECT name FROM players WHERE team_name = ?", (bowling_team,))]
            
            if len(batting_squad) < 2 or len(bowling_squad) < 1:
                st.error(f"⚠️ Missing players! {batting_team} needs at least 2 players, and {bowling_team} needs at least 1. Go to Roster Management.")
            else:
                
                # ==========================================
