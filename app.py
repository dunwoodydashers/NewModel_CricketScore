import streamlit as st
from sqlalchemy import text

st.set_page_config(page_title="Pro Cricket Scoring System", layout="wide")

# -----------------------------
# DATABASE CONNECTION (Session Pooler)
# -----------------------------
def get_conn():
    return st.connection("supabase", type="sql")

def run_query(query, params=None):
    try:
        conn = get_conn()  # ensure fresh session
        if params:
            result = conn.session.execute(text(query), params)
        else:
            result = conn.session.execute(text(query))
        conn.session.commit()
        return result
    except Exception as e:
        st.error(f"Database error: {e}")
        return None

# -----------------------------
# UI
# -----------------------------
st.title("Manage Teams")

new_team = st.text_input("New Team Name")

if st.button("Add Team"):
    if new_team.strip():
        run_query(
            "INSERT INTO teams (name) VALUES (:name)",
            {"name": new_team.strip()}
        )
        st.success(f"Team '{new_team}' added!")
    else:
        st.warning("Team name cannot be empty.")

# Show existing teams
rows = run_query("SELECT id, name FROM teams ORDER BY id ASC")

if rows:
    st.table(rows.fetchall())
