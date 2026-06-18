import streamlit as st
import json
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

if st.button("Test Insert"):
    try:
        run_query("INSERT INTO teams (name) VALUES ('connection_test')")
        st.success("Insert worked")
    except Exception as e:
        st.error(f"Insert failed: {e}")


# Show existing teams
st.subheader("Connection Test")

try:
    test = run_query("SELECT NOW()")
    st.success(f"Database time: {test.fetchone()[0]}")
except Exception as e:
    st.error(f"Connection failed: {e}")

st.subheader("Check which 'teams' table exists")

rows = run_query("""
    SELECT table_schema, table_name 
    FROM information_schema.tables 
    WHERE table_name ILIKE '%team%'
""")

if rows:
    st.table(rows.fetchall())
else:
    st.write("No tables found.")

rows = run_query("SELECT current_database(), inet_server_addr(), inet_server_port()")
st.table(rows.fetchall())

st.subheader("Where is the row actually going?")

rows = run_query("""
    SELECT table_schema, table_name
    FROM information_schema.tables
    WHERE table_name = 'teams'
""")
st.table(rows.fetchall())

rows2 = run_query("""
    SELECT table_schema, table_name
    FROM information_schema.columns
    WHERE column_name = 'name'
""")
st.table(rows2.fetchall())

