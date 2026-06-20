import streamlit as st
import json
import pandas as pd
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
    """Ensures state has all required keys for professional stats."""
    if "batting" not in state:
        state = {
            "runs": state.get("runs", 0),
            "wickets": state.get("wickets", 0),
            "balls": state.get("balls", 0),
            "batting": {
                striker: {"r": 0, "b": 0, "4s": 0, "6s": 0},
                non_striker: {"r": 0, "b": 0, "4s": 0, "6s": 0}
            },
            "bowling": {bowler: {"o": 0, "r": 0, "w": 0, "wd": 0, "nb": 0}},
            "extras": {"wd": 0, "nb": 0, "bye": 0, "lb": 0}
        }
    return state

def process_ball(state, action, striker, bowler):
    t, v = action['type'], action.get('val', 0)
    if t == 'run':
        state['runs'] += v
        state['batting'][striker]['r'] += v
        state['batting'][striker]['b'] += 1
        state['bowling'][bowler]['r'] += v
        if v == 4: state['batting'][striker]['4s'] += 1
        if v == 6: state['batting'][striker]['6s'] += 1
    elif t == 'wkt':
        state['wickets'] += 1
        state['bowling'][bowler]['w'] += 1
    elif t == 'wd':
        state['runs'] += 1
        state['bowling'][bowler]['wd'] += 1
    return state

# --- 3. UI LAYOUT ---
menu = ["Schedule & Rosters", "Live Scoring"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Schedule & Rosters":
    # ... (Your existing scheduling code remains unchanged)
    pass 

elif choice == "Live Scoring":
    st.subheader("Live Match Tracker")
    with conn.session as s:
        matches = s.execute(text("SELECT * FROM matches WHERE status != 'Completed'")).mappings().all()
    
    if not matches:
        st.info("No active matches found.")
    else:
        m = st.selectbox("Select Match", matches, format_func=lambda x: f"{x['team_a']} vs {x['team_b']} ({x['status']})")
        
        # --- PHASE 1: TOSS ---
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

        # --- PHASE 2: LINEUP ---
        elif m['status'] == 'Lineup':
            # Logic to determine teams...
            bat_team = m['toss_winner'] if m['toss_decision'] == 'Bat' else (m['team_a'] if m['toss_winner'] == m['team_b'] else m['team_b'])
            bowl_team = m['team_a'] if bat_team == m['team_b'] else m['team_b']
            
            with conn.session as s:
                bat_list = [p[0] for p in s.execute(text("SELECT name FROM players WHERE team_name = :t"), {"t": bat_team}).fetchall()]
                bowl_list = [p[0] for p in s.execute(text("SELECT name FROM players WHERE team_name = :t"), {"t": bowl_team}).fetchall()]
            
            s1 = st.selectbox("Striker", bat_list)
            s2 = st.selectbox("Non-Striker", [p for p in bat_list if p != s1])
            b = st.selectbox("Bowler", bowl_list)
            
            if st.button("Start Ball-by-Ball"):
                with conn.session as s:
                    s.execute(text("UPDATE matches SET striker_id=:s1, non_striker_id=:s2, bowler_id=:b, status='Live', score_state=:ss WHERE id=:id"), 
                              {"s1": s1, "s2": s2, "b": b, "ss": json.dumps({"runs":0}), "id": m['id']})
                    s.commit()
                st.rerun()

        # --- PHASE 3: LIVE SCORING ---
        elif m['status'] == 'Live':
            # Load State
            state = json.loads(m['score_state']) if isinstance(m['score_state'], str) else m['score_state']
            state = upgrade_to_pro_state(state, m['striker_id'], m['non_striker_id'], m['bowler_id'])
            
            st.metric("Total Score", f"{state['runs']}/{state['wickets']}")
            
            # Action Buttons
            cols = st.columns(6)
            for i in range(1, 7):
                if cols[i-1].button(str(i)):
                    state = process_ball(state, {'type': 'run', 'val': i}, m['striker_id'], m['bowler_id'])
                    with conn.session as s:
                        s.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), {"s": json.dumps(state), "id": m['id']}); s.commit(); st.rerun()
            
            if st.button("Wicket"):
                state = process_ball(state, {'type': 'wkt', 'val': 0}, m['striker_id'], m['bowler_id'])
                with conn.session as s:
                    s.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), {"s": json.dumps(state), "id": m['id']}); s.commit(); st.rerun()

            # --- DISPLAY TABLES ---
            st.write("### Batting")
            bat_df = pd.DataFrame.from_dict(state['batting'], orient='index')
            bat_df['SR'] = (bat_df['r'] / bat_df['b'] * 100).fillna(0).round(2)
            st.table(bat_df)

            st.write("### Bowling")
            bowl_df = pd.DataFrame.from_dict(state['bowling'], orient='index')
            st.table(bowl_df)
