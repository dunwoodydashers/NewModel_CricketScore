import streamlit as st
import json
from sqlalchemy import text

# --- CONNECTION ---
conn = st.connection("supabase", type="sql", connect_args={"sslmode": "require"})

st.set_page_config(page_title="Pro Cricket Scorer", layout="wide")
st.title("🏏 Pro Cricket Scoring System")

# --- HELPER FUNCTIONS ---
def get_teams():
    try:
        with conn.session as s:
            return [r[0] for r in s.execute(text("SELECT name FROM teams")).fetchall()]
    except: return []

# --- UI ---
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
            with conn.session as s:
                players = s.execute(text("SELECT name FROM players WHERE team_name IN (:a, :b)"), {"a": m['team_a'], "b": m['team_b']}).fetchall()
            
            p_list = [p[0] for p in players]
            if not p_list: st.warning("Add players first!"); st.stop()
            
            s1 = st.selectbox("Striker", p_list)
            s2 = st.selectbox("Non-Striker", p_list)
            b = st.selectbox("Bowler", p_list)
            
            if st.button("Start Ball-by-Ball"):
                with conn.session as s:
                    s.execute(text("UPDATE matches SET striker_id=:s1, non_striker_id=:s2, bowler_id=:b, status='Live', score_state=:ss WHERE id=:id"), 
                              {"s1": s1, "s2": s2, "b": b, "ss": json.dumps({"runs":0, "wickets":0, "balls":0}), "id": m['id']})
                    s.commit()
                st.rerun()

        # --- PHASE 3: LIVE SCORING ---
        elif m['status'] == 'Live':
            st.write(f"**Striker:** {m['striker_id']} | **Non-Striker:** {m['non_striker_id']} | **Bowler:** {m['bowler_id']}")
            
            score_val = m['score_state']
            state = score_val if isinstance(score_val, dict) else json.loads(score_val)
            
            st.metric("Score", f"{state['runs']}/{state['wickets']}", f"Overs: {state['balls'] // 6}.{state['balls'] % 6}")
            
            b1, b2, b3, b4, b5 = st.columns(5)
            with conn.session as s:
                if b1.button("0 Run"): state['balls'] += 1; s.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), {"s": json.dumps(state), "id": m['id']}); s.commit(); st.rerun()
                if b2.button("1 Run"): state['runs'] += 1; state['balls'] += 1; s.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), {"s": json.dumps(state), "id": m['id']}); s.commit(); st.rerun()
                if b3.button("4 Runs"): state['runs'] += 4; state['balls'] += 1; s.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), {"s": json.dumps(state), "id": m['id']}); s.commit(); st.rerun()
                if b4.button("Wicket"): state['wickets'] += 1; state['balls'] += 1; s.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), {"s": json.dumps(state), "id": m['id']}); s.commit(); st.rerun()
                if b5.button("End Match"): s.execute(text("UPDATE matches SET status='Completed' WHERE id=:id"), {"id": m['id']}); s.commit(); st.rerun()
