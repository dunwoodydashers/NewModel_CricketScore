import streamlit as st
import json
from sqlalchemy import text

# --- DATABASE SETUP ---
# Connection is initialized once at the top. 
# We rely on the Supabase SQL Editor having already created the tables.
conn = st.connection("supabase", type="sql")

st.set_page_config(layout="wide", page_title="Pro Cricket Scorer")
st.title("🏏 Pro Cricket Scoring System")

# --- HELPER FUNCTIONS ---
def get_teams():
    try:
        # Fetch current teams from the DB
        with conn.session as s:
            result = s.execute(text("SELECT name FROM teams")).fetchall()
        return [r[0] for r in result]
    except Exception as e:
        st.error(f"Error fetching teams: {e}")
        return []

menu = ["Schedule & Rosters", "Live Scoring", "Match History"]
choice = st.sidebar.selectbox("Menu", menu)

# --- PAGE 1: SCHEDULE & ROSTERS ---
if choice == "Schedule & Rosters":
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Manage Teams")
        t_name = st.text_input("New Team Name")
        if st.button("Add Team"): 
            if t_name:
                conn.session.execute(text("INSERT INTO teams (name) VALUES (:n)"), {"n": t_name})
                conn.session.commit()
                st.success(f"Added {t_name}!")
                st.rerun()
        
        teams = get_teams()
        sel_t = st.selectbox("Select Team for Player", teams if teams else ["Add a team first"])
        p_name = st.text_input("Player Name")
        if st.button("Add Player"): 
            if p_name:
                conn.session.execute(text("INSERT INTO players (team_name, name) VALUES (:t, :p)"), {"t": sel_t, "p": p_name})
                conn.session.commit()
                st.rerun()
            
    with c2:
        st.subheader("Schedule Match")
        teams = get_teams()
        ta = st.selectbox("Team A", teams if teams else [])
        tb = st.selectbox("Team B", teams if teams else [])
        m_date = st.date_input("Match Date")
        if st.button("Schedule Match"): 
            conn.session.execute(text("INSERT INTO matches (team_a, team_b, date, status) VALUES (:a, :b, :d, 'Scheduled')"), 
                                 {"a": ta, "b": tb, "d": m_date})
            conn.session.commit()
            st.success("Match Scheduled!"); st.rerun()

# --- PAGE 2: LIVE SCORING ---
elif choice == "Live Scoring":
    # Get all active matches
    with conn.session as s:
        matches = s.execute(text("SELECT * FROM matches WHERE status != 'Completed'")).mappings().all()
    
    if not matches: st.info("No active matches found. Please schedule one first."); st.stop()
    
    m = st.selectbox("Select Match", matches, format_func=lambda x: f"{x['team_a']} vs {x['team_b']} ({x['status']})")
    
    if m['status'] == 'Scheduled':
        with st.form("toss_form"):
            overs = st.number_input("Total Overs", 1, 50, 20)
            tw = st.radio("Toss Winner", [m['team_a'], m['team_b']])
            td = st.radio("Decision", ["Bat", "Bowl"])
            if st.form_submit_button("Start Match"): 
                conn.session.execute(text("UPDATE matches SET total_overs=:o, toss_winner=:tw, toss_decision=:td, status='Live' WHERE id=:id"), 
                                     {"o": overs, "tw": tw, "td": td, "id": m['id']})
                conn.session.commit(); st.rerun()
    else:
        state = json.loads(m['score_state'])
        st.metric("Score", f"{state['runs']}/{state['wickets']}", f"Overs: {state['balls']//6}.{state['balls']%6}")
        
        c1, c2, c3 = st.columns(3)
        if c1.button("0 Run"): 
            state['balls'] += 1
            conn.session.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), {"s": json.dumps(state), "id": m['id']})
            conn.session.commit(); st.rerun()
        if c2.button("1 Run"): 
            state['runs'] += 1; state['balls'] += 1
            conn.session.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), {"s": json.dumps(state), "id": m['id']})
            conn.session.commit(); st.rerun()
        if c3.button("End Match"): 
            conn.session.execute(text("UPDATE matches SET status='Completed' WHERE id=:id"), {"id": m['id']})
            conn.session.commit(); st.rerun()
