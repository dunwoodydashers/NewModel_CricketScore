import streamlit as st
import json
from sqlalchemy import text

# --- 1. CONFIGURATION ---
# Ensure your secrets.toml has [connections.supabase] with your Neon/Postgres URL
# The connect_args fixes the channel_binding error
conn = st.connection(
    "supabase", 
    type="sql",
    connect_args={"sslmode": "require"} 
)

st.set_page_config(page_title="Pro Cricket Scorer", layout="wide")
st.title("🏏 Pro Cricket Scoring System")

# --- 2. HELPER FUNCTIONS ---
def get_teams():
    try:
        with conn.session as s:
            result = s.execute(text("SELECT name FROM teams")).fetchall()
        return [r[0] for r in result]
    except Exception:
        return []

# --- 3. UI LAYOUT ---
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
            if p_name.strip():
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
            if ta and tb:
                with conn.session as s:
                    s.execute(text("INSERT INTO matches (team_a, team_b, status) VALUES (:a, :b, 'Scheduled')"), {"a": ta, "b": tb})
                    s.commit()
                st.success("Match Scheduled!")
                st.rerun()

elif choice == "Live Scoring":
    st.subheader("Live Match Tracker")
    
    with conn.session as s:
        matches = s.execute(text("SELECT * FROM matches WHERE status != 'Completed'")).mappings().all()
    
    if not matches:
        st.info("No active matches found. Go to 'Schedule & Rosters' to start one!")
    else:
        m = st.selectbox("Select Match", matches, format_func=lambda x: f"{x['team_a']} vs {x['team_b']} ({x['status']})")
        
        # --- TOSS / START PHASE ---
        if m['status'] == 'Scheduled':
            with st.form("toss_form"):
                st.subheader("Start Match: Toss & Overs")
                overs = st.number_input("Total Overs", 1, 50, 20)
                tw = st.radio("Toss Winner", [m['team_a'], m['team_b']])
                td = st.radio("Decision", ["Bat", "Bowl"])
                if st.form_submit_button("Start Match"): 
                    with conn.session as s:
                        initial_state = json.dumps({"runs": 0, "wickets": 0, "balls": 0})
                        s.execute(text("""
                            UPDATE matches 
                            SET total_overs=:o, toss_winner=:tw, toss_decision=:td, status='Live', score_state=:s 
                            WHERE id=:id
                        """), {"o": overs, "tw": tw, "td": td, "s": initial_state, "id": m['id']})
                        s.commit()
                    st.rerun()
        
        # --- SCORING PHASE ---
        elif m['status'] == 'Live':
            # Handle JSON safely (Handles both String and Dict types)
            score_val = m['score_state']
            state = score_val if isinstance(score_val, dict) else json.loads(score_val)
            
            st.metric("Score", f"{state['runs']}/{state['wickets']}", f"Overs: {state['balls'] // 6}.{state['balls'] % 6}")
            
            st.write("---")
            b1, b2, b3, b4, b5 = st.columns(5)
            
            with conn.session as s:
                if b1.button("0 Run"):
                    state['balls'] += 1
                    s.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), {"s": json.dumps(state), "id": m['id']})
                    s.commit(); st.rerun()
                if b2.button("1 Run"):
                    state['runs'] += 1; state['balls'] += 1
                    s.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), {"s": json.dumps(state), "id": m['id']})
                    s.commit(); st.rerun()
                if b3.button("4 Runs"):
                    state['runs'] += 4; state['balls'] += 1
                    s.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), {"s": json.dumps(state), "id": m['id']})
                    s.commit(); st.rerun()
                if b4.button("Wicket"):
                    state['wickets'] += 1; state['balls'] += 1
                    s.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), {"s": json.dumps(state), "id": m['id']})
                    s.commit(); st.rerun()
                if b5.button("End Match"):
                    s.execute(text("UPDATE matches SET status='Completed' WHERE id=:id"), {"id": m['id']})
                    s.commit(); st.rerun()
