import streamlit as st
from sqlalchemy import create_engine, text
import pandas as pd
import datetime

st.set_page_config(page_title="Pro Cricket Scoring System", layout="wide")

# -----------------------------
# DATABASE CONNECTION (SESSION POOLER)
# -----------------------------
# Streamlit Cloud reads secrets from st.secrets
DB_URL = st.secrets["supabase"]["url"]

engine = create_engine(DB_URL)

def run_query(query, params=None):
    try:
        with engine.connect() as conn:
            if params:
                result = conn.execute(text(query), params)
            else:
                result = conn.execute(text(query))
            try:
                return result.fetchall()
            except:
                return None
    except Exception as e:
        st.error(f"Database error: {e}")
        return None

# -----------------------------
# UI SECTIONS
# -----------------------------
st.sidebar.title("Menu")
menu = st.sidebar.selectbox("Select", ["Schedule & Rosters"])

if menu == "Schedule & Rosters":
    col1, col2 = st.columns(2)

    # -----------------------------
    # MANAGE TEAMS
    # -----------------------------
    with col1:
        st.header("Manage Teams")
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

        st.subheader("Existing Teams")
        teams = run_query("SELECT id, name FROM teams ORDER BY name ASC")
        if teams:
            df_teams = pd.DataFrame(teams, columns=["ID", "Team Name"])
            st.table(df_teams)

    # -----------------------------
    # SCHEDULE MATCH
    # -----------------------------
    with col2:
        st.header("Schedule Match")

        teams = run_query("SELECT name FROM teams ORDER BY name ASC")
        team_list = [t[0] for t in teams] if teams else []

        if len(team_list) < 2:
            st.info("You need at least two teams to schedule a match.")
        else:
            team_a = st.selectbox("Team A", team_list)
            team_b = st.selectbox("Team B", team_list)
            match_date = st.date_input("Match Date", datetime.date.today())
            overs = st.number_input("Total Overs", min_value=1, max_value=50, value=20)

            if st.button("Create Match"):
                if team_a == team_b:
                    st.error("Teams must be different.")
                else:
                    run_query(
                        """
                        INSERT INTO matches (team_a, team_b, date, total_overs)
                        VALUES (:a, :b, :d, :o)
                        """,
                        {"a": team_a, "b": team_b, "d": match_date, "o": overs}
                    )
                    st.success("Match scheduled successfully!")
