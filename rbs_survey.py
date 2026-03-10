import streamlit as st
import pandas as pd
import bcrypt
from sqlalchemy import create_engine, text
import plotly.express as px
import json
import io
from datetime import datetime, timedelta, timezone
import extra_streamlit_components as stx

# --- 1. Database & Cookie Setup ---
@st.cache_resource
def get_engine():
    # Uses your secret DATABASE_URL from Streamlit Cloud
    return create_engine(st.secrets["DATABASE_URL"])

engine = get_engine()

# Cookie manager must be outside cache because it is a widget
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

# --- 3. Standardized Question Engine (Clean & No Numbers) ---
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
    j13 = st.text_area("Justification (if any)", value=prev_resp.get("13", ""), key=f"{prefix}j13")

    st.subheader("Potential Impact")
    q14a = st.radio("a) Does the research address an important issue in medical science?", 
                    ["Yes", "No"], index=get_radio_index(prev_resp, "14a"), horizontal=True, key=f"{prefix}q14a")
    q14b = st.radio("b) Does it have the potential to contribute to significant advancements in the medical field?", 
                    ["Yes", "No"], index=get_radio_index(prev_resp, "14b"), horizontal=True, key=f"{prefix}q14b")
    j15 = st.text_area("Justification (if any)", value=prev_resp.get("15", ""), key=f"{prefix}j15")

    st.subheader("Innovation and Novelty")
    q16a = st.radio("a) Does the research propose a novel approach or methodology?", 
                    ["Yes", "No"], index=get_radio_index(prev_resp, "16a"), horizontal=True, key=f"{prefix}q16a")
    j17 = st.text_area("Justification (if any)", value=prev_resp.get("17", ""), key=f"{prefix}j17")

    st.subheader("Value for Money")
    q18a = st.radio("a) Are the requested funds essential and appropriately allocated based on the importance of the research?", 
                    ["Yes", "No"], index=get_radio_index(prev_resp, "18a"), horizontal=True, key=f"{prefix}q18a")
    j19 = st.text_area("Justification (if any)", value=prev_resp.get("19", ""), key=f"{prefix}j19")

    responses = {"12a": q12a, "12b": q12b, "12c": q12c, "13": j13, "14a": q14a, "14b": q14b, "15": j15, "16a": q16a, "17": j17, "18a": q18a, "19": j19}
    is_complete = all(x is not None for x in [q12a, q12b, q12c, q14a, q14b, q16a, q18a])
    return responses, is_complete

# --- 4. Database Schema Setup ---
with engine.begin() as conn:
    conn.execute(text("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username VARCHAR(255) UNIQUE, full_name VARCHAR(255), email VARCHAR(255), password_hash VARCHAR(255), role VARCHAR(50), profile_pic BYTEA)"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS reviewers (id SERIAL PRIMARY KEY, username VARCHAR(255) UNIQUE, full_name VARCHAR(255), email VARCHAR(255), password_hash VARCHAR(255), profile_pic BYTEA)"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS applicants (id SERIAL PRIMARY KEY, name VARCHAR(255) UNIQUE, proposal_title TEXT, info_link TEXT, photo BYTEA)"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS reviews (id SERIAL PRIMARY KEY, reviewer_username VARCHAR(255) REFERENCES reviewers(username) ON UPDATE CASCADE ON DELETE SET NULL, applicant_name VARCHAR(255), responses TEXT, final_recommendation VARCHAR(50), overall_justification TEXT, submitted_at TIMESTAMP, updated_at TIMESTAMP)"))
    
    # Auto-admin check
    if conn.execute(text("SELECT COUNT(*) FROM users")).fetchone()[0] == 0:
        conn.execute(text("INSERT INTO users (username, full_name, role, password_hash) VALUES ('admin', 'Master Admin', 'Admin', :pw)"), {"pw": hash_password("Admin123!")})

# --- 5. Persistence & Auth Logic ---
if 'authenticated' not in st.session_state: st.session_state.authenticated = False

saved_user = cookie_manager.get(cookie="rbs_user")
if saved_user and not st.session_state.authenticated:
    with engine.connect() as conn:
        res = conn.execute(text("SELECT full_name, 'Admin' as r FROM users WHERE username=:u UNION SELECT full_name, 'Reviewer' as r FROM reviewers WHERE username=:u"), {"u": saved_user}).fetchone()
        if res: st.session_state.update({"authenticated": True, "username": saved_user, "full_name": res[0], "role": res[1]})

# --- 6. Dialogs ---
@st.dialog("Edit Evaluation Form", width="large")
def edit_review_dialog(edit_data):
    st.info(f"Editing Review for **{edit_data['applicant_name']}**")
    prev_resp = json.loads(edit_data['responses']) if edit_data['responses'] else {}
    with st.form("edit_rbs_full_form"):
        resp_data, complete = render_evaluation_fields(prev_resp, is_edit=True)
        st.divider()
        q20 = st.radio("Considering the evaluations made, do you recommend this application for further consideration?", ["Yes", "No"], index=(0 if edit_data['final_recommendation']=="Yes" else 1), horizontal=True)
        j21 = st.text_area("Please provide a justification for your choice above.", value=edit_data.get('overall_justification', ""))
        if st.form_submit_button("Update Evaluation"):
            if complete and q20:
                with engine.begin() as conn:
                    conn.execute(text("UPDATE reviews SET responses=:r, final_recommendation=:fr, overall_justification=:oj, updated_at=:t WHERE id=:id"),
                                 {"r": json.dumps(resp_data), "fr": q20, "oj": j21, "t": get_malaysia_time(), "id": int(edit_data['id'])})
                st.session_state.success_msg = "Successfully updated!"; st.rerun()

# --- 7. Main UI ---
st.set_page_config(page_title="RBS Secure Review System", layout="wide")

if not st.session_state.authenticated:
    st.title("🔐 RBS Shortlisting Review Form")
    with st.form("login"):
        u, p = st.text_input("Username"), st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            with engine.connect() as conn:
                res = conn.execute(text("SELECT password_hash, full_name, 'Admin' as r FROM users WHERE username=:u UNION SELECT password_hash, full_name, 'Reviewer' as r FROM reviewers WHERE username=:u"), {"u": u}).fetchone()
                if res and check_password(p, res[0]):
                    cookie_manager.set("rbs_user", u, expires_at=datetime.now() + timedelta(days=7))
                    st.session_state.update({"authenticated": True, "username": u, "full_name": res[1], "role": res[2]})
                    st.rerun()
                else: st.error("Invalid credentials")
    st.stop()

with st.sidebar:
    st.title(f"Hi, {st.session_state.full_name}")
    nav = ["Dashboard", "User Management", "Reviewer Management", "Applicant Management"] if st.session_state.role == "Admin" else ["Review Form", "My Submissions"]
    menu = st.radio("Navigation", nav)
    if st.button("Logout"):
        cookie_manager.delete("rbs_user"); st.session_state.clear(); st.rerun()

if 'success_msg' in st.session_state:
    st.success(st.session_state.success_msg); del st.session_state.success_msg

# --- PAGE LOGIC ---
if menu == "Review Form":
    st.title("Dr Ranjeet Bhagwan Singh Medical Research Grant Review")
    st.subheader(f"👋 Welcome, {st.session_state.full_name}!")
    
    pending_q = text("SELECT * FROM applicants WHERE name NOT IN (SELECT applicant_name FROM reviews WHERE reviewer_username = :u)")
    apps_df = pd.read_sql(pending_q, engine, params={"u": st.session_state.username})
    
    if apps_df.empty: 
        st.success("All reviews completed!"); st.stop()
        
    target_applicant_name = st.selectbox("Select Applicant", apps_df['name'])
    app_details = pd.read_sql(text("SELECT * FROM applicants WHERE name = :n"), engine, params={"n": target_applicant_name}).iloc[0]
    
    with st.container(border=True):
        c_img, c_info = st.columns([1, 4])
        with c_img:
            if app_details['photo']: st.image(bytes(app_details['photo']), width=150)
            else: st.image("https://cdn-icons-png.flaticon.com/512/149/149071.png", width=150)
        with c_info:
            st.subheader(app_details['name'])
            st.write(f"**Proposal:** {app_details['proposal_title']}")
            st.markdown(f"**OneDrive / Supporting Documents:** [Click to View Files]({app_details['info_link']})")

    @st.fragment
    def render_form_fragment():
        with st.form("rbs_full_form"):
            resp, complete = render_evaluation_fields()
            st.divider()
            q20 = st.radio("Considering the evaluations made, do you recommend this application for further consideration?", ["Yes", "No"], index=None, horizontal=True)
            j21 = st.text_area("Please provide a justification for your choice above.")
            
            if st.form_submit_button("Submit Evaluation"):
                if not complete or q20 is None:
                    st.warning("Please select Yes/No for all criteria before submitting.")
                else:
                    with engine.begin() as conn:
                        conn.execute(text("INSERT INTO reviews (reviewer_username, applicant_name, responses, final_recommendation, overall_justification, submitted_at, updated_at) VALUES (:u, :a, :r, :fr, :oj, :t, :t)"),
                                     {"u": st.session_state.username, "a": target_applicant_name, "r": json.dumps(resp), "fr": q20, "oj": j21, "t": get_malaysia_time()})
                    st.session_state.success_msg = "Submitted!"
                    st.session_state.menu_choice = "My Submissions"
                    st.rerun()
    render_form_fragment()

elif menu == "My Submissions":
    st.header("📋 My Review History")
    query = text("SELECT r.*, a.photo FROM reviews r LEFT JOIN applicants a ON r.applicant_name = a.name WHERE r.reviewer_username = :u ORDER BY r.submitted_at DESC")
    my_revs = pd.read_sql(query, engine, params={"u": st.session_state.username})
    for _, row in my_revs.iterrows():
        with st.container(border=True):
            m1, m2, m3, m4 = st.columns([1, 4, 2, 1])
            with m1:
                if row['photo']: st.image(bytes(row['photo']), width=70)
                else: st.image("https://cdn-icons-png.flaticon.com/512/149/149071.png", width=70)
            with m2:
                st.write(f"**Applicant:** {row['applicant_name']}")
                st.caption(f"Submitted: {row['submitted_at']}")
            m3.write(f"**Rec:** {row['final_recommendation']}")
            with m4:
                if st.button("✏️ Edit", key=f"h_{row['id']}"): edit_review_dialog(row)

elif menu == "Applicant Management":
    st.header("📝 Applicant Management")
    t1, t2 = st.tabs(["Add Individual", "Bulk Add"])
    with t1:
        with st.expander("➕ Create New Applicant"):
            with st.form("add_app"):
                an, at, al = st.text_input("Name"), st.text_area("Proposal Title"), st.text_input("OneDrive Link")
                ap = st.file_uploader("Applicant Photo", type=['jpg', 'png'])
                if st.form_submit_button("Add"):
                    p_data = ap.getvalue() if ap else None
                    with engine.begin() as conn:
                        conn.execute(text("INSERT INTO applicants (name, proposal_title, info_link, photo) VALUES (:n, :t, :l, :p)"), {"n": an, "t": at, "l": al, "p": p_data})
                    st.rerun()
    with t2:
        st.info("Format: Name, Proposal Title, Link (CSV Format)")
        uploaded_file = st.file_uploader("Upload CSV", type="csv")
        if uploaded_file and st.button("Process Bulk"):
            bulk_df = pd.read_csv(uploaded_file)
            with engine.begin() as conn:
                for _, r in bulk_df.iterrows():
                    conn.execute(text("INSERT INTO applicants (name, proposal_title, info_link) VALUES (:n, :t, :l) ON CONFLICT (name) DO NOTHING"), {"n": r['name'], "t": r['proposal_title'], "l": r['info_link']})
            st.success("Applicants added!"); st.rerun()
    apps = pd.read_sql("SELECT id, name, proposal_title FROM applicants", engine)
    st.dataframe(apps, use_container_width=True)

elif menu == "Dashboard":
    st.header("📊 Admin Dashboard")
    df = pd.read_sql("SELECT reviewer_username, applicant_name, final_recommendation FROM reviews", engine)
    if not df.empty:
        st.metric("Total Reviews", len(df))
        st.dataframe(df, use_container_width=True)

# ... Placeholders for other Management modules ...
else:
    st.info(f"The {menu} module is active.")
