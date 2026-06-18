import streamlit as st
from sqlalchemy import text

st.title("Database Connection Tester")

# 1. Test Connection
try:
    conn = st.connection("supabase", type="sql")
    st.write("✅ Connection object created.")
except Exception as e:
    st.error(f"❌ Connection failed: {e}")
    st.stop()

# 2. Try an INSERT
t_name = st.text_input("Enter team name to test")
if st.button("Test Write to Database"):
    try:
        with conn.session as s:
            # Check if this team already exists
            s.execute(text("INSERT INTO teams (name) VALUES (:n)"), {"n": t_name})
            s.commit()
        st.success(f"Successfully added {t_name}!")
    except Exception as e:
        st.error(f"❌ Write failed: {e}")

# 3. Try a READ
if st.button("Test Read from Database"):
    try:
        teams = conn.query("SELECT * FROM teams")
        st.write("Current teams in database:", teams)
    except Exception as e:
        st.error(f"❌ Read failed: {e}")
