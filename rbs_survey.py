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

# 1. Inisialisasi Database
init_db()

# 2. Konfigurasi Halaman
st.set_page_config(page_title="RBS Grant System", layout="wide")

# --- 3. COOKIE MANAGER SETUP (STABLE VERSION) ---
# Kita simpan manager dalam session_state supaya ia dibina SEKALI SAHAJA setiap sesi
if 'cookie_manager' not in st.session_state:
    st.session_state.cookie_manager = stx.CookieManager(key="rbs_cookie_manager_v1")

cookie_manager = st.session_state.cookie_manager

# Initialize authentication status
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

# --- 4. AUTO-LOGIN LOGIC (READ FROM COOKIES) ---
# Jika session state False (baru buka/refresh), cuba ambil data dari kuki
if not st.session_state.authenticated:
    saved_user = cookie_manager.get('rbs_user')
    saved_role = cookie_manager.get('rbs_role')
    saved_name = cookie_manager.get('rbs_name')
    
    # Jika kuki wujud, automatik login semula
    if saved_user and saved_role and saved_name:
        st.session_state.update({
            "authenticated": True,
            "username": saved_user,
            "role": saved_role,
            "full_name": saved_name
        })

# --- 5. LOGIN INTERFACE ---
if not st.session_state.authenticated:
    st.title("🔐 RBS Login")
    with st.form("login_form"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Login", use_container_width=True):
            with engine.connect() as conn:
                # Semak kredential dalam table users (Admin) dan reviewers (Reviewer)
                query = text("""
                    SELECT password_hash, 'Admin' as role, full_name FROM users WHERE username = :u 
                    UNION 
                    SELECT password_hash, 'Reviewer' as role, full_name FROM reviewers WHERE username = :u
                """)
                res = conn.execute(query, {"u": u}).fetchone()
                
                if res and check_password(p, res[0]):
                    # A. Simpan dalam Session State (Memori semasa)
                    st.session_state.update({
                        "authenticated": True, 
                        "username": u, 
                        "role": res[1], 
                        "full_name": res[2]
                    })
                    
                    # B. Simpan dalam Browser Cookies (Tahan selama 1 hari)
                    # Ini yang menghalang logout bila refresh
                    expiry = datetime.now() + timedelta(days=1)
                    cookie_manager.set('rbs_user', u, expires_at=expiry)
                    cookie_manager.set('rbs_role', res[1], expires_at=expiry)
                    cookie_manager.set('rbs_name', res[2], expires_at=expiry)
                    
                    st.success("Login successful! Redirecting...")
                    st.rerun()
                else:
                    st.error("Invalid credentials. Please check your username or password.")
    st.stop()

# --- 6. SIDEBAR & NAVIGATION (Bila dah Login) ---
with st.sidebar:
    st.title(f"👤 {st.session_state.full_name}")
    st.caption(f"Logged in as: {st.session_state.role}")
    
    # Menu Navigasi
    if st.session_state.role == "Admin":
        opts = ["Dashboard", "Reporting", "User Management", "Reviewer Management", "Applicant Management"]
        menu = st.radio("Navigation", opts)
    else:
        # Reviewer terus ke borang tanpa menu lain
        menu = "Review Form"
    
    st.divider()
    
    # Butang Logout (Mesti buang Session DAN Kuki)
    if st.button("Logout", use_container_width=True, type="primary"):
        cookie_manager.delete('rbs_user')
        cookie_manager.delete('rbs_role')
        cookie_manager.delete('rbs_name')
        st.session_state.clear()
        st.rerun()

# --- 7. MODULE ROUTING ---
if menu == "Dashboard":
    render_dashboard(engine)
elif menu == "Reporting": 
    render_reporting(engine)
elif menu in ["User Management", "Reviewer Management", "Applicant Management"]:
    render_management(menu, engine, hash_password, delete_item)
elif menu == "Review Form":
    render_review_form(engine, get_malaysia_time, render_evaluation_fields)
