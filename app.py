import streamlit as st
import json
import pandas as pd
from sqlalchemy import text

# --- 1. CONFIGURATION ---
conn = st.connection("supabase", type="sql", connect_args={"sslmode": "require"})

st.set_page_config(page_title="Pro Cricket Scorer", layout="wide")
st.title("🏏 Pro Cricket Scoring System")

# --- 2. HELPER FUNCTIONS (Must be at top level) ---
def get_teams():
    try:
        with conn.session as s:
            return [r[0] for r in s.execute(text("SELECT name FROM teams")).fetchall()]
    except: return []

def upgrade_to_pro_state(state, striker, non_striker, bowler):
    if "batting" not in state:
        state = {
            "runs": state.get("runs", 0), "wickets": state.get("wickets", 0), "balls": state.get("balls", 0),
            "batting": {striker: {"r": 0, "b": 0, "4s": 0, "6s": 0}, non_striker: {"r": 0, "b": 0, "4s": 0, "6s": 0}},
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
        state['bowling'][bowler]['b'] += 1
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
    # (Your existing Roster code)
    st.write("Roster Management is active.") 
    # ... [Keep your existing Roster logic here] ...

elif choice == "Live Scoring":
    st.subheader("Live Match Tracker")
    
    # 1. Fetch Matches
    try:
        with conn.session as s:
            matches = s.execute(text("SELECT * FROM matches WHERE status != 'Completed'")).mappings().all()
    except Exception as e:
        st.error(f"DB Error: {e}")
        st.stop()
    
    if not matches:
        st.info("No active matches found. Schedule one first!")
    else:
        m = st.selectbox("Select Match", matches, format_func=lambda x: f"{x['team_a']} vs {x['team_b']} ({x['status']})")
        
        # --- PHASE 1: TOSS ---
        if m['status'] == 'Scheduled':
            # ... [Keep your existing Toss logic here] ...
            st.warning("Match is scheduled. Perform toss in the setup phase.")

        # --- PHASE 2: LINEUP ---
        elif m['status'] == 'Lineup':
            st.write("Match is in Lineup selection phase.")
            # ... [Keep your existing Lineup logic here] ...

        # --- PHASE 3: LIVE SCORING ---
        elif m['status'] == 'Live':
            st.divider()
            
            # Load State
            state = json.loads(m['score_state']) if isinstance(m['score_state'], str) else m['score_state']
            state = upgrade_to_pro_state(state, m['striker_id'], m['non_striker_id'], m['bowler_id'])
            
            # Dashboard Container
            with st.container():
                c1, c2 = st.columns([1, 3])
                c1.metric("Total Score", f"{state['runs']}/{state['wickets']}")
                c2.write(f"**Striker:** {m['striker_id']} | **Bowler:** {m['bowler_id']}")
            
            # Action Grid
            st.subheader("Action Bar")
            cols = st.columns(6)
            for i in range(1, 7):
                if cols[i-1].button(f"{i} Run"):
                    state = process_ball(state, {'type': 'run', 'val': i}, m['striker_id'], m['bowler_id'])
                    with conn.session as s:
                        s.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), {"s": json.dumps(state), "id": m['id']}); s.commit(); st.rerun()
            
            if st.button("Wicket", type="primary"):
                state = process_ball(state, {'type': 'wkt', 'val': 0}, m['striker_id'], m['bowler_id'])
                with conn.session as s:
                    s.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), {"s": json.dumps(state), "id": m['id']}); s.commit(); st.rerun()

            # Scorecard Table
            st.divider()
            st.write("### Scorecard")
            bat_df = pd.DataFrame.from_dict(state['batting'], orient='index')
            bat_df['SR'] = (bat_df['r'] / bat_df['b'] * 100).fillna(0).round(2)
            st.table(bat_df)
