import streamlit as st
import json
from sqlalchemy import text

# --- PAGE CONFIG ---
st.set_page_config(layout="wide", page_title="Pro Cricket Scorer")
st.title("🏏 Pro Cricket Scoring System")

# --- DATABASE CONNECTION ---
# Requires secrets in Streamlit Cloud:
# [supabase]
# dialect = "postgresql"
# host = "<your-project>.supabase.co"
# port = 5432
# database = "postgres"
# username = "postgres"
# password = "<YOUR_SUPABASE_DB_PASSWORD>"
try:
    conn = st.connection("supabase", type="sql")
except Exception as e:
    st.error("❌ Could not connect to database. Check Streamlit secrets and Supabase credentials.")
    st.stop()

# --- HELPER FUNCTIONS ---
def get_teams():
    try:
        with conn.session as s:
            result = s.execute(text("SELECT id, name FROM teams ORDER BY name")).mappings().all()
        return result
    except Exception as e:
        st.error(f"Error fetching teams: {e}")
        return []

def get_players(team_name=None):
    try:
        with conn.session as s:
            if team_name:
                result = s.execute(
                    text("SELECT id, team_name, name FROM players WHERE team_name = :t ORDER BY name"),
                    {"t": team_name},
                ).mappings().all()
            else:
                result = s.execute(
                    text("SELECT id, team_name, name FROM players ORDER BY team_name, name")
                ).mappings().all()
        return result
    except Exception as e:
        st.error(f"Error fetching players: {e}")
        return []

def get_active_matches():
    try:
        with conn.session as s:
            matches = s.execute(
                text("SELECT * FROM matches WHERE status != 'Completed' ORDER BY date DESC, id DESC")
            ).mappings().all()
        return matches
    except Exception as e:
        st.error(f"Error fetching matches: {e}")
        return []

def get_completed_matches():
    try:
        with conn.session as s:
            matches = s.execute(
                text("SELECT * FROM matches WHERE status = 'Completed' ORDER BY date DESC, id DESC")
            ).mappings().all()
        return matches
    except Exception as e:
        st.error(f"Error fetching match history: {e}")
        return []

def init_score_state(raw_state):
    """Ensure score_state is always a valid dict."""
    if not raw_state:
        return {"runs": 0, "wickets": 0, "balls": 0, "extras": 0}
    try:
        state = json.loads(raw_state)
        # Ensure required keys exist
        for k in ["runs", "wickets", "balls", "extras"]:
            state.setdefault(k, 0)
        return state
    except Exception:
        return {"runs": 0, "wickets": 0, "balls": 0, "extras": 0}

def save_score_state(match_id, state):
    try:
        with conn.session as s:
            s.execute(
                text("UPDATE matches SET score_state = :s WHERE id = :id"),
                {"s": json.dumps(state), "id": match_id},
            )
            s.commit()
    except Exception as e:
        st.error(f"Error updating score: {e}")

# --- SIDEBAR MENU ---
menu = ["Schedule & Rosters", "Live Scoring", "Match History"]
choice = st.sidebar.selectbox("Menu", menu)

# --- PAGE 1: SCHEDULE & ROSTERS ---
if choice == "Schedule & Rosters":
    c1, c2 = st.columns(2)

    # --- Manage Teams & Players ---
    with c1:
        st.subheader("Manage Teams")

        # Add Team
        t_name = st.text_input("New Team Name")
        if st.button("Add Team"):
            if t_name.strip():
                try:
                    with conn.session as s:
                        s.execute(
                            text("INSERT INTO teams (name) VALUES (:n)"),
                            {"n": t_name.strip()},
                        )
                        s.commit()
                    st.success(f"✅ Added team: {t_name}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error adding team: {e}")
            else:
                st.warning("Please enter a valid team name.")

        teams = get_teams()
        team_names = [t["name"] for t in teams]

        # Add Player
        st.markdown("---")
        st.subheader("Add Players")
        sel_t = st.selectbox(
            "Select Team for Player",
            team_names if team_names else ["No teams yet"],
        )
        p_name = st.text_input("Player Name")
        if st.button("Add Player"):
            if not team_names:
                st.warning("Create a team before adding players.")
            elif p_name.strip():
                try:
                    with conn.session as s:
                        s.execute(
                            text("INSERT INTO players (team_name, name) VALUES (:t, :p)"),
                            {"t": sel_t, "p": p_name.strip()},
                        )
                        s.commit()
                    st.success(f"✅ Added player {p_name} to {sel_t}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error adding player: {e}")
            else:
                st.warning("Please enter a valid player name.")

        # Team & Player listing
        st.markdown("---")
        st.subheader("Teams & Players")
        if teams:
            for t in teams:
                st.markdown(f"**{t['name']}**")
                players = get_players(t["name"])
                if players:
                    st.write(", ".join([p["name"] for p in players]))
                else:
                    st.write("_No players yet_")
        else:
            st.info("No teams created yet.")

    # --- Schedule Matches ---
    with c2:
        st.subheader("Schedule Match")

        teams = get_teams()
        team_names = [t["name"] for t in teams]

        if len(team_names) < 2:
            st.info("You need at least two teams to schedule a match.")
        else:
            ta = st.selectbox("Team A", team_names, key="team_a_select")
            tb = st.selectbox("Team B", team_names, key="team_b_select")
            m_date = st.date_input("Match Date")

            if st.button("Schedule Match"):
                if ta == tb:
                    st.warning("Team A and Team B must be different.")
                else:
                    try:
                        with conn.session as s:
                            s.execute(
                                text(
                                    """
                                    INSERT INTO matches (team_a, team_b, date, status, score_state)
                                    VALUES (:a, :b, :d, 'Scheduled',
                                            '{"runs":0,"wickets":0,"balls":0,"extras":0}')
                                    """
                                ),
                                {"a": ta, "b": tb, "d": m_date},
                            )
                            s.commit()
                        st.success("✅ Match Scheduled!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error scheduling match: {e}")

# --- PAGE 2: LIVE SCORING ---
elif choice == "Live Scoring":
    st.subheader("Live Scoring")

    matches = get_active_matches()
    if not matches:
        st.info("No active or scheduled matches found. Please schedule a match first.")
        st.stop()

    m = st.selectbox(
        "Select Match",
        matches,
        format_func=lambda x: f"{x['team_a']} vs {x['team_b']} ({x['status']}) on {x['date']}",
    )

    # If match is still scheduled, set toss and overs
    if m["status"] == "Scheduled":
        st.info("Match is scheduled but not started yet.")
        with st.form("toss_form"):
            overs = st.number_input("Total Overs", 1, 50, int(m.get("total_overs") or 20))
            tw = st.radio("Toss Winner", [m["team_a"], m["team_b"]])
            td = st.radio("Decision", ["Bat", "Bowl"])
            start_btn = st.form_submit_button("Start Match")

            if start_btn:
                try:
                    with conn.session as s:
                        s.execute(
                            text(
                                """
                                UPDATE matches
                                SET total_overs = :o,
                                    toss_winner = :tw,
                                    toss_decision = :td,
                                    status = 'Live'
                                WHERE id = :id
                                """
                            ),
                            {"o": overs, "tw": tw, "td": td, "id": m["id"]},
                        )
                        s.commit()
                    st.success("✅ Match started!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error starting match: {e}")

    else:
        # Live match scoring
        state = init_score_state(m["score_state"])
        balls = state["balls"]
        overs_done = balls // 6
        balls_in_over = balls % 6
        total_overs = m.get("total_overs") or 20

        st.metric(
            "Score",
            f"{state['runs']}/{state['wickets']}",
            f"Overs: {overs_done}.{balls_in_over} / {total_overs}",
        )
        st.write(f"Extras: {state['extras']}")

        # Scoring controls
        c1, c2, c3, c4 = st.columns(4)

        # 0 run
        if c1.button("0 Run"):
            state["balls"] += 1
            save_score_state(m["id"], state)
            st.rerun()

        # 1, 2, 3, 4, 6 runs
        with c2:
            run = st.selectbox("Runs", [1, 2, 3, 4, 6], key="runs_select")
            if st.button("Add Runs"):
                state["runs"] += run
                state["balls"] += 1
                save_score_state(m["id"], state)
                st.rerun()

        # Wicket
        with c3:
            if st.button("Wicket"):
                state["wickets"] += 1
                state["balls"] += 1
                save_score_state(m["id"], state)
                st.rerun()

        # Extras (no ball, wide, etc.)
        with c4:
            extra_type = st.selectbox("Extra Type", ["Wide", "No Ball", "Bye", "Leg Bye"], key="extra_type")
            extra_runs = st.number_input("Extra Runs", 1, 6, 1, key="extra_runs")
            if st.button("Add Extra"):
                # For simplicity: wides/no balls add runs but may or may not count as balls
                # Here we treat wides/no balls as not counting balls, byes/leg byes as counting balls.
                if extra_type in ["Wide", "No Ball"]:
                    state["runs"] += extra_runs
                    state["extras"] += extra_runs
                else:
                    state["runs"] += extra_runs
                    state["extras"] += extra_runs
                    state["balls"] += 1
                save_score_state(m["id"], state)
                st.rerun()

        # End match
        st.markdown("---")
        if st.button("End Match"):
            try:
                with conn.session as s:
                    s.execute(
                        text("UPDATE matches SET status = 'Completed' WHERE id = :id"),
                        {"id": m["id"]},
                    )
                    s.commit()
                st.success("✅ Match marked as completed.")
                st.rerun()
            except Exception as e:
                st.error(f"Error ending match: {e}")

# --- PAGE 3: MATCH HISTORY ---
elif choice == "Match History":
    st.subheader("Match History")

    matches = get_completed_matches()
    if not matches:
        st.info("No completed matches yet.")
    else:
        for m in matches:
            state = init_score_state(m["score_state"])
            balls = state["balls"]
            overs_done = balls // 6
            balls_in_over = balls % 6

            st.markdown(
                f"**{m['team_a']} vs {m['team_b']}** on {m['date']}  "
                f"- Final Score: {state['runs']}/{state['wickets']} in {overs_done}.{balls_in_over} overs "
                f"(Extras: {state['extras']})"
            )
