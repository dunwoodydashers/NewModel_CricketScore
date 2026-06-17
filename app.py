import streamlit as st
from sqlalchemy import text

conn = st.connection("supabase", type="sql")

# --- NAVIGATION & STATE ---
st.set_page_config(layout="wide")
st.title("🏏 Pro Cricket Scorer")

# --- PAGE: LIVE SCORING ---
def live_scoring():
    matches = conn.query("SELECT * FROM matches WHERE status != 'Completed'")
    if not matches.empty:
        match = st.selectbox("Select Match", matches.to_dict('records'), format_func=lambda x: f"{x['team_a']} vs {x['team_b']}")
        m_id = match['id']

        # PHASE 1: CONFIGURATION (Toss & Overs)
        if not match['toss_winner']:
            st.subheader("Match Setup")
            overs = st.number_input("Total Overs", 1, 50, 20)
            winner = st.radio("Toss Winner", [match['team_a'], match['team_b']])
            decision = st.radio("Elected to", ["Bat", "Bowl"])
            if st.button("Start Match"):
                conn.session.execute(text("UPDATE matches SET total_overs=:o, toss_winner=:tw, toss_decision=:td, status='Live' WHERE id=:id"), 
                                     {"o": overs, "tw": winner, "td": decision, "id": m_id})
                conn.session.commit()
                st.rerun()
        
        # PHASE 2: SCORING CONSOLE
        else:
            st.success(f"Match Live: {match['team_a']} vs {match['team_b']} ({match['total_overs']} Overs)")
            
            # Wicket Logic
            with st.expander("🔴 Wicket"):
                dismissal = st.selectbox("Type", ["Bowled", "Caught", "Run Out", "LBW"])
                if dismissal in ["Caught", "Run Out"]:
                    fielder = st.text_input("Fielder Name")
                if st.button("Confirm Out"):
                    st.toast(f"Batsman out: {dismissal}")
                    # Logic to update database/score state here
            
            # Scoring Buttons (simplified example)
            cols = st.columns(6)
            if cols[0].button("0"): st.write("Dot ball")
            if cols[1].button("1"): st.write("Single")
            # ... Add remaining buttons for 2, 4, 6, Wide, Leg Bye
