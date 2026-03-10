import streamlit as st
import pandas as pd
from sqlalchemy import text
from database_utils import engine, init_db, check_password, hash_password, get_malaysia_time, delete_item
from form_components import render_evaluation_fields
from admin_logic import render_dashboard, render_management
from reviewer_logic import render_review_form, render_submissions
# --- NEW IMPORT ---
from reporting_logic import render_reporting 

init_db()
st.set_page_config(page_title="RBS Grant System", layout="wide")
if 'authenticated' not in st.session_state: st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 RBS Login")
    with st.form("login"):
        u, p = st.text_input("Username"), st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            with engine.connect() as conn:
                query = text("SELECT password_hash, 'Admin' as role, full_name FROM users WHERE username = :u UNION SELECT password_hash, 'Reviewer' as role, full_name FROM reviewers WHERE username = :u")
                res = conn.execute(query, {"u": u}).fetchone()
                if res and check_password(p, res[0]):
                    st.session_state.update({"authenticated": True, "username": u, "role": res[1], "full_name": res[2]})
                    st.rerun()
                else: st.error("Invalid credentials")
    st.stop()

with st.sidebar:
    st.title(f"👤 {st.session_state.full_name}")
    # ADDED "Reporting" to opts
    opts = ["Dashboard", "Reporting", "User Management", "Reviewer Management", "Applicant Management"] if st.session_state.role == "Admin" else ["Review Form", "My Submissions"]
    menu = st.radio("Navigation", opts)
    if st.button("Logout", use_container_width=True):
        st.session_state.clear(); st.rerun()

# --- MODULE ROUTING ---
if menu == "Dashboard":
    render_dashboard(engine)
elif menu == "Reporting": # --- NEW ROUTE ---
    render_reporting(engine)
elif menu in ["User Management", "Reviewer Management", "Applicant Management"]:
    render_management(menu, engine, hash_password, delete_item)
elif menu == "Review Form":
    render_review_form(engine, get_malaysia_time, render_evaluation_fields)
elif menu == "My Submissions":
    render_submissions(engine)
