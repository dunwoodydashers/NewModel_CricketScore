import streamlit as st
import json
import pandas as pd
from sqlalchemy import text

# --- 1. CONFIGURATION ---
conn = st.connection("supabase", type="sql", connect_args={"sslmode": "require"})

st.set_page_config(page_title="Pro Cricket Scorer", layout="wide")
st.title("🏏 Pro Cricket Scoring System")

# --- 2. HELPER FUNCTIONS (Placed at Top Level) ---
def get_teams():
    try:
        with conn.session as s:
            return [r[0] for r in s.execute(text("SELECT name FROM teams")).fetchall()]
    except: return []

def upgrade_to_pro_state(state, striker, non_striker, bowler):
    """Ensures state has all required keys for professional stats."""
    if "batting" not in state:
        state = {
            "runs": state.get("runs", 0), "wickets": state.get("wickets", 0), "balls": state.get("balls", 0),
            "batting": {
                striker: {"r": 0, "b": 0, "4s": 0, "6s": 0},
                non_striker: {"r": 0, "b": 0, "4s": 0, "6s": 0}
            },
            "bowling": {bowler: {"r": 0, "b": 0, "w": 0, "wd": 0, "nb": 0}},
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
        state['bowling'][bowler]['b'] += 1 # Balls for economy
        if v == 4: state['batting'][striker]['4s'] += 1
        if v == 6: state['batting'][striker]['6s'] += 1
    elif t == 'wkt':
        state['wickets'] += 1
        state['bowling'][bowler]['w'] += 1
        state['balls'] += 1
    return state

# --- 3. UI LAYOUT ---
menu = ["Schedule & Rosters", "Live Scoring"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Schedule & Rosters":
    # (Keep your existing Roster code)
    st.write("Manage your teams and matches here.")

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
            # ... (Your existing Toss Logic) ...
            st.warning("Match is scheduled. Please initialize toss.")

        # --- PHASE 2: LINEUP ---
        elif m['status'] == 'Lineup':
            # ... (Your existing Lineup Logic) ...
            st.warning("Match is in lineup phase.")

        # --- PHASE 3: LIVE SCORING ---
        elif m['status'] == 'Live':
            # 1. Load & Upgrade State
            state = json.loads(m['score_state']) if isinstance(m['score_state'], str) else m['score_state']
            state = upgrade_to_pro_state(state, m['striker_id'], m['non_striker_id'], m['bowler_id'])
            
            st.metric("Total Score", f"{state['runs']}/{state['wickets']}", f"Overs: {state['balls'] // 6}.{state['balls'] % 6}")
            
            # 2. Action Grid (Scoring Buttons)
            st.subheader("Action Bar")
            cols = st.columns(6)
            for i in range(1, 7):
                if cols[i-1].button(f"{i} Run"):
                    state = process_ball(state, {'type': 'run', 'val': i}, m['striker_id'], m['bowler_id'])
                    with conn.session as s:
                        s.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), {"s": json.dumps(state), "id": m['id']})
                        s.commit()
                    st.rerun()
            
            if st.button("Wicket"):
                state = process_ball(state, {'type': 'wkt', 'val': 0}, m['striker_id'], m['bowler_id'])
                with conn.session as s:
                    s.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), {"s": json.dumps(state), "id": m['id']})
                    s.commit()
                st.rerun()

            # 3. Tables (Pro Scorecard)
            st.divider()
            col_a, col_b = st.columns(2)
            with col_a:
                st.write("### Batters")
                bat_df = pd.DataFrame.from_dict(state['batting'], orient='index')
                bat_df['SR'] = (bat_df['r'] / bat_df['b'] * 100).fillna(0).round(2)
                st.table(bat_df)
            with col_b:
                st.write("### Bowler")
                bowl_df = pd.DataFrame.from_dict(state['bowling'], orient='index')
                st.table(bowl_df)
