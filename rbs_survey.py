import streamlit as st
import extra_streamlit_components as stx
import pandas as pd
from sqlalchemy import text
from datetime import datetime, timedelta
from database_utils import engine, init_db, check_password, hash_password, get_malaysia_time, delete_item
from form_components import render_evaluation_fields
from admin_logic import render_dashboard, render_management
from reviewer_logic import render_review_form
from reporting_logic import render_reporting 

# Inisialisasi Database
init_db()

st.set_page_config(page_title="RBS Grant System", layout="wide")

# --- 1. COOKIE MANAGER SETUP ---
def get_manager():
    return stx.CookieManager()

cookie_manager = get_manager()

# Initialize session state if not exist
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

# --- 2. AUTO-LOGIN LOGIC (READ FROM COOKIES) ---
# Jika session state kosong tetapi kuki ada, pulihkan session
if not st.session_state.authenticated:
    saved_user = cookie_manager.get('rbs_user')
    saved_role = cookie_manager.get('rbs_role')
    saved_name = cookie_manager.get('rbs_name')
    
    if saved_user and saved_role and saved_name:
        st.session_state.update({
            "authenticated": True,
            "username": saved_user,
            "role": saved_role,
            "full_name": saved_name
        })

# --- 3. LOGIN INTERFACE ---
if not st.session_state.authenticated:
    st.title("🔐 RBS Login")
    with st.form("login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            with engine.connect() as conn:
                query = text("""
                    SELECT password_hash, 'Admin' as role, full_name FROM users WHERE username = :u 
                    UNION 
                    SELECT password_hash, 'Reviewer' as role, full_name FROM reviewers WHERE username = :u
                """)
                res = conn.execute(query, {"u": u}).fetchone()
                
                if res and check_password(p, res[0]):
                    # Simpan dalam session state
                    st.session_state.update({
                        "authenticated": True, 
                        "username": u, 
                        "role": res[1], 
                        "full_name": res[2]
                    })
                    
                    # Simpan dalam Cookies (Tahan selama 1 hari)
                    expiry = datetime.now() + timedelta(days=1)
                    cookie_manager.set('rbs_user', u, expires_at=expiry)
                    cookie_manager.set('rbs_role', res[1], expires_at=expiry)
                    cookie_manager.set('rbs_name', res[2], expires_at=expiry)
                    
                    st.success("Login successful!")
                    st.rerun()
                else:
                    st.error("Invalid credentials")
    st.stop()

# --- 4. SIDEBAR & NAVIGATION ---
with st.sidebar:
    st.title(f"👤 {st.session_state.full_name}")
    st.caption(f"Role: {st.session_state.role}")
    
    # Navigation Menu
    if st.session_state.role == "Admin":
        opts = ["Dashboard", "Reporting", "User Management", "Reviewer Management", "Applicant Management"]
        menu = st.radio("Navigation", opts)
    else:
        menu = "Review Form"
    
    st.divider()
    
    # Logout Button (Mesti padam session DAN kuki)
    if st.button("Logout", use_container_width=True, type="primary"):
        cookie_manager.delete('rbs_user')
        cookie_manager.delete('rbs_role')
        cookie_manager.delete('rbs_name')
        st.session_state.clear()
        st.rerun()

# --- 5. MODULE ROUTING ---
if menu == "Dashboard":
    render_dashboard(engine)
elif menu == "Reporting": 
    render_reporting(engine)
elif menu in ["User Management", "Reviewer Management", "Applicant Management"]:
    render_management(menu, engine, hash_password, delete_item)
elif menu == "Review Form":
    render_review_form(engine, get_malaysia_time, render_evaluation_fields)
