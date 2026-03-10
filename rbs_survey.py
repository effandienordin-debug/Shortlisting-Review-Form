import streamlit as st
import pandas as pd
import bcrypt
import urllib.parse
from sqlalchemy import create_engine, text
import plotly.express as px
import json
from datetime import datetime, timedelta, timezone

# --- 1. Database Configuration ---
DB_URL = st.secrets["DATABASE_URL"]
engine = create_engine(DB_URL)

# --- 2. Helper Functions ---
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def get_malaysia_time():
    my_tz = timezone(timedelta(hours=8))
    return datetime.now(my_tz).strftime('%Y-%m-%d %H:%M:%S')

def get_radio_index(prev_dict, key):
    val = prev_dict.get(key)
    if val == "Yes": return 0
    if val == "No": return 1
    return None

# --- 3. Database Schema Self-Healing ---
with engine.begin() as conn:
    # Existing tables...
    conn.execute(text("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username VARCHAR(255) UNIQUE, full_name VARCHAR(255), email VARCHAR(255), password_hash VARCHAR(255), role VARCHAR(50), profile_pic BYTEA)"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS reviewers (id SERIAL PRIMARY KEY, username VARCHAR(255) UNIQUE, full_name VARCHAR(255), email VARCHAR(255), password_hash VARCHAR(255), profile_pic BYTEA)"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS applicants (id SERIAL PRIMARY KEY, name VARCHAR(255) UNIQUE, proposal_title TEXT, info_link TEXT, photo BYTEA)"))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS reviews (
            id SERIAL PRIMARY KEY,
            reviewer_username VARCHAR(255) REFERENCES reviewers(username) ON UPDATE CASCADE ON DELETE SET NULL,
            applicant_name VARCHAR(255),
            responses TEXT,
            final_recommendation VARCHAR(50),
            overall_justification TEXT,
            submitted_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """))
    # 🚀 UPGRADE: Add 'is_final' column for locking workflow
    conn.execute(text("ALTER TABLE reviews ADD COLUMN IF NOT EXISTS is_final BOOLEAN DEFAULT FALSE"))
    conn.execute(text("ALTER TABLE reviews ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP"))

    # Default Admin
    if conn.execute(text("SELECT COUNT(*) FROM users")).fetchone()[0] == 0:
        conn.execute(text("INSERT INTO users (username, full_name, email, password_hash, role) VALUES ('admin', 'Master Admin', 'admin@system.com', :pw, 'Admin')"), {"pw": hash_password("Admin123!")})

# --- 4. Shared Form Engine (Sections 1 - 5) ---
def render_evaluation_fields(prev_resp=None, prev_data=None, disabled=False):
    """Unified form fields for both Review Form and Edit Dialog"""
    if prev_resp is None: prev_resp = {}
    if prev_data is None: prev_data = {}

    st.subheader("Section 1 — Research Quality and Feasibility")
    q12a = st.radio("a) Are the proposed methods and objectives appropriate and achievable within the grant period (2 years)?", ["Yes", "No"], index=get_radio_index(prev_resp, "12a"), horizontal=True, disabled=disabled)
    q12b = st.radio("b) Does the applicant have relevant expertise and a strong research track record?", ["Yes", "No"], index=get_radio_index(prev_resp, "12b"), horizontal=True, disabled=disabled)
    q12c = st.radio("c) Have potential risks been identified, and are there plans to address them?", ["Yes", "No"], index=get_radio_index(prev_resp, "12c"), horizontal=True, disabled=disabled)
    j13 = st.text_area("Justification (Research Quality)", value=prev_resp.get("13", ""), disabled=disabled)

    st.divider()
    st.subheader("Section 2 — Potential Impact")
    q14a = st.radio("a) Does the research address an important issue in medical science?", ["Yes", "No"], index=get_radio_index(prev_resp, "14a"), horizontal=True, disabled=disabled)
    q14b = st.radio("b) Does it have the potential to contribute to significant advancements in the medical field?", ["Yes", "No"], index=get_radio_index(prev_resp, "14b"), horizontal=True, disabled=disabled)
    j15 = st.text_area("Justification (Potential Impact)", value=prev_resp.get("15", ""), key="j15_field", disabled=disabled)

    st.divider()
    st.subheader("Section 3 — Innovation and Novelty")
    q16a = st.radio("a) Does the research propose a novel approach or methodology?", ["Yes", "No"], index=get_radio_index(prev_resp, "16a"), horizontal=True, disabled=disabled)
    j17 = st.text_area("Justification (Innovation)", value=prev_resp.get("17", ""), key="j17_field", disabled=disabled)

    st.divider()
    st.subheader("Section 4 — Value for Money")
    q18a = st.radio("a) Are the requested funds essential and appropriately allocated based on the importance of the research?", ["Yes", "No"], index=get_radio_index(prev_resp, "18a"), horizontal=True, disabled=disabled)
    j19 = st.text_area("Justification (Value for Money)", value=prev_resp.get("19", ""), key="j19_field", disabled=disabled)

    st.divider()
    st.subheader("Section 5 — Final Recommendation")
    fr_val = prev_data.get('final_recommendation')
    fr_idx = 0 if fr_val == "Yes" else (1 if fr_val == "No" else None)
    q20 = st.radio("Do you recommend this application for further consideration?", ["Yes", "No"], index=fr_idx, horizontal=True, disabled=disabled)
    j21 = st.text_area("Final justification for your choice", value=prev_data.get('overall_justification', ""), disabled=disabled)

    return {
        "responses": {"12a":q12a, "12b":q12b, "12c":q12c, "13":j13, "14a":q14a, "14b":q14b, "15":j15, "16a":q16a, "17":j17, "18a":q18a, "19":j19},
        "recommendation": q20,
        "final_justification": j21,
        "is_complete": all(x is not None for x in [q12a, q12b, q12c, q14a, q14b, q16a, q18a, q20])
    }

# --- 5. Dialogs (Refactored) ---
@st.dialog("Edit Evaluation Form", width="large")
def edit_review_dialog(edit_data):
    st.info(f"Editing Review for **{edit_data['applicant_name']}**")
    prev_resp = json.loads(edit_data['responses']) if edit_data['responses'] else {}
    
    # Check if locked
    is_locked = edit_data.get('is_final', False)
    
    with st.form("edit_eval_form"):
        form_result = render_evaluation_fields(prev_resp, edit_data, disabled=is_locked)
        
        if not is_locked:
            if st.form_submit_button("Update Draft", use_container_width=True):
                with engine.begin() as conn:
                    conn.execute(text("""
                        UPDATE reviews SET responses=:r, final_recommendation=:fr, overall_justification=:oj, updated_at=:t 
                        WHERE id=:id
                    """), {
                        "r": json.dumps(form_result["responses"]), 
                        "fr": form_result["recommendation"], 
                        "oj": form_result["final_justification"], 
                        "t": get_malaysia_time(), 
                        "id": edit_data['id']
                    })
                st.session_state.success_msg = "Draft updated!"
                st.rerun()
        else:
            st.warning("This review is locked and cannot be edited.")
            if st.form_submit_button("Close"): st.rerun()

# --- 6. Application Logic ---
st.set_page_config(page_title="RBS Secure Review System", layout="wide")

if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if 'active_review_app' not in st.session_state: st.session_state.active_review_app = None

# --- [Login Logic Unchanged] ---
if not st.session_state.authenticated:
    st.title("🔐 RBS Grant Login")
    with st.form("login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            with engine.connect() as conn:
                res_admin = conn.execute(text("SELECT password_hash, full_name, profile_pic FROM users WHERE username = :u"), {"u": u}).fetchone()
                if res_admin and check_password(p, res_admin[0]):
                    st.session_state.update({"authenticated": True, "username": u, "role": "Admin", "full_name": res_admin[1], "pic": res_admin[2], "menu_choice": "Dashboard"})
                    st.rerun()
                else:
                    res_rev = conn.execute(text("SELECT password_hash, full_name, profile_pic FROM reviewers WHERE username = :u"), {"u": u}).fetchone()
                    if res_rev and check_password(p, res_rev[0]):
                        st.session_state.update({"authenticated": True, "username": u, "role": "Reviewer", "full_name": res_rev[1], "pic": res_rev[2], "menu_choice": "Review Form"})
                        st.rerun()
                    else: st.error("Invalid credentials")
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    if st.session_state.pic: st.image(bytes(st.session_state.pic), width=100)
    else: st.image("https://cdn-icons-png.flaticon.com/512/149/149071.png", width=100) 
    st.title(f"{st.session_state.full_name}")
    options = ["Dashboard", "User Management", "Reviewer Management", "Applicant Management"] if st.session_state.role == "Admin" else ["Review Form", "My Submissions"]
    st.session_state.menu_choice = st.radio("Navigation", options, index=options.index(st.session_state.menu_choice) if st.session_state.menu_choice in options else 0)
    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

# --- REVIEWER: REVIEW FORM ---
if st.session_state.menu_choice == "Review Form":
    st.title("Dr Ranjeet Bhagwan Singh Grant Review")
    
    # Logic to check if user has already finalized everything
    is_fully_locked = pd.read_sql(text("SELECT COUNT(*) FROM reviews WHERE reviewer_username = :u AND is_final = TRUE"), engine, params={"u": st.session_state.username}).iloc[0,0] > 0

    if st.session_state.active_review_app:
        # INDIVIDUAL REVIEW FORM VIEW
        app_name = st.session_state.active_review_app
        app_details = pd.read_sql(text("SELECT * FROM applicants WHERE name = :n"), engine, params={"n": app_name}).iloc[0]
        
        # Check if there is an existing draft
        existing_rev = pd.read_sql(text("SELECT * FROM reviews WHERE reviewer_username = :u AND applicant_name = :a"), engine, params={"u": st.session_state.username, "a": app_name})
        prev_resp = json.loads(existing_rev.iloc[0]['responses']) if not existing_rev.empty else None
        prev_data = existing_rev.iloc[0].to_dict() if not existing_rev.empty else None

        with st.container(border=True):
            c1, c2 = st.columns([1, 4])
            with c1:
                if app_details['photo']: st.image(bytes(app_details['photo']), width=120)
            with c2:
                st.subheader(app_details['name'])
                st.write(f"**Proposal:** {app_details['proposal_title']}")
                st.markdown(f"🔗 [Supporting Documents]({app_details['info_link']})")

        with st.form("main_review_form"):
            form_result = render_evaluation_fields(prev_resp, prev_data, disabled=is_fully_locked)
            
            col_b1, col_b2 = st.columns(2)
            if not is_fully_locked:
                if col_b1.form_submit_button("💾 Save Review as Draft", type="primary", use_container_width=True):
                    with engine.begin() as conn:
                        if not existing_rev.empty:
                            conn.execute(text("UPDATE reviews SET responses=:r, final_recommendation=:fr, overall_justification=:oj, updated_at=:t WHERE id=:id"), 
                                         {"r": json.dumps(form_result["responses"]), "fr": form_result["recommendation"], "oj": form_result["final_justification"], "t": get_malaysia_time(), "id": int(prev_data['id'])})
                        else:
                            conn.execute(text("INSERT INTO reviews (reviewer_username, applicant_name, responses, final_recommendation, overall_justification, submitted_at, updated_at) VALUES (:u, :a, :r, :fr, :oj, :t, :t)"), 
                                         {"u": st.session_state.username, "a": app_name, "r": json.dumps(form_result["responses"]), "fr": form_result["recommendation"], "oj": form_result["final_justification"], "t": get_malaysia_time()})
                    st.toast(f"Progress saved for {app_name}!")
                    st.session_state.active_review_app = None
                    st.rerun()
            
            if col_b2.form_submit_button("Cancel", use_container_width=True):
                st.session_state.active_review_app = None
                st.rerun()

    else:
        # APPLICANT CARD GRID VIEW
        apps = pd.read_sql("SELECT * FROM applicants", engine)
        revs = pd.read_sql(text("SELECT applicant_name, responses FROM reviews WHERE reviewer_username = :u"), engine, params={"u": st.session_state.username})
        reviewed_names = revs['applicant_name'].tolist()

        st.subheader("Select an Applicant to Review")
        
        # Display as cards
        for i in range(0, len(apps), 3):
            cols = st.columns(3)
            for j in range(3):
                if i + j < len(apps):
                    row = apps.iloc[i + j]
                    with cols[j]:
                        with st.container(border=True):
                            # Small Profile Pic
                            if row['photo']: st.image(bytes(row['photo']), width=80)
                            else: st.image("https://cdn-icons-png.flaticon.com/512/149/149071.png", width=80)
                            
                            st.write(f"**{row['name']}**")
                            st.caption(row['proposal_title'][:100] + "...")
                            
                            is_done = row['name'] in reviewed_names
                            btn_label = "📝 Edit Draft" if is_done else "➕ Start Review"
                            if st.button(btn_label, key=f"btn_{row['id']}", use_container_width=True, disabled=is_fully_locked):
                                st.session_state.active_review_app = row['name']
                                st.rerun()
        
        # --- FINAL SUBMISSION SECTION ---
        if not is_fully_locked and len(reviewed_names) >= len(apps) and len(apps) > 0:
            st.divider()
            with st.container(border=True):
                st.warning("⚠️ **Final Submission:** You have completed all reviews. Clicking the button below will lock your evaluations permanently.")
                if st.button("🚀 SUBMIT ALL REVIEWS", type="primary", use_container_width=True):
                    with engine.begin() as conn:
                        conn.execute(text("UPDATE reviews SET is_final = TRUE WHERE reviewer_username = :u"), {"u": st.session_state.username})
                    st.success("All reviews finalized and locked!")
                    st.balloons()
                    st.rerun()
        elif is_fully_locked:
            st.success("✅ All your evaluations have been submitted and locked.")

# --- REVIEWER: MY SUBMISSIONS ---
elif st.session_state.menu_choice == "My Submissions":
    st.header("📋 My Review History")
    query = text("""
        SELECT r.*, a.photo 
        FROM reviews r 
        LEFT JOIN applicants a ON r.applicant_name = a.name 
        WHERE r.reviewer_username = :u 
        ORDER BY r.submitted_at DESC
    """)
    my_revs = pd.read_sql(query, engine, params={"u": st.session_state.username})
    
    if my_revs.empty:
        st.info("You haven't started any reviews yet.")
    
    for _, row in my_revs.iterrows():
        with st.container(border=True):
            m1, m2, m3 = st.columns([1, 5, 2])
            with m1:
                if row['photo']: st.image(bytes(row['photo']), width=70)
                else: st.image("https://cdn-icons-png.flaticon.com/512/149/149071.png", width=70)
            with m2:
                st.markdown(f"### {row['applicant_name']}")
                st.caption(f"Submitted: {row['submitted_at']} | Recommendation: **{row['final_recommendation']}**")
                st.write("**Justification:**")
                st.write(row['overall_justification'])
            with m3:
                # Reuse the dialog for viewing/editing
                if st.button("View Detail", key=f"view_{row['id']}", use_container_width=True):
                    edit_review_dialog(row)

# --- [Admin Dashboard & Management Logic - Keep existing or standard] ---
elif st.session_state.menu_choice == "Dashboard":
    st.header("📊 Analytics Dashboard")
    # ... [Keep your existing analytics code here] ...
    st.info("Analytics engine is active.")
