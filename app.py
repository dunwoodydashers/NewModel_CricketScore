import streamlit as st
import json
from sqlalchemy import text

# --- DATABASE SETUP ---
conn = st.connection("supabase", type="sql")

def init_db():
    with conn.session as s:
        s.execute(text('CREATE TABLE IF NOT EXISTS teams (id SERIAL PRIMARY KEY, name TEXT UNIQUE)'))
        s.execute(text('CREATE TABLE IF NOT EXISTS players (id SERIAL PRIMARY KEY, team_name TEXT, name TEXT)'))
        s.execute(text('''CREATE TABLE IF NOT EXISTS matches (
            id SERIAL PRIMARY KEY, 
            team_a TEXT, team_b TEXT, date DATE, 
            status TEXT DEFAULT 'Scheduled', 
            toss_winner TEXT, toss_decision TEXT, 
            total_overs INTEGER DEFAULT 20
        )'''))
        try:
            s.execute(text("ALTER TABLE matches ADD COLUMN IF NOT EXISTS score_state JSONB DEFAULT '{\"runs\":0, \"wickets\":0, \"balls\":0, \"extras\":0}'::jsonb"))
        except: pass
        s.commit()

init_db()

# --- SCORING ENGINE ---
def update_score(m_id, runs=0, wicket=False, extra=False):
    with conn.session as s:
        res = s.execute(text("SELECT score_state FROM matches WHERE id=:id"), {"id": m_id}).fetchone()
        state = json.loads(res[0])
        state['runs'] += runs
        if wicket: state['wickets'] += 1
        if not extra: state['balls'] += 1
        else: state['extras'] += runs
        s.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), {"s": json.dumps(state), "id": m_id})
        s.commit()

# --- UI ---
st.set_page_config(layout="wide", page_title="Pro Cricket Scorer")
st.title("🏏 Pro Cricket Scoring System")

menu = ["Schedule & Rosters", "Live Scoring", "Match History"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Schedule & Rosters":
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Manage Teams")
        t_name = st.text_input("New Team Name")
        if st.button("Add Team"): 
            conn.session.execute(text("INSERT INTO teams (name) VALUES (:n)"), {"n": t_name}); conn.session.commit(); st.rerun()
        teams = [r[0] for r in conn.session.execute(text("SELECT name FROM teams"))]
        sel_t = st.selectbox("Select Team", teams)
        p_name = st.text_input("Player Name")
        if st.button("Add Player"): 
            conn.session.execute(text("INSERT INTO players (team_name, name) VALUES (:t, :p)"), {"t": sel_t, "p": p_name}); conn.session.commit(); st.rerun()
    with c2:
        st.subheader("Schedule Match")
        ta, tb = st.selectbox("Team A", teams), st.selectbox("Team B", teams)
        m_date = st.date_input("Date")
        if st.button("Schedule Match"): 
            # Force status as 'Scheduled'
            conn.session.execute(text("INSERT INTO matches (team_a, team_b, date, status) VALUES (:a, :b, :d, 'Scheduled')"), 
                                 {"a": ta, "b": tb, "d": m_date})
            conn.session.commit(); st.success("Match Scheduled!"); st.rerun()

elif choice == "Live Scoring":
    # Broad query to see all matches that are not completed
    matches = conn.query("SELECT * FROM matches WHERE status != 'Completed'")
    if matches.empty: 
        st.info("No active matches. Go to 'Schedule & Rosters' to create one.")
        st.stop()
    
    m = st.selectbox("Select Match", matches.to_dict('records'), format_func=lambda x: f"{x['team_a']} vs {x['team_b']} [{x['status']}]")
    
    if m['status'] == 'Scheduled':
        with st.form("toss_form"):
            st.subheader("Start Match: Toss & Overs")
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
        
        c1, c2, c3, c4 = st.columns(4)
        if c1.button("0 Run"): update_score(m['id'], 0); st.rerun()
        if c2.button("1 Run"): update_score(m['id'], 1); st.rerun()
        if c3.button("Wicket"): update_score(m['id'], 0, True); st.rerun()
        if c4.button("End Match"): conn.session.execute(text("UPDATE matches SET status='Completed' WHERE id=:id"), {"id": m['id']}); conn.session.commit(); st.rerun()
