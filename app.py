import streamlit as st
from datetime import datetime
import json
from sqlalchemy import text

# --- 1. CLOUD DATABASE SETUP ---
# This natively connects to the secret you added in the Streamlit dashboard
conn = st.connection("supabase", type="sql")

def init_db():
    with conn.session as s:
        # Postgres uses SERIAL instead of AUTOINCREMENT
        s.execute(text('''CREATE TABLE IF NOT EXISTS teams (id SERIAL PRIMARY KEY, name TEXT UNIQUE)'''))
        s.execute(text('''CREATE TABLE IF NOT EXISTS players (id SERIAL PRIMARY KEY, team_name TEXT, name TEXT)'''))
        s.execute(text('''CREATE TABLE IF NOT EXISTS matches (id SERIAL PRIMARY KEY, team_a TEXT, team_b TEXT, date TEXT, status TEXT, report TEXT, toss_winner TEXT, toss_decision TEXT)'''))
        s.commit()

init_db()

# --- 2. HELPER FUNCTIONS ---
def run_query(query, params=None, commit=False):
    if params is None:
        params = {}
    with conn.session as s:
        result = s.execute(text(query), params)
        if commit:
            s.commit()
            return None
        return result.fetchall()

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
                    # Notice the change from ? to :name for Postgres
                    run_query("INSERT INTO teams (name) VALUES (:name)", {"name": team_name}, commit=True)
                    st.success(f"Team '{team_name}' registered successfully!")
                except Exception:
                    st.error("Team already exists or database error!")
                    
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
                run_query("INSERT INTO matches (team_a, team_b, date, status) VALUES (:ta, :tb, :d, :s)",
                          {"ta": team_a, "tb": team_b, "d": str(match_date), "s": "Scheduled"}, commit=True)
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
                    run_query("INSERT INTO players (team_name, name) VALUES (:tn, :pn)", 
                              {"tn": selected_team, "pn": player_name}, commit=True)
                    st.success(f"Added {player_name} to {selected_team}!")
        with col2:
            st.subheader(f"Current Squad: {selected_team}")
            squad = run_query("SELECT name FROM players WHERE team_name = :tn", {"tn": selected_team})
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
        match_options = {f"{row[1]} vs {row[2]} ({row[3]})": row for row in scheduled_matches}
        selected_match_str = st.selectbox("Select Match to Score", list(match_options.keys()))
        match_data = match_options[selected_match_str]
        
        match_id, team_a, team_b, m_date, toss_winner, toss_decision = match_data
        
        if not toss_winner:
            st.markdown("---")
            st.subheader("🪙 Match Setup: The Toss")
            col1, col2 = st.columns(2)
            with col1:
                winner = st.radio("Who won the toss?", [team_a, team_b])
            with col2:
                decision = st.radio("Elected to?", ["Bat", "Bowl"])
            
            if st.button("Confirm Toss & Proceed", type="primary"):
                run_query("UPDATE matches SET toss_winner=:tw, toss_decision=:td, status='Live' WHERE id=:id", 
                          {"tw": winner, "td": decision, "id": match_id}, commit=True)
                st.rerun()
                
        else:
            if (toss_winner == team_a and toss_decision == "Bat") or (toss_winner == team_b and toss_decision == "Bowl"):
                batting_team, bowling_team = team_a, team_b
            else:
                batting_team, bowling_team = team_b, team_a
                
            batting_squad = [row[0] for row in run_query("SELECT name FROM players WHERE team_name = :tn", {"tn": batting_team})]
            bowling_squad = [row[0] for row in run_query("SELECT name FROM players WHERE team_name = :tn", {"tn": bowling_team})]
            
            if len(batting_squad) < 2 or len(bowling_squad) < 1:
                st.error(f"⚠️ Missing players! {batting_team} needs at least 2 players, and {bowling_team} needs at least 1. Go to Roster Management.")
            else:
                if 'innings_started' not in st.session_state or st.session_state.get('current_match_id') != match_id:
                    st.markdown("---")
                    st.subheader("🏏 Select Opening Players")
                    st.write(f"**Toss:** {toss_winner} won the toss and elected to {toss_decision.lower()} first.")
                    
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        striker = st.selectbox("Striker", batting_squad)
                    with c2:
                        non_striker = st.selectbox("Non-Striker", batting_squad, index=1 if len(batting_squad)>1 else 0)
                    with c3:
                        bowler = st.selectbox("Opening Bowler", bowling_squad)
                        
                    if st.button("Start Innings", type="primary", use_container_width=True):
                        if striker == non_striker:
                            st.error("Striker and Non-Striker cannot be the same person!")
                        else:
                            st.session_state.current_match_id = match_id
                            st.session_state.innings_started = True
                            st.session_state.runs = 0
                            st.session_state.wickets = 0
                            st.session_state.balls = 0
                            st.session_state.striker = striker
                            st.session_state.non_striker = non_striker
                            st.session_state.bowler = bowler
                            st.rerun()
                else:
                    st.markdown("---")
                    overs = f"{st.session_state.balls // 6}.{st.session_state.balls % 6}"
                    st.metric(label=f"{batting_team} Innings", value=f"{st.session_state.runs} / {st.session_state.wickets}", delta=f"Overs: {overs}")
                    st.info(f"🏏 **Striker:** {st.session_state.striker}  |  👤 **Non-Striker:** {st.session_state.non_striker}  |  ⚾ **Bowler:** {st.session_state.bowler}")
                    
                    with st.expander("🔄 Change Batsman or Bowler"):
                        col1, col2 = st.columns(2)
                        with col1:
                            new_striker = st.selectbox("New Striker", batting_squad, index=batting_squad.index(st.session_state.striker))
                            new_non_striker = st.selectbox("New Non-Striker", batting_squad, index=batting_squad.index(st.session_state.non_striker))
                            if st.button("Update Batsmen"):
                                st.session_state.striker = new_striker
                                st.session_state.non_striker = new_non_striker
                                st.rerun()
                        with col2:
                            new_bowler = st.selectbox("New Bowler", bowling_squad, index=bowling_squad.index(st.session_state.bowler))
                            if st.button("Update Bowler"):
                                st.session_state.bowler = new_bowler
                                st.rerun()

                    st.subheader("Score this ball")
                    c1, c2, c3, c4, c5, c6 = st.columns(6)
                    
                    def add_ball(runs_scored, is_extra=False, wicket=False):
                        if not is_extra:
                            st.session_state.balls += 1
                        st.session_state.runs += runs_scored
                        if wicket:
                            st.session_state.wickets += 1
                        
                        if runs_scored in [1, 3]:
                            st.session_state.striker, st.session_state.non_striker = st.session_state.non_striker, st.session_state.striker
                            
                        if st.session_state.balls > 0 and st.session_state.balls % 6 == 0 and not is_extra:
                            st.session_state.striker, st.session_state.non_striker = st.session_state.non_striker, st.session_state.striker
                            st.toast("End of over! Please change the bowler using the dropdown above.", icon="🔄")

                    if c1.button("0 Run"): add_ball(0)
                    if c2.button("1 Run"): add_ball(1)
                    if c3.button("2 Runs"): add_ball(2)
                    if c4.button("4 Runs"): add_ball(4)
                    if c5.button("6 Runs"): add_ball(6)
                    if c6.button("🔴 Wicket", type="primary"): add_ball(0, wicket=True)
                    
                    st.write("---")
                    
                    if st.button("End Match & Save Report"):
                        report_data = {
                            "toss": f"{toss_winner} elected to {toss_decision.lower()}",
                            "total_runs": st.session_state.runs,
                            "total_wickets": st.session_state.wickets,
                            "overs_played": overs,
                            "date_completed": str(datetime.now().strftime("%Y-%m-%d %H:%M"))
                        }
                        report_json = json.dumps(report_data)
                        run_query("UPDATE matches SET status = 'Completed', report = :r WHERE id = :id", 
                                  {"r": report_json, "id": match_id}, commit=True)
                        
                        keys_to_clear = ['innings_started', 'current_match_id', 'runs', 'wickets', 'balls', 'striker', 'non_striker', 'bowler']
                        for key in keys_to_clear:
                            if key in st.session_state:
                                del st.session_state[key]
                                
                        st.success("Match finalized! Report compiled and archived.")
                        st.rerun()

# ----------------------------------------------------
# PAGE 4: MATCH HISTORY
# ----------------------------------------------------
elif choice == "Match History":
    st.header("Archived Match Reports")
    completed_matches = run_query("SELECT team_a, team_b, date, report FROM matches WHERE status = 'Completed'")
    
    if not completed_matches:
        st.info("No historical records found yet.")
    else:
        for row in completed_matches:
            t_a, t_b, m_date, raw_report = row[0], row[1], row[2], row[3]
            report = json.loads(raw_report)
            with st.expander(f"📋 {t_a} vs {t_b} — {m_date}"):
                st.write(f"**Toss:** {report.get('toss', 'Data unavailable')}")
                st.write(f"**Final Score:** **{report['total_runs']}/{report['total_wickets']}** in **{report['overs_played']}** overs.")
