import streamlit as st
import json
from sqlalchemy import text

# 1. DATABASE CONFIGURATION
# Streamlit will look for [connections.supabase] in your secrets.toml
conn = st.connection("supabase", type="sql")

st.set_page_config(page_title="Pro Cricket Scoring System", layout="wide")
st.title("🏏 Pro Cricket Scoring System")

# 2. HELPER FUNCTIONS (Defined BEFORE usage)
def execute_query(query, params=None):
    try:
        with conn.session as s:
            result = s.execute(text(query), params or {})
            s.commit()
            return result
    except Exception as e:
        st.error(f"Database error: {e}")
        return None

# 3. UI
st.subheader("Manage Teams")
new_team = st.text_input("New Team Name")

if st.button("Add Team"):
    if new_team.strip():
        # Using the helper function
        execute_query("INSERT INTO public.teams (name) VALUES (:name)", {"name": new_team.strip()})
        st.success(f"Team '{new_team}' added!")
        st.rerun() # Refresh to see changes
    else:
        st.warning("Team name cannot be empty.")

# Show existing teams
st.subheader("Teams in Database")
try:
    with conn.session as s:
        # If this returns empty, RLS is likely still on!
        teams = s.execute(text("SELECT id, name FROM public.teams ORDER BY id ASC")).fetchall()
        if teams:
            st.table(teams)
        else:
            st.info("No teams found in database.")
except Exception as e:
    st.error(f"Could not read from database: {e}")

# Diagnostics (Hidden in sidebar to keep UI clean)
with st.sidebar:
    st.subheader("Diagnostics")
    if st.button("Check Connection"):
        try:
            with conn.session as s:
                time = s.execute(text("SELECT NOW()")).fetchone()
                st.success(f"Database Time: {time[0]}")
        except Exception as e:
            st.error(f"Connection Failed: {e}")
