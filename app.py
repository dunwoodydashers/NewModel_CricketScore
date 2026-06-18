import streamlit as st
import json
from sqlalchemy import text

# Streamlit connects to the URL in your secrets.toml
# Note: st.connection('supabase') works fine with Neon's Postgres URL
conn = st.connection("supabase", type="sql")

st.set_page_config(page_title="Pro Cricket Scorer", layout="wide")
st.title("🏏 Pro Cricket Scoring System")

def get_teams():
    try:
        with conn.session as s:
            result = s.execute(text("SELECT name FROM teams")).fetchall()
        return [r[0] for r in result]
    except Exception as e:
        return []

menu = ["Schedule & Rosters", "Live Scoring"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Schedule & Rosters":
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Manage Teams")
        t_name = st.text_input("New Team Name")
        if st.button("Add Team"):
            if t_name.strip():
                with conn.session as s:
                    s.execute(text("INSERT INTO teams (name) VALUES (:n)"), {"n": t_name.strip()})
                    s.commit()
                st.rerun()

        teams = get_teams()
        sel_t = st.selectbox("Select Team", teams if teams else ["Add a team first"])
        p_name = st.text_input("Player Name")
        if st.button("Add Player"):
            with conn.session as s:
                s.execute(text("INSERT INTO players (team_name, name) VALUES (:t, :p)"), {"t": sel_t, "p": p_name})
                s.commit()
            st.rerun()

    with c2:
        st.subheader("Schedule Match")
        teams = get_teams()
        ta = st.selectbox("Team A", teams if teams else [])
        tb = st.selectbox("Team B", teams if teams else [])
        if st.button("Schedule Match"):
            with conn.session as s:
                s.execute(text("INSERT INTO matches (team_a, team_b, status) VALUES (:a, :b, 'Scheduled')"), {"a": ta, "b": tb})
                s.commit()
            st.success("Match Scheduled!")

elif choice == "Live Scoring":
    with conn.session as s:
        matches = s.execute(text("SELECT * FROM matches WHERE status != 'Completed'")).mappings().all()
    
    if not matches:
        st.info("No active matches.")
    else:
        m = st.selectbox("Select Match", matches, format_func=lambda x: f"{x['team_a']} vs {x['team_b']}")
        state = json.loads(m['score_state'])
        st.metric("Score", f"{state['runs']}/{state['wickets']}")
        if st.button("Add Run"):
            state['runs'] += 1
            with conn.session as s:
                s.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), {"s": json.dumps(state), "id": m['id']})
                s.commit()
            st.rerun()
