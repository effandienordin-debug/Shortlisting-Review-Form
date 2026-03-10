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
    q12a = st.radio("a) Are the proposed methods achievable?", ["Yes", "No"], index=get_radio_index(prev_resp, "12a"), horizontal=True, disabled=disabled, key="q12a")
    q12b = st.radio("b) Does the applicant have expertise?", ["Yes", "No"], index=get_radio_index(prev_resp, "12b"), horizontal=True, disabled=disabled, key="q12b")
    q12c = st.radio("c) Are risks identified?", ["Yes", "No"], index=get_radio_index(prev_resp, "12c"), horizontal=True, disabled=disabled, key="q12c")
    j13 = st.text_area("Justification (Quality)", value=prev_resp.get("13", ""), disabled=disabled, key="j13")

    st.divider()
    st.subheader("Section 2 — Potential Impact")
    q14a = st.radio("a) Address important issue?", ["Yes", "No"], index=get_radio_index(prev_resp, "14a"), horizontal=True, disabled=disabled, key="q14a")
    q14b = st.radio("b) Significant advancements?", ["Yes", "No"], index=get_radio_index(prev_resp, "14b"), horizontal=True, disabled=disabled, key="q14b")
    j15 = st.text_area("Justification (Impact)", value=prev_resp.get("15", ""), disabled=disabled, key="j15")

    st.divider()
    st.subheader("Section 3 — Innovation and Novelty")
    q16a = st.radio("a) Novel approach?", ["Yes", "No"], index=get_radio_index(prev_resp, "16a"), horizontal=True, disabled=disabled, key="q16a")
    j17 = st.text_area("Justification (Innovation)", value=prev_resp.get("17", ""), disabled=disabled, key="j17")

    st.divider()
    st.subheader("Section 4 — Value for Money")
    q18a = st.radio("a) Funds essential?", ["Yes", "No"], index=get_radio_index(prev_resp, "18a"), horizontal=True, disabled=disabled, key="q18a")
    j19 = st.text_area("Justification (Value)", value=prev_resp.get("19", ""), disabled=disabled, key="j19")

    st.divider()
    st.subheader("Section 5 — Final Recommendation")
    fr_val = prev_data.get('final_recommendation')
    fr_idx = 0 if fr_val == "Yes" else (1 if fr_val == "No" else None)
    q20 = st.radio("Do you recommend this application?", ["Yes", "No"], index=fr_idx, horizontal=True, disabled=disabled, key="q20")
    j21 = st.text_area("Final justification", value=prev_data.get('overall_justification', ""), disabled=disabled, key="j21")

    return {
        "responses": {"12a":q12a, "12b":q12b, "12c":q12c, "13":j13, "14a":q14a, "14b":q14b, "15":j15, "16a":q16a, "17":j17, "18a":q18a, "19":j19},
        "recommendation": q20, "justification": j21, "complete": all(x is not None for x in [q12a, q12b, q12c, q14a, q14b, q16a, q18a, q20])
    }

# --- 5. Application Setup & State Initialization ---
st.set_page_config(page_title="RBS Secure Review", layout="wide")

# CRITICAL: Initialize session state keys to prevent AttributeErrors
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
    st.title("Dr Ranjeet Bhagwan Singh Grant Review")
    is_locked = pd.read_sql(text("SELECT COUNT(*) FROM reviews WHERE reviewer_username = :u AND is_final = TRUE"), engine, params={"u": st.session_state.username}).iloc[0,0] > 0

    if st.session_state.active_review_app:
        name = st.session_state.active_review_app
        app = pd.read_sql(text("SELECT * FROM applicants WHERE name = :n"), engine, params={"n": name}).iloc[0]
        rev = pd.read_sql(text("SELECT * FROM reviews WHERE reviewer_username = :u AND applicant_name = :a"), engine, params={"u": st.session_state.username, "a": name})
        prev_resp = json.loads(rev.iloc[0]['responses']) if not rev.empty else None
        
        with st.container(border=True):
            c1, c2 = st.columns([1, 4])
            with c1:
                if app['photo']: st.image(bytes(app['photo']), width=120)
            with c2:
                st.subheader(name)
                st.write(f"**Proposal:** {app['proposal_title']}")
                st.markdown(f"🔗 [Supporting Documents]({app['info_link']})")

        with st.form("evaluation_form"):
            result = render_evaluation_fields(prev_resp, rev.iloc[0].to_dict() if not rev.empty else {}, disabled=is_locked)
            col1, col2 = st.columns(2)
            if not is_locked:
                if col1.form_submit_button("💾 Save Draft", use_container_width=True, type="primary"):
                    with engine.begin() as conn:
                        if not rev.empty:
                            conn.execute(text("UPDATE reviews SET responses=:r, final_recommendation=:fr, overall_justification=:oj, updated_at=:t WHERE id=:id"), {"r":json.dumps(result["responses"]), "fr":result["recommendation"], "oj":result["justification"], "t":get_malaysia_time(), "id":int(rev.iloc[0]['id'])})
                        else:
                            conn.execute(text("INSERT INTO reviews (reviewer_username, applicant_name, responses, final_recommendation, overall_justification, submitted_at, updated_at) VALUES (:u, :a, :r, :fr, :oj, :t, :t)"), {"u":st.session_state.username, "a":name, "r":json.dumps(result["responses"]), "fr":result["recommendation"], "oj":result["justification"], "t":get_malaysia_time()})
                    st.session_state.active_review_app = None
                    st.rerun()
            if col2.form_submit_button("Back to List", use_container_width=True):
                st.session_state.active_review_app = None
                st.rerun()
    else:
        apps = pd.read_sql("SELECT * FROM applicants", engine)
        revs = pd.read_sql(text("SELECT applicant_name FROM reviews WHERE reviewer_username = :u"), engine, params={"u": st.session_state.username})['applicant_name'].tolist()
        
        st.subheader("Applicant Gallery")
        for i in range(0, len(apps), 3):
            cols = st.columns(3)
            for j in range(3):
                if i+j < len(apps):
                    row = apps.iloc[i+j]
                    with cols[j]:
                        with st.container(border=True):
                            if row['photo']: st.image(bytes(row['photo']), width=80)
                            st.write(f"**{row['name']}**")
                            done = row['name'] in revs
                            st.markdown(f":{'green' if done else 'orange'}[● {'Draft Done' if done else 'Awaiting'}]")
                            if st.button("Review" if not done else "Edit", key=f"btn_{row['id']}", use_container_width=True, disabled=is_locked):
                                st.session_state.active_review_app = row['name']
                                st.rerun()

        if not is_locked and len(revs) >= len(apps) and len(apps) > 0:
            st.divider()
            if st.button("🚀 FINAL SUBMIT ALL REVIEWS", type="primary", use_container_width=True):
                with engine.begin() as conn:
                    conn.execute(text("UPDATE reviews SET is_final = TRUE WHERE reviewer_username = :u"), {"u": st.session_state.username})
                st.balloons(); st.rerun()

elif menu == "My Submissions":
    st.header("📋 Review History")
    my_revs = pd.read_sql(text("SELECT r.*, a.photo FROM reviews r LEFT JOIN applicants a ON r.applicant_name = a.name WHERE r.reviewer_username = :u ORDER BY r.submitted_at DESC"), engine, params={"u": st.session_state.username})
    for _, row in my_revs.iterrows():
        with st.container(border=True):
            m1, m2 = st.columns([1, 6])
            if row['photo']: m1.image(bytes(row['photo']), width=70)
            m2.markdown(f"### {row['applicant_name']} | Rec: **{row['final_recommendation']}**")
            st.info(row['overall_justification'] or "No justification provided.")

else:
    st.info(f"Module {menu} is active.")
