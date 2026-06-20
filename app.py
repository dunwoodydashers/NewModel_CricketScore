import streamlit as st
import json
from sqlalchemy import text
import pandas as pd

# --- KEEP YOUR ORIGINAL CONNECTION LINE ---
conn = st.connection("supabase", type="sql", connect_args={"sslmode": "require"})

st.set_page_config(page_title="Pro Cricket Scorer", layout="wide")
st.title("🏏 Pro Cricket Scoring System")

# --- HELPERS ---
def get_teams():
    try:
        with conn.session as s:
            return [r[0] for r in s.execute(text("SELECT name FROM teams")).fetchall()]
    except Exception:
        return []

def upgrade_to_pro_state(state, striker, non_striker, bowler):
    """Ensure canonical pro structure exists and initialize missing players/bowler."""
    if state is None:
        state = {
            "runs": 0,
            "wickets": 0,
            "balls": 0,            # legal balls
            "batting": {},         # name -> {runs, balls, 4s, 6s}
            "bowling": {},         # name -> {runs, balls, wickets, wd, nb}
            "extras": {"wd": 0, "nb": 0, "bye": 0, "lb": 0}
        }

    for p in (striker, non_striker):
        if p and p not in state["batting"]:
            state["batting"][p] = {"runs": 0, "balls": 0, "4s": 0, "6s": 0}

    if bowler and bowler not in state["bowling"]:
        state["bowling"][bowler] = {"runs": 0, "balls": 0, "wickets": 0, "wd": 0, "nb": 0}

    return state

def process_ball(state, action, striker, bowler):
    """
    action: {'type': 'run'|'wkt'|'wd'|'nb'|'bye'|'lb', 'val': int}
    Returns updated state.
    """
    t = action.get("type")
    v = int(action.get("val", 0))
    state = upgrade_to_pro_state(state, striker, None, bowler)

    if t == "run":
        # legal delivery
        state["runs"] += v
        state["balls"] += 1
        state["batting"][striker]["runs"] += v
        state["batting"][striker]["balls"] += 1
        if v == 4: state["batting"][striker]["4s"] += 1
        if v == 6: state["batting"][striker]["6s"] += 1
        state["bowling"][bowler]["runs"] += v
        state["bowling"][bowler]["balls"] += 1

    elif t == "wkt":
        # wicket on legal ball
        state["wickets"] += 1
        state["balls"] += 1
        state["bowling"][bowler]["wickets"] += 1
        state["bowling"][bowler]["balls"] += 1

    elif t == "wd":
        # wide: extra(s), not a legal ball
        state["runs"] += v
        state["extras"]["wd"] += v
        state["bowling"][bowler]["wd"] += v
        state["bowling"][bowler]["runs"] += v

    elif t == "nb":
        # no-ball: extra(s), not a legal ball (free-hit logic not included)
        state["runs"] += v
        state["extras"]["nb"] += v
        state["bowling"][bowler]["nb"] += v
        state["bowling"][bowler]["runs"] += v

    elif t in ("bye", "lb"):
        # byes/leg-byes: extras, legal ball
        state["runs"] += v
        state["extras"][t] += v
        state["balls"] += 1
        state["bowling"][bowler]["runs"] += v
        state["bowling"][bowler]["balls"] += 1

    return state

def save_state_to_db(match_id, state):
    with conn.session as s:
        s.execute(text("UPDATE matches SET score_state = :ss WHERE id = :id"),
                  {"ss": json.dumps(state), "id": match_id})
        s.commit()

def load_state_from_db(m):
    ss = m.get("score_state")
    if not ss:
        return None
    try:
        return json.loads(ss) if isinstance(ss, str) else ss
    except Exception:
        return None

# --- UI LAYOUT ---
menu = ["Schedule & Rosters", "Live Scoring"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Schedule & Rosters":
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Manage Teams & Players")
        t_name = st.text_input("New Team Name")
        if st.button("Add Team") and t_name.strip():
            with conn.session as s:
                s.execute(text("INSERT INTO teams (name) VALUES (:n)"), {"n": t_name.strip()})
                s.commit()
            st.rerun()

        teams = get_teams()
        sel_t = st.selectbox("Select Team", teams if teams else ["Add a team first"])
        p_name = st.text_input("Player Name")
        if st.button("Add Player") and p_name.strip() and sel_t:
            with conn.session as s:
                s.execute(text("INSERT INTO players (team_name, name) VALUES (:t, :p)"), {"t": sel_t, "p": p_name.strip()})
                s.commit()
            st.rerun()

    with c2:
        st.subheader("Schedule Match")
        teams = get_teams()
        ta = st.selectbox("Team A", teams)
        tb = st.selectbox("Team B", teams)
        if st.button("Schedule Match") and ta and tb and ta != tb:
            with conn.session as s:
                s.execute(text("INSERT INTO matches (team_a, team_b, status) VALUES (:a, :b, 'Scheduled')"), {"a": ta, "b": tb})
                s.commit()
            st.success("Match Scheduled!"); st.rerun()

elif choice == "Live Scoring":
    st.subheader("Live Match Tracker")
    with conn.session as s:
        matches = s.execute(text("SELECT * FROM matches WHERE status != 'Completed'")).mappings().all()

    if not matches:
        st.info("No active matches found.")
    else:
        m = st.selectbox("Select Match", matches, format_func=lambda x: f"{x['team_a']} vs {x['team_b']} ({x['status']})")

        # --- SCHEDULED: Toss ---
        if m["status"] == "Scheduled":
            with st.form("toss_form"):
                overs = st.number_input("Total Overs", 1, 50, 20)
                tw = st.radio("Toss Winner", [m["team_a"], m["team_b"]])
                td = st.radio("Decision", ["Bat", "Bowl"])
                if st.form_submit_button("Start Match"):
                    with conn.session as s:
                        s.execute(text("UPDATE matches SET total_overs=:o, toss_winner=:tw, toss_decision=:td, status='Lineup' WHERE id=:id"),
                                  {"o": overs, "tw": tw, "td": td, "id": m["id"]})
                        s.commit()
                    st.rerun()

        # --- LINEUP ---
        elif m["status"] == "Lineup":
            if m.get("toss_decision") == "Bat":
                batting_team = m["toss_winner"]
                bowling_team = m["team_a"] if m["toss_winner"] == m["team_b"] else m["team_b"]
            else:
                bowling_team = m["toss_winner"]
                batting_team = m["team_a"] if m["toss_winner"] == m["team_b"] else m["team_b"]

            with conn.session as s:
                batting_players = s.execute(text("SELECT name FROM players WHERE team_name = :t"), {"t": batting_team}).fetchall()
                bowling_players = s.execute(text("SELECT name FROM players WHERE team_name = :t"), {"t": bowling_team}).fetchall()

            bat_list = [p[0] for p in batting_players]
            bowl_list = [p[0] for p in bowling_players]

            s1 = st.selectbox("Striker", bat_list)
            s2 = st.selectbox("Non-Striker", [p for p in bat_list if p != s1])
            b = st.selectbox("Bowler", bowl_list)

            if st.button("Start Ball-by-Ball"):
                initial_state = {"runs": 0, "wickets": 0, "balls": 0, "batting": {}, "bowling": {}, "extras": {"wd":0,"nb":0,"bye":0,"lb":0}}
                initial_state = upgrade_to_pro_state(initial_state, s1, s2, b)
                with conn.session as s:
                    s.execute(text("""
                        UPDATE matches 
                        SET striker_id=:s1, non_striker_id=:s2, bowler_id=:b, status='Live', 
                            batting_team=:bt, bowling_team=:bowlt, score_state=:ss 
                        WHERE id=:id
                    """), {"s1": s1, "s2": s2, "b": b, "bt": batting_team, "bowlt": bowling_team, "ss": json.dumps(initial_state), "id": m["id"]})
                    s.commit()
                st.rerun()

        # --- LIVE ---
        elif m["status"] == "Live":
            # initialize session state for this match
            if "live_match_id" not in st.session_state or st.session_state["live_match_id"] != m["id"]:
                st.session_state["live_match_id"] = m["id"]
                st.session_state["state"] = load_state_from_db(m) or {}
                st.session_state["striker"] = m.get("striker_id")
                st.session_state["non_striker"] = m.get("non_striker_id")
                st.session_state["bowler"] = m.get("bowler_id")

            state = upgrade_to_pro_state(st.session_state.get("state"), st.session_state["striker"], st.session_state["non_striker"], st.session_state["bowler"])

            # Dashboard
            overs = state["balls"] // 6
            balls_in_over = state["balls"] % 6
            st.metric("Score", f"{state['runs']}/{state['wickets']}", f"Overs: {overs}.{balls_in_over}")

            # Action grid
            st.write("### Scoring Actions")
            cols = st.columns(6)
            for i, val in enumerate([1,2,3,4,5,6]):
                if cols[i].button(str(val)):
                    state = process_ball(state, {"type":"run","val":val}, st.session_state["striker"], st.session_state["bowler"])
                    # rotate strike on odd runs
                    if val % 2 == 1:
                        st.session_state["striker"], st.session_state["non_striker"] = st.session_state["non_striker"], st.session_state["striker"]
                    st.session_state["state"] = state
                    save_state_to_db(m["id"], state)
                    st.rerun()

            cols2 = st.columns(4)
            if cols2[0].button("Wide"):
                state = process_ball(state, {"type":"wd","val":1}, st.session_state["striker"], st.session_state["bowler"])
                st.session_state["state"] = state
                save_state_to_db(m["id"], state)
                st.rerun()

            if cols2[1].button("Wicket"):
                # show a small inline flow to confirm new batter
                nb = st.text_input("New batter name (enter then click Confirm Wicket)", key=f"nb_{m['id']}")
                if st.button("Confirm Wicket"):
                    state = process_ball(state, {"type":"wkt","val":0}, st.session_state["striker"], st.session_state["bowler"])
                    if nb and nb.strip():
                        state = upgrade_to_pro_state(state, nb.strip(), st.session_state["non_striker"], st.session_state["bowler"])
                        st.session_state["striker"] = nb.strip()
                    st.session_state["state"] = state
                    save_state_to_db(m["id"], state)
                    st.rerun()

            if cols2[2].button("Swap Strike"):
                st.session_state["striker"], st.session_state["non_striker"] = st.session_state["non_striker"], st.session_state["striker"]
                with conn.session as s:
                    s.execute(text("UPDATE matches SET striker_id=:s1, non_striker_id=:s2 WHERE id=:id"),
                              {"s1": st.session_state["striker"], "s2": st.session_state["non_striker"], "id": m["id"]})
                    s.commit()
                st.rerun()

            if cols2[3].button("End Over"):
                # rotate strike at over end
                st.session_state["striker"], st.session_state["non_striker"] = st.session_state["non_striker"], st.session_state["striker"]
                with conn.session as s:
                    s.execute(text("UPDATE matches SET striker_id=:s1, non_striker_id=:s2 WHERE id=:id"),
                              {"s1": st.session_state["striker"], "s2": st.session_state["non_striker"], "id": m["id"]})
                    s.commit()
                st.rerun()

            # Scorecards
            st.write("### Batting Scorecard")
            bat_df = pd.DataFrame.from_dict(state["batting"], orient="index").rename_axis("Name").reset_index()
            if not bat_df.empty:
                bat_df["SR"] = (bat_df["runs"] / bat_df["balls"] * 100).fillna(0).round(2)
            st.dataframe(bat_df)

            st.write("### Bowling Scorecard")
            bowl_df = pd.DataFrame.from_dict(state["bowling"], orient="index").rename_axis("Name").reset_index()
            if not bowl_df.empty:
                bowl_df["Overs"] = (bowl_df["balls"] // 6).astype(int).astype(str) + "." + (bowl_df["balls"] % 6).astype(str)
                bowl_df["Econ"] = (bowl_df["runs"] / (bowl_df["balls"] / 6)).replace([float("inf"), float("nan")], 0).round(2)
            st.dataframe(bowl_df)

            # persist session state
            st.session_state["state"] = state
