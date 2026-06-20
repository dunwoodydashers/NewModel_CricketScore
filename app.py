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
    """Ensures state has the correct dictionary keys."""
    if "batting" not in state:
        return {
            "runs": state.get("runs", 0),
            "wickets": state.get("wickets", 0),
            "balls": state.get("balls", 0),
            "batting": {
                striker: {"r": 0, "b": 0, "4s": 0, "6s": 0},
                non_striker: {"r": 0, "b": 0, "4s": 0, "6s": 0}
            },
            "bowling": {
                bowler: {"r": 0, "b": 0, "w": 0, "wd": 0}
            }
        }
    return state

# --- 3. UI LAYOUT ---
menu = ["Schedule & Rosters", "Live Scoring"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Schedule & Rosters":
    # ... (Keep your existing Roster logic)
    pass 

elif choice == "Live Scoring":
    st.subheader("Live Match Tracker")
    with conn.session as s:
        matches = s.execute(text("SELECT * FROM matches WHERE status != 'Completed'")).mappings().all()
    
    if not matches:
        st.info("No active matches found.")
    else:
        m = st.selectbox("Select Match", matches, format_func=lambda x: f"{x['team_a']} vs {x['team_b']} ({x['status']})")
        
        if m['status'] == 'Live':
            # Load State
            state = json.loads(m['score_state']) if isinstance(m['score_state'], str) else m['score_state']
            state = upgrade_to_pro_state(state, m['striker_id'], m['non_striker_id'], m['bowler_id'])
            
            # --- DASHBOARD ---
            st.metric("Total Score", f"{state['runs']}/{state['wickets']}", f"Overs: {state['balls'] // 6}.{state['balls'] % 6}")
            
            # --- ACTION GRID ---
            st.write("### Scoring Actions")
            cols = st.columns(6)
            
            # Helper to update DB
            def update_db(new_state):
                with conn.session as s:
                    s.execute(text("UPDATE matches SET score_state=:s WHERE id=:id"), 
                              {"s": json.dumps(new_state), "id": m['id']})
                    s.commit()
                st.rerun()

            for i in range(1, 7):
                if cols[i-1].button(f"{i} Run"):
                    state['runs'] += i
                    state['batting'][m['striker_id']]['r'] += i
                    state['batting'][m['striker_id']]['b'] += 1
                    state['bowling'][m['bowler_id']]['r'] += i
                    state['bowling'][m['bowler_id']]['b'] += 1
                    if i == 4: state['batting'][m['striker_id']]['4s'] += 1
                    if i == 6: state['batting'][m['striker_id']]['6s'] += 1
                    update_db(state)

            if st.button("Wicket", type="primary"):
                state['wickets'] += 1
                state['bowling'][m['bowler_id']]['w'] += 1
                state['balls'] += 1
                update_db(state)

            # --- SCORECARDS ---
            # --- PRO SCORECARD ---
            st.write("### Batting Scorecard")
            bat_df = pd.DataFrame.from_dict(state['batting'], orient='index')
            
            # Normalize column names: If keys are 'runs'/'balls', map them to 'r'/'b'
            if 'runs' in bat_df.columns: bat_df = bat_df.rename(columns={'runs': 'r'})
            if 'balls' in bat_df.columns: bat_df = bat_df.rename(columns={'balls': 'b'})
            
            # Ensure columns exist before calculating
            if 'r' in bat_df.columns and 'b' in bat_df.columns:
                bat_df['SR'] = (bat_df['r'] / bat_df['b'] * 100).fillna(0).round(2)
                st.table(bat_df)
            else:
                st.write("Stats data not yet formatted correctly.")
            
            st.write("### Bowling Scorecard")
            bowl_df = pd.DataFrame.from_dict(state['bowling'], orient='index')
            
            # Normalize column names for Bowler
            if 'runs' in bowl_df.columns: bowl_df = bowl_df.rename(columns={'runs': 'r'})
            if 'balls' in bowl_df.columns: bowl_df = bowl_df.rename(columns={'balls': 'b'})
            
            st.table(bowl_df)
