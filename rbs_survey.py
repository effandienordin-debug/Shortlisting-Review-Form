import streamlit as st
import extra_streamlit_components as stx
import pandas as pd
import json
import time
from sqlalchemy import text
from datetime import datetime, timedelta
from database_utils import engine, init_db, check_password, hash_password, get_malaysia_time, delete_item
from form_components import render_evaluation_fields
from admin_logic import render_dashboard, render_management
from reviewer_logic import render_review_form
from reporting_logic import render_reporting 

# --- 1. INISIALISASI DATABASE ---
init_db()

# --- 2. KONFIGURASI HALAMAN ---
st.set_page_config(page_title="RBS Grant System", layout="wide")

# --- 3. COOKIE MANAGER SETUP ---
if 'cookie_manager' not in st.session_state:
    st.session_state.cookie_manager = stx.CookieManager(key="rbs_cookie_mgr")

cookie_manager = st.session_state.cookie_manager

# Beri masa komponen kuki dimuatkan selepas refresh
if 'cookie_synced' not in st.session_state:
    st.session_state.cookie_synced = False

if not st.session_state.cookie_synced:
    time.sleep(0.5)
    st.session_state.cookie_synced = True
    st.rerun()

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

# --- 4. AUTO-LOGIN LOGIC ---
if not st.session_state.authenticated:
    session_data = cookie_manager.get('rbs_session_data')
    
    if session_data:
        try:
            if isinstance(session_data, str):
                session_data = json.loads(session_data)
                
            st.session_state.update({
                "authenticated": True,
                "username": session_data.get('username'),
                "role": session_data.get('role'),
                "full_name": session_data.get('full_name')
            })
        except Exception:
            pass 

# --- 5. LOGIN INTERFACE ---
if not st.session_state.authenticated:
    st.title("🔐 RBS Login")
    with st.form("login_form"):
        # TAMBAHAN BARU: Pilihan Peranan (Role)
        login_role = st.radio("Log in as:", ["Reviewer", "Admin"], horizontal=True)
        
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Login", use_container_width=True):
            with engine.connect() as conn:
                # ASINGKAN QUERY BERDASARKAN PILIHAN (Elak konflik username)
                if login_role == "Admin":
                    query = text("SELECT password_hash, 'Admin' as role, full_name FROM users WHERE username = :u")
                else:
                    query = text("SELECT password_hash, 'Reviewer' as role, full_name FROM reviewers WHERE username = :u")
                    
                res = conn.execute(query, {"u": u}).fetchone()
                
                if res and check_password(p, res[0]):
                    st.session_state.update({
                        "authenticated": True, 
                        "username": u, 
                        "role": res[1], 
                        "full_name": res[2]
                    })
                    
                    expiry = datetime.now() + timedelta(days=1)
                    cookie_data = json.dumps({
                        "username": u,
                        "role": res[1],
                        "full_name": res[2]
                    })
                    
                    cookie_manager.set('rbs_session_data', cookie_data, expires_at=expiry, key='set_login_cookie')
                    
                    st.success(f"Login successful! Welcome {res[2]} ({res[1]})")
                    time.sleep(1) 
                    st.rerun()
                else:
                    st.error("Invalid credentials or wrong role selected. Please check your username and password.")
    st.stop()

# --- 6. SIDEBAR & NAVIGATION ---
with st.sidebar:
    st.title(f"👤 {st.session_state.full_name}")
    st.caption(f"Logged in as: {st.session_state.role}")
    
    if st.session_state.role == "Admin":
        opts = ["Dashboard", "Reporting", "User Management", "Reviewer Management", "Applicant Management"]
        menu = st.radio("Navigation", opts)
    else:
        menu = "Review Form"
    
    st.divider()
    
    if st.button("Logout", use_container_width=True, type="primary"):
        # TAMBAHAN BARU: Paksa kuki mati (Expire semalam)
        past_date = datetime.now() - timedelta(days=1)
        cookie_manager.set('rbs_session_data', '', expires_at=past_date, key='force_expire_cookie')
        
        # Bersihkan semua pembolehubah sesi
        for key in list(st.session_state.keys()):
            if key != 'cookie_manager':
                del st.session_state[key]
                
        st.session_state.authenticated = False
        time.sleep(0.5) # Beri masa sikit untuk browser proses tarikh luput
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
