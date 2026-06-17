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
        s.execute(text('''CREATE TABLE IF NOT EXISTS matches (
            id SERIAL PRIMARY KEY, team_a TEXT, team_b TEXT, date DATE, 
            status TEXT DEFAULT 'Scheduled', toss_winner TEXT, toss_decision TEXT, 
            total_overs INTEGER DEFAULT 20, 
            score_state JSONB DEFAULT '{"runs":0, "wickets":0, "balls":0, "extras":0, "byes":0, "legbyes":0, "wides":0, "noballs":0}'
        )'''))
        s.commit()
init_db()

# --- SCORING ENGINE ---
def update_score(m_id, runs=0, wicket=False, extra_type=None):
    match = conn.query("SELECT score_state FROM matches WHERE id=:id", {"id": m_id}).iloc[0]
    state = json.loads(match['score_state'])
    
    state['runs'] += runs
    if wicket: state['wickets'] += 1
    if not extra_type: state['balls'] += 1
    if extra_type: state[extra_type] += 1
    
    conn.session.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), 
                         {"s": json.dumps(state), "id": m_id})
    conn.session.commit()

# --- UI ---
st.set_page_config(layout="wide", page_title="Pro Cricket Scorer")
st.title("🏏 Pro Cricket Scoring System")

menu = ["Schedule & Rosters", "Live Scoring", "Match History"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Schedule & Rosters":
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Add Teams/Players")
        t_name = st.text_input("Team Name")
        if st.button("Add Team"): conn.session.execute(text("INSERT INTO teams (name) VALUES (:n)"), {"n": t_name}); conn.session.commit(); st.rerun()
        
        teams = [r[0] for r in conn.session.execute(text("SELECT name FROM teams"))]
        sel_t = st.selectbox("Select Team", teams)
        p_name = st.text_input("Player Name")
        if st.button("Add Player"): conn.session.execute(text("INSERT INTO players (team_name, name) VALUES (:t, :p)"), {"t": sel_t, "p": p_name}); conn.session.commit(); st.rerun()
    with c2:
        st.subheader("Schedule Match")
        ta, tb = st.selectbox("Team A", teams), st.selectbox("Team B", teams)
        m_date = st.date_input("Date")
        if st.button("Schedule Match"): conn.session.execute(text("INSERT INTO matches (team_a, team_b, date) VALUES (:a, :b, :d)"), {"a": ta, "b": tb, "d": m_date}); conn.session.commit(); st.rerun()

elif choice == "Live Scoring":
    matches = conn.query("SELECT * FROM matches WHERE status != 'Completed'")
    if matches.empty: st.stop()
    m = st.selectbox("Select Match", matches.to_dict('records'), format_func=lambda x: f"{x['team_a']} vs {x['team_b']}")
    
    if not m['toss_winner']:
        with st.form("setup"):
            overs = st.number_input("Overs", 1, 50, 20)
            tw = st.radio("Toss Winner", [m['team_a'], m['team_b']])
            td = st.radio("Decision", ["Bat", "Bowl"])
            if st.form_submit_button("Start"): conn.session.execute(text("UPDATE matches SET total_overs=:o, toss_winner=:tw, toss_decision=:td, status='Live' WHERE id=:id"), {"o": overs, "tw": tw, "td": td, "id": m['id']}); conn.session.commit(); st.rerun()
    else:
        state = json.loads(m['score_state'])
        st.metric("Total Score", f"{state['runs']}/{state['wickets']}", f"Overs: {state['balls']//6}.{state['balls']%6}")
        
        # Scoring Row
        cols = st.columns(8)
        if cols[0].button("0"): update_score(m['id'], 0); st.rerun()
        if cols[1].button("1"): update_score(m['id'], 1); st.rerun()
        if cols[2].button("2"): update_score(m['id'], 2); st.rerun()
        if cols[3].button("4"): update_score(m['id'], 4); st.rerun()
        if cols[4].button("6"): update_score(m['id'], 6); st.rerun()
        if cols[5].button("Wide"): update_score(m['id'], 1, extra_type='wides'); st.rerun()
        if cols[6].button("Byes"): update_score(m['id'], 1, extra_type='byes'); st.rerun()
        
        with st.expander("🔴 Wicket Details"):
            d_type = st.selectbox("Dismissal", ["Bowled", "Caught", "Run Out", "LBW"])
            f_name = st.text_input("Fielder Name")
            if st.button("Confirm Out"): update_score(m['id'], 0, True); st.rerun()
