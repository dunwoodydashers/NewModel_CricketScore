import streamlit as st
from sqlalchemy import text

st.set_page_config(page_title="Pro Cricket Scoring System", layout="wide")
from sqlalchemy import create_engine, text

# Replace this with your actual connection string from Supabase
DATABASE_URL = "postgresql://postgres:[YOUR_PASSWORD]@db.[YOUR_PROJECT_ID].supabase.co:5432/postgres"

# Create the engine
engine = create_engine(DATABASE_URL)

# How to use it:
def add_team_direct(team_name):
    try:
        with engine.connect() as conn:
            conn.execute(text("INSERT INTO teams (name) VALUES (:name)"), {"name": team_name})
            conn.commit()
        return True
    except Exception as e:
        st.error(f"Direct connection error: {e}")
        return False

# -----------------------------
# UI
# -----------------------------
st.title("Manage Teams")

new_team = st.text_input("New Team Name")

if st.button("Add Team"):
    if new_team.strip():
        run_query(
            "INSERT INTO public.teams (name) VALUES (:name)",
            {"name": new_team.strip()}
        )
        st.success(f"Team '{new_team}' added!")
    else:
        st.warning("Team name cannot be empty.")

if st.button("Test Insert"):
    run_query("INSERT INTO public.teams (name) VALUES ('connection_test')")
    st.success("Insert worked")

# Show existing teams
rows = run_query("SELECT id, name FROM public.teams ORDER BY id ASC")
st.subheader("Teams in Database")
st.table(rows.fetchall())

# Diagnostics
st.subheader("Connection Test")
test = run_query("SELECT NOW()")
st.success(f"Database time: {test.fetchone()[0]}")

st.subheader("Database Info")
info = run_query("SELECT current_database(), inet_server_addr(), inet_server_port()")

rows = run_query("SELECT current_database(), inet_server_addr(), inet_server_port()")
st.table(rows.fetchall())



