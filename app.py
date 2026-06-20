import streamlit as st
import json
from sqlalchemy import text
import pandas as pd
from copy import deepcopy

# -------------------------
# CONFIGURATION / CONNECTION
# -------------------------
# Keep your original connection line here
conn = st.connection("supabase", type="sql", connect_args={"sslmode": "require"})

st.set_page_config(page_title="Pro Cricket Scorer", layout="wide")
st.title("🏏 Pro Cricket Scoring System (Full)")

# -------------------------
# HELPERS
# -------------------------
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
            "extras": {"wd": 0, "nb": 0, "bye": 0, "lb": 0},
            "history": [],         # stack of previous states for undo
            "free_hit": False,     # free-hit active for next legal delivery
            "need_new_bowler": False
        }

    for p in (striker, non_striker):
        if p and p not in state["batting"]:
            state["batting"][p] = {"runs": 0, "balls": 0, "4s": 0, "6s": 0}

    if bowler and bowler not in state["bowling"]:
        state["bowling"][bowler] = {"runs": 0, "balls": 0, "wickets": 0, "wd": 0, "nb": 0}

    if "history" not in state:
        state["history"] = []
    if "free_hit" not in state:
        state["free_hit"] = False
    if "need_new_bowler" not in state:
        state["need_new_bowler"] = False

    return state


def push_history(state):
    # store a deep copy of the state for undo (limit history length)
    h = deepcopy(state)
    h.pop("history", None)
    state["history"].append(h)
    if len(state["history"]) > 50:
        state["history"].pop(0)
    return state


def pop_history(state):
    if state.get("history"):
        prev = state["history"].pop()
        prev["history"] = state.get("history", [])
        return prev
    return state


def process_ball(state, action, striker, bowler):
    """
    action: {'type': 'run'|'wkt'|'wd'|'nb'|'bye'|'lb'|'runout', 'val': int, 'out_player': optional, 'new_batter': optional}
    Returns updated state.
    """
    t = action.get("type")
    v = int(action.get("val", 0))
    state = upgrade_to_pro_state(state, striker, None, bowler)

    # Save snapshot for undo BEFORE applying this ball
    state = push_history(state)

    def legal_ball():
        state["balls"] += 1
        state["bowling"][bowler]["balls"] += 1

    free_hit = state.get("free_hit", False)

    if t == "run":
        state["runs"] += v
        legal_ball()
        state["batting"][striker]["runs"] += v
        state["batting"][striker]["balls"] += 1
        if v == 4:
            state["batting"][striker]["4s"] += 1
        if v == 6:
            state["batting"][striker]["6s"] += 1
        state["bowling"][bowler]["runs"] += v
        if v % 2 == 1:
            # rotate strike on odd runs
            st.session_state["striker"], st.session_state["non_striker"] = (
                st.session_state["non_striker"],
                st.session_state["striker"],
            )
        if free_hit:
            state["free_hit"] = False

    elif t == "wkt":
        if free_hit:
            # legal ball but wicket ignored (except run-out)
            legal_ball()
            state["bowling"][bowler]["runs"] += 0
            state["free_hit"] = False
        else:
            state["wickets"] += 1
            legal_ball()
            state["bowling"][bowler]["wickets"] += 1
            state["bowling"][bowler]["runs"] += 0

    elif t == "runout":
        legal_ball()
        state["runs"] += v
        state["bowling"][bowler]["runs"] += v
        # credit runs to striker for simplicity
        state["batting"][striker]["runs"] += v
        state["batting"][striker]["balls"] += 1
        if v == 4:
            state["batting"][striker]["4s"] += 1
        if v == 6:
            state["batting"][striker]["6s"] += 1
        state["wickets"] += 1
        state["bowling"][bowler]["wickets"] += 1

    elif t == "wd":
        state["runs"] += v
        state["extras"]["wd"] += v
        state["bowling"][bowler]["wd"] += v
        state["bowling"][bowler]["runs"] += v

    elif t == "nb":
        state["runs"] += v
        state["extras"]["nb"] += v
        state["bowling"][bowler]["nb"] += v
        state["bowling"][bowler]["runs"] += v
        state["free_hit"] = True

    elif t in ("bye", "lb"):
        state["runs"] += v
        state["extras"][t] += v
        legal_ball()
        state["bowling"][bowler]["runs"] += v

    # Over-end check: if legal balls %6 == 0 -> over ended
    if state["balls"] > 0 and state["balls"] % 6 == 0:
        state["need_new_bowler"] = True
        # rotate strike at over end
        st.session_state["striker"], st.session_state["non_striker"] = (
            st.session_state["non_striker"],
            st.session_state["striker"],
        )
    else:
        state["need_new_bowler"] = False

    return state


def save_state_to_db(match_id, state, m_updates=None):
    payload = {"ss": json.dumps(state), "id": match_id}
    set_clauses = ["score_state = :ss"]
    if m_updates:
        for k in m_updates.keys():
            set_clauses.append(f"{k} = :{k}")
            payload[k] = m_updates[k]
    set_sql = ", ".join(set_clauses)
    with conn.session as s:
        s.execute(text(f"UPDATE matches SET {set_sql} WHERE id = :id"), payload)
        s.commit()


def load_state_from_db(m):
    ss = m.get("score_state")
    if not ss:
        return None
    try:
        return json.loads(ss) if isinstance(ss, str) else ss
    except Exception:
        return None


def finish_innings(m, state):
    innings = m.get("innings_number") or 1
    if innings == 1:
    # compute target and prepare new empty state for next innings
        target = int(state["runs"]) + 1
        new_state = {
            "runs": 0,
            "wickets": 0,
            "balls": 0,
            "batting": {},
            "bowling": {},
            "extras": {"wd": 0, "nb": 0, "bye": 0, "lb": 0},
            "history": [],
            "free_hit": False,
            "need_new_bowler": False,
        }

        batting_team = m.get("bowling_team")
        bowling_team = m.get("batting_team")

        sql = """
            UPDATE matches
            SET innings_number = :innings,
                target = :target,
                batting_team = :bt,
                bowling_team = :bowlt,
                striker_id = NULL,
                non_striker_id = NULL,
                bowler_id = NULL,
                score_state = :ss
            WHERE id = :id
        """
        params = {
            "innings": 2,
            "target": target,
            "bt": batting_team,
            "bowlt": bowling_team,
            "ss": json.dumps(new_state),
            "id": m["id"],
        }

        try:
            with conn.session as s:
                s.execute(text(sql), params)
                s.commit()
        except Exception as e:
        # temporary debug output while you verify the fix
            st.error("Error finishing innings: " + str(e))
            st.write("SQL:", sql)
            st.write("Params:", params)
            raise

        return {"next_phase": "second_innings", "target": target}

    else:
        target = m.get("target", 0)
        if state["runs"] >= target:
            winner = m.get("batting_team")
        else:
            winner = m.get("bowling_team")
        try:
            with conn.session as s:
                s.execute(
                    text("UPDATE matches SET status='Completed', winner=:w WHERE id=:id"),
                    {"w": winner, "id": m["id"]},
                )
                s.commit()
        except Exception as e:
            st.error("Error completing match: " + str(e))
            raise
        return {"next_phase": "match_completed", "winner": winner}


# -------------------------
# UI LAYOUT
# -------------------------
menu = ["Schedule & Rosters", "Live Scoring"]
choice = st.sidebar.selectbox("Menu", menu)

# -------------------------
# SCHEDULE & ROSTERS
# -------------------------
if choice == "Schedule & Rosters":
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Manage Teams & Players")
        t_name = st.text_input("New Team Name")
        if st.button("Add Team") and t_name.strip():
            with conn.session as s:
                s.execute(text("INSERT INTO teams (name) VALUES (:n)"), {"n": t_name.strip()})
                s.commit()
            st.experimental_rerun()

        teams = get_teams()
        sel_t = st.selectbox("Select Team", teams if teams else ["Add a team first"])
        p_name = st.text_input("Player Name")
        if st.button("Add Player") and p_name.strip() and sel_t:
            with conn.session as s:
                s.execute(
                    text("INSERT INTO players (team_name, name) VALUES (:t, :p)"),
                    {"t": sel_t, "p": p_name.strip()},
                )
                s.commit()
            st.experimental_rerun()

    with c2:
        st.subheader("Schedule Match")
        teams = get_teams()
        ta = st.selectbox("Team A", teams)
        tb = st.selectbox("Team B", teams)
        if st.button("Schedule Match") and ta and tb and ta != tb:
            sql = "INSERT INTO matches (team_a, team_b, status, innings_number) VALUES (:a, :b, 'Scheduled', 1)"
            params = {"a": ta, "b": tb}
            try:
                with conn.session as s:
                    s.execute(text(sql), params)
                    s.commit()
                st.success("Match Scheduled!")
        # Safe rerun: only call if available, otherwise fall back to a harmless session_state toggle
                if hasattr(st, "experimental_rerun"):
                    try:
                        st.experimental_rerun()
                    except Exception:
                # If it still fails for some reason, fall back to a soft refresh
                        st.session_state["_refresh_flag"] = not st.session_state.get("_refresh_flag", False)
                else:
            # Soft refresh fallback for environments without experimental_rerun
                    st.session_state["_refresh_flag"] = not st.session_state.get("_refresh_flag", False)
            except Exception as e:
                st.error("Scheduling failed: " + str(e))
                st.write("SQL:", sql)
                st.write("Params:", params)
                import traceback
                st.text(traceback.format_exc())



# -------------------------
# LIVE SCORING
# -------------------------
elif choice == "Live Scoring":
    st.subheader("Live Match Tracker")
    with conn.session as s:
        matches = s.execute(text("SELECT * FROM matches WHERE status != 'Completed'")).mappings().all()

    if not matches:
        st.info("No active matches found.")
    else:
        m = st.selectbox(
            "Select Match",
            matches,
            format_func=lambda x: f"{x['team_a']} vs {x['team_b']} (Innings {x.get('innings_number',1)} - {x['status']})",
        )

        # --- SCHEDULED: Toss ---
        if m["status"] == "Scheduled":
            with st.form("toss_form"):
                overs = st.number_input("Total Overs", 1, 50, 20)
                tw = st.radio("Toss Winner", [m["team_a"], m["team_b"]])
                td = st.radio("Decision", ["Bat", "Bowl"])
                if st.form_submit_button("Start Match"):
                    if td == "Bat":
                        batting_team = tw
                        bowling_team = m["team_a"] if tw == m["team_b"] else m["team_b"]
                    else:
                        bowling_team = tw
                        batting_team = m["team_a"] if tw == m["team_b"] else m["team_b"]

                sql = """
                    UPDATE matches
                    SET total_overs = :o,
                        toss_winner = :tw,
                        toss_decision = :td,
                        status = 'Lineup',
                        batting_team = :bt,
                        bowling_team = :bowlt
                    WHERE id = :id
                """
                params = {"o": overs, "tw": tw, "td": td, "bt": batting_team, "bowlt": bowling_team, "id": m["id"]}

                try:
                    with conn.session as s:
                        s.execute(text(sql), params)
                        s.commit()
                    st.success("Match prepared — go to Lineup")

        # Safe rerun: call experimental_rerun only if available; otherwise toggle a session flag
                    if hasattr(st, "experimental_rerun"):
                        try:
                            st.experimental_rerun()
                        except Exception:
                            st.session_state["_refresh_flag"] = not st.session_state.get("_refresh_flag", False)
                    else:
                        st.session_state["_refresh_flag"] = not st.session_state.get("_refresh_flag", False)

                except Exception as e:
                    st.error("Failed to start match: " + str(e))
                    st.write("SQL:", sql)
                    st.write("Params:", params)
                    import traceback
                    st.text(traceback.format_exc())

               

        # --- LINEUP ---
        elif m["status"] == "Lineup":
            batting_team = m.get("batting_team")
            bowling_team = m.get("bowling_team")
            with conn.session as s:
                batting_players = s.execute(text("SELECT name FROM players WHERE team_name = :t"), {"t": batting_team}).fetchall()
                bowling_players = s.execute(text("SELECT name FROM players WHERE team_name = :t"), {"t": bowling_team}).fetchall()

            bat_list = [p[0] for p in batting_players]
            bowl_list = [p[0] for p in bowling_players]

            s1 = st.selectbox("Striker", bat_list)
            s2 = st.selectbox("Non-Striker", [p for p in bat_list if p != s1])
            b = st.selectbox("Bowler", bowl_list)

            if st.button("Start Ball-by-Ball"):
                initial_state = {
                    "runs": 0,
                    "wickets": 0,
                    "balls": 0,
                    "batting": {},
                    "bowling": {},
                    "extras": {"wd": 0, "nb": 0, "bye": 0, "lb": 0},
                    "history": [],
                    "free_hit": False,
                    "need_new_bowler": False,
                }
                initial_state = upgrade_to_pro_state(initial_state, s1, s2, b)
                with conn.session as s:
                    s.execute(
                        text(
                            """
                        UPDATE matches 
                        SET striker_id=:s1, non_striker_id=:s2, bowler_id=:b, status='Live', 
                            batting_team=:bt, bowling_team=:bowlt, score_state=:ss, innings_number=1
                        WHERE id=:id
                    """
                        ),
                        {"s1": s1, "s2": s2, "b": b, "bt": batting_team, "bowlt": bowling_team, "ss": json.dumps(initial_state), "id": m["id"]},
                    )
                    s.commit()
                st.experimental_rerun()

        # --- LIVE ---
        elif m["status"] == "Live":
            # initialize session state for this match
            if "live_match_id" not in st.session_state or st.session_state["live_match_id"] != m["id"]:
                st.session_state["live_match_id"] = m["id"]
                st.session_state["state"] = load_state_from_db(m) or {}
                st.session_state["striker"] = m.get("striker_id")
                st.session_state["non_striker"] = m.get("non_striker_id")
                st.session_state["bowler"] = m.get("bowler_id")
                st.session_state["target"] = m.get("target")
                st.session_state["total_overs"] = m.get("total_overs") or 0
                st.session_state["innings_number"] = m.get("innings_number") or 1

            state = upgrade_to_pro_state(
                st.session_state.get("state"),
                st.session_state["striker"],
                st.session_state["non_striker"],
                st.session_state["bowler"],
            )

            # Dashboard
            overs = state["balls"] // 6
            balls_in_over = state["balls"] % 6
            target = st.session_state.get("target")
            innings_no = st.session_state.get("innings_number", 1)
            subtitle = f"Innings {innings_no}"
            if target:
                subtitle += f" | Target: {target}"
            st.metric("Score", f"{state['runs']}/{state['wickets']}", f"{subtitle} • Overs: {overs}.{balls_in_over}")

            # Action grid
            st.write("### Scoring Actions")
            cols = st.columns(6)
            for i, val in enumerate([1, 2, 3, 4, 5, 6]):
                if cols[i].button(str(val)):
                    state = process_ball(state, {"type": "run", "val": val}, st.session_state["striker"], st.session_state["bowler"])
                    st.session_state["state"] = state
                    save_state_to_db(
                        m["id"],
                        state,
                        {"striker_id": st.session_state["striker"], "non_striker_id": st.session_state["non_striker"], "bowler_id": st.session_state["bowler"]},
                    )
                    st.experimental_rerun()

            cols2 = st.columns(5)
            if cols2[0].button("Wide"):
                state = process_ball(state, {"type": "wd", "val": 1}, st.session_state["striker"], st.session_state["bowler"])
                st.session_state["state"] = state
                save_state_to_db(m["id"], state)
                st.experimental_rerun()

            if cols2[1].button("No-ball"):
                state = process_ball(state, {"type": "nb", "val": 1}, st.session_state["striker"], st.session_state["bowler"])
                st.session_state["state"] = state
                save_state_to_db(m["id"], state)
                st.experimental_rerun()

            # Bye flow: show a small inline confirm
            if cols2[2].button("Bye"):
                val = st.number_input("Bye runs", min_value=0, max_value=6, value=0, key=f"bye_{m['id']}")
                if st.button("Confirm Bye", key=f"confirm_bye_{m['id']}"):
                    state = process_ball(state, {"type": "bye", "val": val}, st.session_state["striker"], st.session_state["bowler"])
                    st.session_state["state"] = state
                    save_state_to_db(m["id"], state)
                    st.experimental_rerun()

            # Wicket flow: show remaining batters dropdown when confirming wicket
            if cols2[3].button("Wicket"):
                # Fetch full batting squad for batting_team
                with conn.session as s:
                    all_bat_players = [r[0] for r in s.execute(text("SELECT name FROM players WHERE team_name = :t"), {"t": m.get("batting_team")}).fetchall()]

                already_used = set(state["batting"].keys())
                remaining_batters = [p for p in all_bat_players if p not in already_used]

                st.write("### Wicket — Select replacement batter")
                if not remaining_batters:
                    st.warning("No remaining batters available in squad. This will end the innings if 10 wickets are down.")
                    # allow confirming wicket without replacement
                    if st.button("Confirm Wicket (No Replacement)"):
                        state = process_ball(state, {"type": "wkt", "val": 0}, st.session_state["striker"], st.session_state["bowler"])
                        st.session_state["state"] = state
                        save_state_to_db(m["id"], state)
                        st.experimental_rerun()
                else:
                    next_batter = st.selectbox("Next Batter", remaining_batters, key=f"next_batter_{m['id']}")
                    if st.button("Confirm Wicket and Add Batter"):
                        state = process_ball(state, {"type": "wkt", "val": 0}, st.session_state["striker"], st.session_state["bowler"])
                        # initialize new batter and set as striker (assuming striker was out)
                        state = upgrade_to_pro_state(state, next_batter, st.session_state["non_striker"], st.session_state["bowler"])
                        st.session_state["striker"] = next_batter
                        st.session_state["state"] = state
                        save_state_to_db(m["id"], state, {"striker_id": st.session_state["striker"], "non_striker_id": st.session_state["non_striker"]})
                        st.experimental_rerun()

            # Undo
            if cols2[4].button("Undo Last Ball"):
                state = pop_history(state)
                st.session_state["state"] = state
                save_state_to_db(m["id"], state, {"striker_id": st.session_state["striker"], "non_striker_id": st.session_state["non_striker"], "bowler_id": st.session_state["bowler"]})
                st.experimental_rerun()

            # If over ended automatically, prompt for new bowler
            if state.get("need_new_bowler"):
                st.info("Over completed. Please select new bowler for next over.")
                with st.form("change_bowler_form"):
                    with conn.session as s:
                        bowl_players = s.execute(text("SELECT name FROM players WHERE team_name = :t"), {"t": m.get("bowling_team")}).fetchall()
                    bowl_list = [p[0] for p in bowl_players]
                    last_bowler = st.session_state.get("bowler")
                    available_bowlers = [p for p in bowl_list if p != last_bowler]
                    if not available_bowlers:
                        st.warning("No other bowlers available; you may reselect the same bowler.")
                        available_bowlers = bowl_list
                    new_bowler = st.selectbox("New Bowler", available_bowlers, key=f"new_bowler_{m['id']}")
                    if st.form_submit_button("Confirm New Bowler"):
                        st.session_state["bowler"] = new_bowler
                        state["need_new_bowler"] = False
                        st.session_state["state"] = state
                        save_state_to_db(m["id"], state, {"bowler_id": st.session_state["bowler"], "striker_id": st.session_state["striker"], "non_striker_id": st.session_state["non_striker"]})
                        st.experimental_rerun()

            # Manual Swap / Force End Over
            col_a, col_b = st.columns(2)
            if col_a.button("Swap Strike"):
                st.session_state["striker"], st.session_state["non_striker"] = st.session_state["non_striker"], st.session_state["striker"]
                save_state_to_db(m["id"], state, {"striker_id": st.session_state["striker"], "non_striker_id": st.session_state["non_striker"]})
                st.experimental_rerun()

            if col_b.button("End Over (force)"):
                st.session_state["striker"], st.session_state["non_striker"] = st.session_state["non_striker"], st.session_state["striker"]
                state["need_new_bowler"] = True
                st.session_state["state"] = state
                save_state_to_db(m["id"], state, {"striker_id": st.session_state["striker"], "non_striker_id": st.session_state["non_striker"]})
                st.experimental_rerun()

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

            # Persist session state
            st.session_state["state"] = state

            # Check innings end conditions: overs completed or 10 wickets or chase reached
            total_overs = st.session_state.get("total_overs", 0)
            legal_balls = state["balls"]
            overs_completed = legal_balls // 6
            wickets = state["wickets"]
            target = st.session_state.get("target")
            innings_no = st.session_state.get("innings_number", 1)

            innings_end = False
            if total_overs and overs_completed >= total_overs:
                innings_end = True
            if wickets >= 10:
                innings_end = True
            if innings_no == 2 and target and state["runs"] >= target:
                innings_end = True

            if innings_end:
                result = finish_innings(m, state)
                if result["next_phase"] == "second_innings":
                    st.success(f"Innings 1 complete. Target set to {result['target']}. Please set lineup for chasing team.")
                    st.experimental_rerun()
                elif result["next_phase"] == "match_completed":
                    st.success(f"Match completed. Winner: {result['winner']}")
                    st.experimental_rerun()
