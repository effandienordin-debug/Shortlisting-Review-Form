import streamlit as stimport streamlit as st
import pandas as pd
import bcrypt
from sqlalchemy import create_engine, text
import plotly.express as px
import json
from datetime import datetime, timedelta, timezone
import extra_streamlit_components as stx

# --- 1. Database & Cookie Setup ---
@st.cache_resource
def get_engine():
    return create_engine(st.secrets["DATABASE_URL"])

engine = get_engine()

# Initialize Cookie Manager to prevent logout on refresh
def get_cookie_manager():
    return stx.CookieManager()

cookie_manager = get_cookie_manager()

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

# --- 3. Standardized Question Engine (IDENTICAL QUESTIONS) ---
def render_evaluation_fields(prev_resp=None, is_edit=False):
    prefix = "e_" if is_edit else "n_"
    if prev_resp is None: prev_resp = {}

    st.subheader("Research Quality and Feasibility")
    q12a = st.radio("a) Are the proposed methods and objectives appropriate and achievable within the grant period (2 years)?", 
                    ["Yes", "No"], index=get_radio_index(prev_resp, "12a"), horizontal=True, key=f"{prefix}q12a")
    q12b = st.radio("b) Does the applicant have relevant expertise and a strong research track record?", 
                    ["Yes", "No"], index=get_radio_index(prev_resp, "12b"), horizontal=True, key=f"{prefix}q12b")
    q12c = st.radio("c) Have potential risks been identified, and are there plans to address them?", 
                    ["Yes", "No"], index=get_radio_index(prev_resp, "12c"), horizontal=True, key=f"{prefix}q12c")
    j13 = st.text_area("Justification (Research Quality)", value=prev_resp.get("13", ""), key=f"{prefix}j13")

    st.subheader("Potential Impact")
    q14a = st.radio("a) Does the research address an important issue in medical science?", 
                    ["Yes", "No"], index=get_radio_index(prev_resp, "14a"), horizontal=True, key=f"{prefix}q14a")
    q14b = st.radio("b) Does it have the potential to contribute to significant advancements in the medical field?", 
                    ["Yes", "No"], index=get_radio_index(prev_resp, "14b"), horizontal=True, key=f"{prefix}q14b")
    j15 = st.text_area("Justification (Potential Impact)", value=prev_resp.get("15", ""), key=f"{prefix}j15")

    st.subheader("Innovation and Novelty")
    q16a = st.radio("a) Does the research propose a novel approach or methodology?", 
                    ["Yes", "No"], index=get_radio_index(prev_resp, "16a"), horizontal=True, key=f"{prefix}q16a")
    j17 = st.text_area("Justification (Innovation)", value=prev_resp.get("17", ""), key=f"{prefix}j17")

    st.subheader("Value for Money")
    q18a = st.radio("a) Are the requested funds essential and appropriately allocated?", 
                    ["Yes", "No"], index=get_radio_index(prev_resp, "18a"), horizontal=True, key=f"{prefix}q18a")
    j19 = st.text_area("Justification (Value for Money)", value=prev_resp.get("19", ""), key=f"{prefix}j19")

    responses = {"12a": q12a, "12b": q12b, "12c": q12c, "13": j13, "14a": q14a, "14b": q14b, "15": j15, "16a": q16a, "17": j17, "18a": q18a, "19": j19}
    is_complete = all(x is not None for x in [q12a, q12b, q12c, q14a, q14b, q16a, q18a])
    return responses, is_complete

# --- 4. Database Schema Setup ---
with engine.begin() as conn:
    conn.execute(text("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username VARCHAR(255) UNIQUE, full_name VARCHAR(255), email VARCHAR(255), password_hash VARCHAR(255), role VARCHAR(50), profile_pic BYTEA)"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS reviewers (id SERIAL PRIMARY KEY, username VARCHAR(255) UNIQUE, full_name VARCHAR(255), email VARCHAR(255), password_hash VARCHAR(255), profile_pic BYTEA)"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS applicants (id SERIAL PRIMARY KEY, name VARCHAR(255) UNIQUE, proposal_title TEXT, info_link TEXT, photo BYTEA)"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS reviews (id SERIAL PRIMARY KEY, reviewer_username VARCHAR(255) REFERENCES reviewers(username) ON UPDATE CASCADE, applicant_name VARCHAR(255), responses TEXT, final_recommendation VARCHAR(50), overall_justification TEXT, submitted_at TIMESTAMP, updated_at TIMESTAMP)"))
    if conn.execute(text("SELECT COUNT(*) FROM users")).fetchone()[0] == 0:
        conn.execute(text("INSERT INTO users (username, full_name, role, password_hash) VALUES ('admin', 'Master Admin', 'Admin', :pw)"), {"pw": hash_password("Admin123!")})

# --- 5. Persistence Logic (Auto-Login from Cookie) ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

saved_user = cookie_manager.get(cookie="rbs_user")
if saved_user and not st.session_state.authenticated:
    with engine.connect() as conn:
        res = conn.execute(text("SELECT full_name, 'Admin' as r FROM users WHERE username=:u UNION SELECT full_name, 'Reviewer' as r FROM reviewers WHERE username=:u"), {"u": saved_user}).fetchone()
        if res:
            st.session_state.update({"authenticated": True, "username": saved_user, "full_name": res[0], "role": res[1]})

# --- 6. Dialogs ---
@st.dialog("Edit Evaluation", width="large")
def edit_review_dialog(edit_data):
    prev_resp = json.loads(edit_data['responses'])
    with st.form("edit_eval"):
        new_resp, complete = render_evaluation_fields(prev_resp, is_edit=True)
        st.divider()
        q20 = st.radio("Recommend?", ["Yes", "No"], index=(0 if edit_data['final_recommendation']=="Yes" else 1), horizontal=True)
        j21 = st.text_area("Justification", value=edit_data.get('overall_justification', ""))
        if st.form_submit_button("Update"):
            if complete and q20:
                with engine.begin() as conn:
                    conn.execute(text("UPDATE reviews SET responses=:r, final_recommendation=:fr, overall_justification=:oj, updated_at=:t WHERE id=:id"),
                                 {"r": json.dumps(new_resp), "fr": q20, "oj": j21, "t": get_malaysia_time(), "id": int(edit_data['id'])})
                st.session_state.success_msg = "Updated!"; st.rerun()

# --- 7. Main UI ---
st.set_page_config(page_title="RBS Secure System", layout="wide")

if not st.session_state.authenticated:
    st.title("🔐 RBS Secure Login")
    with st.form("login"):
        u, p = st.text_input("Username"), st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            with engine.connect() as conn:
                res = conn.execute(text("SELECT password_hash, full_name, 'Admin' as r FROM users WHERE username=:u UNION SELECT password_hash, full_name, 'Reviewer' as r FROM reviewers WHERE username=:u"), {"u": u}).fetchone()
                if res and check_password(p, res[0]):
                    # Set the Cookie for 7 days
                    cookie_manager.set("rbs_user", u, expires_at=datetime.now() + timedelta(days=7))
                    st.session_state.update({"authenticated": True, "username": u, "full_name": res[1], "role": res[2]})
                    st.rerun()
                else: st.error("Invalid Credentials")
    st.stop()

# SIDEBAR
with st.sidebar:
    st.title(f"Hi, {st.session_state.full_name}")
    nav = ["Dashboard", "User Management", "Reviewer Management", "Applicant Management"] if st.session_state.role == "Admin" else ["Review Form", "My Submissions"]
    menu = st.radio("Navigation", nav)
    if st.button("Logout"):
        cookie_manager.delete("rbs_user")
        st.session_state.clear()
        st.rerun()

if 'success_msg' in st.session_state:
    st.success(st.session_state.success_msg); del st.session_state.success_msg

# PAGES
if menu == "Dashboard":
    st.header("📊 Admin Dashboard")
    df = pd.read_sql("SELECT reviewer_username, applicant_name, final_recommendation FROM reviews", engine)
    if not df.empty:
        st.metric("Total Reviews", len(df))
        st.dataframe(df, use_container_width=True)

elif menu == "Review Form":
    st.header("📝 New Evaluation")
    pending = pd.read_sql(text("SELECT * FROM applicants WHERE name NOT IN (SELECT applicant_name FROM reviews WHERE reviewer_username=:u)"), engine, params={"u": st.session_state.username})
    if pending.empty: st.success("🎉 All done!"); st.stop()
    
    selected = st.selectbox("Select Applicant", pending['name'])
    app = pending[pending['name'] == selected].iloc[0]
    
    with st.container(border=True):
        c1, c2 = st.columns([1, 4])
        if app['photo']: c1.image(bytes(app['photo']), width=150)
        c2.subheader(app['name'])
        c2.write(app['proposal_title'])

    @st.fragment
    def render_form():
        with st.form("main_form"):
            resp, complete = render_evaluation_fields()
            st.divider()
            q20 = st.radio("Final Recommendation?", ["Yes", "No"], index=None, horizontal=True)
            j21 = st.text_area("Final Justification")
            if st.form_submit_button("Submit"):
                if complete and q20:
                    with engine.begin() as conn:
                        conn.execute(text("INSERT INTO reviews (reviewer_username, applicant_name, responses, final_recommendation, overall_justification, submitted_at, updated_at) VALUES (:u, :a, :r, :fr, :oj, :t, :t)"),
                                     {"u": st.session_state.username, "a": selected, "r": json.dumps(resp), "fr": q20, "oj": j21, "t": get_malaysia_time()})
                    st.session_state.success_msg = "Submitted!"; st.rerun()
    render_form()

elif menu == "My Submissions":
    st.header("📋 My History")
    my_df = pd.read_sql(text("SELECT * FROM reviews WHERE reviewer_username=:u ORDER BY submitted_at DESC"), engine, params={"u": st.session_state.username})
    for _, row in my_df.iterrows():
        with st.container(border=True):
            cols = st.columns([4, 1, 1])
            cols[0].write(f"**Applicant:** {row['applicant_name']}")
            cols[1].write(f"**Rec:** {row['final_recommendation']}")
            if cols[2].button("Edit", key=f"ed_{row['id']}"): edit_review_dialog(row)

else:
    st.info(f"{menu} is ready for data.")
