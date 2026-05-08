import streamlit as st
import extra_streamlit_components as stx
import pandas as pd
import json
import time
from sqlalchemy import text
from datetime import datetime, timedelta

from database_utils import engine, init_db, check_password, hash_password, get_malaysia_time, delete_item
from admin_logic import render_dashboard, render_management
from reviewer_logic import render_review_form
from reporting_logic import render_reporting

# Pastikan kedua-dua form diimport di sini
from form_components import render_evaluation_fields, render_scoring_fields

# --- 1. INISIALISASI DATABASE ---
init_db()

st.set_page_config(page_title="RBS Grant System", layout="wide")

# --- 2. COOKIE MANAGER SETUP ---
if 'cookie_manager' not in st.session_state:
    st.session_state.cookie_manager = stx.CookieManager(key="rbs_mgr")

cookie_manager = st.session_state.cookie_manager

# --- 3. PROSES ARAHAN KUKI YANG TERTUNGGAK (PENDING QUEUE) ---
# Teknik ini dijamin 100% berjaya kerana ia dijalankan pada permulaan kitaran render
if st.session_state.get('pending_login_cookie'):
    cookie_manager.set('rbs_session_data', st.session_state.pending_login_cookie, expires_at=datetime.now() + timedelta(days=1))
    del st.session_state['pending_login_cookie']

if st.session_state.get('pending_logout'):
    try:
        # Cuba padam kuki
        cookie_manager.delete('rbs_session_data')
    except KeyError:
        # Jika kuki sudah tiada, abaikan ralat ini (jangan crash)
        pass 
    del st.session_state['pending_logout']

# --- 4. INIT AUTH STATE ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

# --- 5. AUTO LOGIN DARI KUKI ---
if not st.session_state.authenticated:
    # Abaikan bacaan kuki jika pengguna baru sahaja tekan Logout
    if st.session_state.get('just_logged_out_flag'):
        st.session_state.just_logged_out_flag = False
    else:
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

# --- 6. LOGIN INTERFACE ---
if not st.session_state.authenticated:
    st.title("🔐 RBS Login")
    with st.form("login_form"):
        login_role = st.radio("Log in as:", ["Reviewer", "Admin"], horizontal=True)
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")

        if st.form_submit_button("Login", use_container_width=True):
            with engine.connect() as conn:
                # Asingkan jadual carian
                if login_role == "Admin":
                    query = text("SELECT password_hash, 'Admin' as role, full_name FROM users WHERE username = :u")
                else:
                    query = text("SELECT password_hash, 'Reviewer' as role, full_name FROM reviewers WHERE username = :u")

                res = conn.execute(query, {"u": u}).fetchone()

                if res and check_password(p, res[0]):
                    # Kemaskini memori sesi Python
                    st.session_state.update({
                        "authenticated": True,
                        "username": u,
                        "role": res[1],
                        "full_name": res[2]
                    })
                    
                    # Masukkan arahan simpan kuki ke dalam "Pending Queue"
                    st.session_state.pending_login_cookie = json.dumps({
                        "username": u,
                        "role": res[1],
                        "full_name": res[2]
                    })

                    st.success(f"Login successful! Welcome {res[2]}")
                    time.sleep(0.5)
                    st.rerun() # Refresh skrin
                else:
                    st.error("Invalid credentials or wrong role selected.")
    st.stop()

# --- 7. SIDEBAR & LOGOUT ---
with st.sidebar:
    st.title(f"👤 {st.session_state.full_name}")
    st.caption(f"Logged in as: {st.session_state.role}")

    # Kawalan Navigasi yang Ketat
    if st.session_state.role == "Admin":
        # Ditambah Phase 2 Management untuk Admin
        opts = ["Dashboard", "Reporting", "Applicant Management", "Phase 2 Management", "Reviewer Management", "User Management"]
        menu = st.radio("Navigation", opts)
    else:
        # Ditambah pilihan Fasa 1 dan Fasa 2 untuk Reviewer
        opts = ["Phase 1: Shortlisting", "Phase 2: Winner Selection"]
        menu = st.radio("Navigation", opts)

    st.divider()

    # Butang Logout
    if st.button("Logout", use_container_width=True, type="primary"):
        st.session_state.clear()
        
        # Masukkan arahan padam kuki ke dalam "Pending Queue"
        st.session_state.pending_logout = True
        st.session_state.just_logged_out_flag = True # Elak auto-login berlaku secara pantas
        
        st.rerun()

# --- 8. MODULE ROUTING ---
if menu == "Dashboard":
    render_dashboard(engine)
elif menu == "Reporting": 
    render_reporting(engine)
elif menu in ["User Management", "Reviewer Management", "Applicant Management", "Phase 2 Management"]:
    # Semua pengurusan Admin di-route ke sini
    render_management(menu, engine, hash_password, delete_item)
elif menu in ["Phase 1: Shortlisting", "Phase 2: Winner Selection"]:
    # Kenalpasti sama ada penilai sedang menekan Fasa 1 atau Fasa 2
    phase_num = 1 if "Phase 1" in menu else 2
    
    # Hantar 5 parameter yang diperlukan oleh fungsi baru (termasuk phase_num & render_scoring_fields)
    render_review_form(engine, get_malaysia_time, phase_num, render_evaluation_fields, render_scoring_fields)
