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
    """Upgrades state to support Extras and full history."""
    if "extras" not in state:
        state.update({
            "extras": {"wides": 0, "noballs": 0, "byes": 0, "legbyes": 0},
            "last_balls": []
        })
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

        # --- PHASE 3: LIVE SCORING ---
        # --- PHASE 3: PRO SCORING INTERFACE ---
        elif m['status'] == 'Live':
            # 1. Load State
            score_val = m['score_state']
            state = json.loads(score_val) if isinstance(score_val, str) else score_val
            state = upgrade_to_pro_state(state, m['striker_id'], m['non_striker_id'], m['bowler_id'])

            # 2. Scoreboard Header
            st.metric("Total Score", f"{state['runs']}/{state['wickets']}", f"Overs: {state['balls'] // 6}.{state['balls'] % 6}")
            
            # 3. Action Grid (The "Scoresheet" Buttons)
            st.write("### Scoring Actions")
            col1, col2, col3, col4 = st.columns(4)
            
            with conn.session as s:
                # Standard Runs
                if col1.button("0 Run"): 
                    state['balls'] += 1; state['bowling'][m['bowler_id']]['balls'] += 1
                    s.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), {"s": json.dumps(state), "id": m['id']}); s.commit(); st.rerun()
                
                if col2.button("1 Run"):
                    state['runs'] += 1; state['balls'] += 1; state['batting'][m['striker_id']]['runs'] += 1
                    state['batting'][m['striker_id']]['balls'] += 1; state['bowling'][m['bowler_id']]['runs'] += 1
                    s.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), {"s": json.dumps(state), "id": m['id']}); s.commit(); st.rerun()

                # Extras Section
                if col3.button("Wide"):
                    state['runs'] += 1; state['extras']['wides'] += 1
                    s.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), {"s": json.dumps(state), "id": m['id']}); s.commit(); st.rerun()

                if col4.button("Wicket", type="primary"):
                    state['wickets'] += 1; state['balls'] += 1
                    state['bowling'][m['bowler_id']]['wickets'] += 1
                    s.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), {"s": json.dumps(state), "id": m['id']}); s.commit(); st.rerun()
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
