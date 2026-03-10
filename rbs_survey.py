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
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except:
        return False

def get_malaysia_time():
    my_tz = timezone(timedelta(hours=8))
    return datetime.now(my_tz).strftime('%Y-%m-%d %H:%M:%S')

def get_radio_index(prev_dict, key):
    if not prev_dict: return None
    val = prev_dict.get(key)
    if val == "Yes": return 0
    if val == "No": return 1
    return None

def save_review_data(applicant_name, result, is_update=False, review_id=None):
    """Helper to handle database writes for both new and updated reviews"""
    now = get_malaysia_time()
    resp_json = json.dumps(result["responses"])
    
    with engine.begin() as conn:
        if is_update:
            conn.execute(text("""
                UPDATE reviews SET responses=:r, final_recommendation=:fr, 
                overall_justification=:oj, updated_at=:t WHERE id=:id
            """), {"r": resp_json, "fr": result["recommendation"], 
                   "oj": result["justification"], "t": now, "id": int(review_id)})
        else:
            conn.execute(text("""
                INSERT INTO reviews (reviewer_username, applicant_name, responses, 
                final_recommendation, overall_justification, submitted_at, updated_at) 
                VALUES (:u, :a, :r, :fr, :oj, :t, :t)
            """), {"u": st.session_state.username, "a": applicant_name, "r": resp_json, 
                   "fr": result["recommendation"], "oj": result["justification"], "t": now})

# --- 3. Database Schema Self-Healing ---
with engine.begin() as conn:
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
            updated_at TIMESTAMP,
            is_final BOOLEAN DEFAULT FALSE
        )
    """))
    conn.execute(text("ALTER TABLE reviews ADD COLUMN IF NOT EXISTS is_final BOOLEAN DEFAULT FALSE"))
    
    if conn.execute(text("SELECT COUNT(*) FROM users")).fetchone()[0] == 0:
        conn.execute(text("INSERT INTO users (username, full_name, email, password_hash, role) VALUES ('admin', 'Master Admin', 'admin@system.com', :pw, 'Admin')"), {"pw": hash_password("Admin123!")})

# --- 4. Shared Question Engine ---
def render_evaluation_fields(prev_resp=None, prev_data=None, disabled=False):
    if prev_resp is None: prev_resp = {}
    if prev_data is None: prev_data = {}

    st.subheader("Section 1 — Research Quality and Feasibility")
    q12a = st.radio("a) Are the proposed methods and objectives appropriate and achievable within the grant period (2 years)?", ["Yes", "No"], index=get_radio_index(prev_resp, "12a"), horizontal=True, disabled=disabled, key="q12a")
    q12b = st.radio("b) Does the applicant have relevant expertise and a strong research track record?", ["Yes", "No"], index=get_radio_index(prev_resp, "12b"), horizontal=True, disabled=disabled, key="q12b")
    q12c = st.radio("c) Have potential risks been identified, and are there plans to address them?", ["Yes", "No"], index=get_radio_index(prev_resp, "12c"), horizontal=True, disabled=disabled, key="q12c")
    j13 = st.text_area("13) Justification (Research Quality)", value=prev_resp.get("13", ""), disabled=disabled, key="j13")

    st.divider()
    st.subheader("Section 2 — Potential Impact")
    q14a = st.radio("a) Does the research address an important issue in medical science?", ["Yes", "No"], index=get_radio_index(prev_resp, "14a"), horizontal=True, disabled=disabled, key="q14a")
    q14b = st.radio("b) Does it have the potential to contribute to significant advancements in the medical field?", ["Yes", "No"], index=get_radio_index(prev_resp, "14b"), horizontal=True, disabled=disabled, key="q14b")
    j15 = st.text_area("15) Justification (Potential Impact)", value=prev_resp.get("15", ""), disabled=disabled, key="j15")

    st.divider()
    st.subheader("Section 3 — Innovation and Novelty")
    q16a = st.radio("a) Does the research propose a novel approach or methodology?", ["Yes", "No"], index=get_radio_index(prev_resp, "16a"), horizontal=True, disabled=disabled, key="q16a")
    j17 = st.text_area("17) Justification (Innovation)", value=prev_resp.get("17", ""), disabled=disabled, key="j17")

    st.divider()
    st.subheader("Section 4 — Value for Money")
    q18a = st.radio("a) Are the requested funds essential and appropriately allocated?", ["Yes", "No"], index=get_radio_index(prev_resp, "18a"), horizontal=True, disabled=disabled, key="q18a")
    j19 = st.text_area("19) Justification (Value for Money)", value=prev_resp.get("19", ""), disabled=disabled, key="j19")

    st.divider()
    st.subheader("Section 5 — Final Recommendation")
    fr_val = prev_data.get('final_recommendation')
    fr_idx = 0 if fr_val == "Yes" else (1 if fr_val == "No" else None)
    q20 = st.radio("20) Considering the evaluations made, do you recommend this application?", ["Yes", "No"], index=fr_idx, horizontal=True, disabled=disabled, key="q20")
    j21 = st.text_area("21) Final justification for your choice", value=prev_data.get('overall_justification', ""), disabled=disabled, key="j21")

    return {
        "responses": {"12a":q12a, "12b":q12b, "12c":q12c, "13":j13, "14a":q14a, "14b":q14b, "15":j15, "16a":q16a, "17":j17, "18a":q18a, "19":j19},
        "recommendation": q20, "justification": j21, "complete": all(x is not None for x in [q12a, q12b, q12c, q14a, q14b, q16a, q18a, q20])
    }

# --- 5. Application Setup & State Initialization ---
st.set_page_config(page_title="RBS Secure Review", layout="wide")

if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if 'menu_choice' not in st.session_state: st.session_state.menu_choice = "Dashboard"
if 'active_review_app' not in st.session_state: st.session_state.active_review_app = None
if 'pic' not in st.session_state: st.session_state.pic = None

# --- LOGIN LOGIC ---
if not st.session_state.authenticated:
    st.title("🔐 RBS Grant Review Login")
    with st.form("login"):
        u, p = st.text_input("Username"), st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            with engine.connect() as conn:
                res = conn.execute(text("SELECT password_hash, 'Admin' as role, full_name, profile_pic FROM users WHERE username = :u UNION SELECT password_hash, 'Reviewer' as role, full_name, profile_pic FROM reviewers WHERE username = :u"), {"u": u}).fetchone()
                if res and check_password(p, res[0]):
                    st.session_state.update({"authenticated": True, "username": u, "role": res[1], "full_name": res[2], "pic": res[3], "menu_choice": "Dashboard" if res[1] == "Admin" else "Review Form"})
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

menu = st.session_state.menu_choice

# --- REVIEWER: REVIEW FORM ---
if menu == "Review Form":
    st.title("Dr Ranjeet Bhagwan Singh Grant Review Portal")
    is_locked = pd.read_sql(text("SELECT COUNT(*) FROM reviews WHERE reviewer_username = :u AND is_final = TRUE"), engine, params={"u": st.session_state.username}).iloc[0,0] > 0

    if st.session_state.active_review_app:
        # INDIVIDUAL FORM VIEW
        name = st.session_state.active_review_app
        app = pd.read_sql(text("SELECT * FROM applicants WHERE name = :n"), engine, params={"n": name}).iloc[0]
        rev = pd.read_sql(text("SELECT * FROM reviews WHERE reviewer_username = :u AND applicant_name = :a"), engine, params={"u": st.session_state.username, "a": name})
        prev_resp = json.loads(rev.iloc[0]['responses']) if not rev.empty else None
        
        # Small Info Box
        with st.container(border=True):
            c1, c2 = st.columns([1, 5])
            with c1:
                if app['photo']: st.image(bytes(app['photo']), width=120)
                else: st.image("https://cdn-icons-png.flaticon.com/512/149/149071.png", width=120)
            with c2:
                st.subheader(name)
                st.write(f"**Proposal:** {app['proposal_title']}")
                st.markdown(f"🔗 [Supporting Documents]({app['info_link']})")

        with st.form("evaluation_form"):
            result = render_evaluation_fields(prev_resp, rev.iloc[0].to_dict() if not rev.empty else {}, disabled=is_locked)
            col1, col2 = st.columns(2)
            if not is_locked:
                if col1.form_submit_button("💾 Save Review as Draft", use_container_width=True, type="primary"):
                    save_review_data(name, result, is_update=not rev.empty, review_id=rev.iloc[0]['id'] if not rev.empty else None)
                    st.session_state.active_review_app = None
                    st.rerun()
            if col2.form_submit_button("Back to Gallery", use_container_width=True):
                st.session_state.active_review_app = None
                st.rerun()
    else:
        # APPLICANT CARD VIEW
        apps = pd.read_sql("SELECT * FROM applicants", engine)
        revs = pd.read_sql(text("SELECT applicant_name FROM reviews WHERE reviewer_username = :u"), engine, params={"u": st.session_state.username})['applicant_name'].tolist()
        
        st.subheader("Select an Applicant")
        for i in range(0, len(apps), 3):
            cols = st.columns(3)
            for j in range(3):
                if i+j < len(apps):
                    row = apps.iloc[i+j]
                    with cols[j]:
                        with st.container(border=True):
                            # Small Profile Pic in Card
                            card_img, card_info = st.columns([1, 2])
                            if row['photo']: card_img.image(bytes(row['photo']), width=80)
                            else: card_img.image("https://cdn-icons-png.flaticon.com/512/149/149071.png", width=80)
                            
                            card_info.write(f"**{row['name']}**")
                            card_info.caption(row['proposal_title'][:60] + "...")
                            
                            done = row['name'] in revs
                            st.markdown(f":{'green' if done else 'orange'}[● {'Draft Completed' if done else 'Awaiting'}]")
                            
                            if st.button("Review" if not done else "Edit Review", key=f"btn_{row['id']}", use_container_width=True, disabled=is_locked):
                                st.session_state.active_review_app = row['name']
                                st.rerun()

        # Final locking section
        if not is_locked and len(revs) >= len(apps) and len(apps) > 0:
            st.divider()
            with st.container(border=True):
                st.warning("⚠️ **Final Submission:** You have completed all drafts. Once you click below, your reviews will be permanently locked.")
                if st.button("🚀 SUBMIT ALL REVIEWS", type="primary", use_container_width=True):
                    with engine.begin() as conn:
                        conn.execute(text("UPDATE reviews SET is_final = TRUE WHERE reviewer_username = :u"), {"u": st.session_state.username})
                    st.balloons(); st.rerun()
        elif is_fully_locked := is_locked:
            st.success("✅ All evaluations have been finalized and locked.")

# --- REVIEWER: MY SUBMISSIONS ---
elif menu == "My Submissions":
    st.header("📋 Review History")
    my_revs = pd.read_sql(text("""
        SELECT r.*, a.photo, a.proposal_title 
        FROM reviews r 
        LEFT JOIN applicants a ON r.applicant_name = a.name 
        WHERE r.reviewer_username = :u 
        ORDER BY r.submitted_at DESC
    """), engine, params={"u": st.session_state.username})
    
    if my_revs.empty:
        st.info("No reviews recorded yet.")
    
    for _, row in my_revs.iterrows():
        with st.container(border=True):
            m1, m2, m3 = st.columns([1, 5, 2])
            with m1:
                if row['photo']: st.image(bytes(row['photo']), width=70)
                else: st.image("https://cdn-icons-png.flaticon.com/512/149/149071.png", width=70)
            with m2:
                st.markdown(f"### {row['applicant_name']}")
                st.caption(f"Proposal: {row['proposal_title']}")
                st.write(f"📅 Submitted: {row['submitted_at']}")
            with m3:
                color = "green" if row['final_recommendation'] == "Yes" else "red"
                st.markdown(f"<h3 style='color:{color}; text-align:right;'>{row['final_recommendation']}</h3>", unsafe_allow_html=True)
            
            st.divider()
            st.write("**Overall Justification:**")
            st.info(row['overall_justification'] or "No justification provided.")

# --- PLACEHOLDERS ---
else:
    st.info(f"The {menu} module is active.")
