import streamlit as st
import pandas as pd
import bcrypt
from sqlalchemy import create_engine, text
import plotly.express as px
import json
from datetime import datetime, timedelta, timezone
import extra_streamlit_components as stx

# --- 1. Database Configuration & Caching ---
@st.cache_resource
def get_engine():
    try:
        # Added connect_args for faster timeout (prevents white screen if DB is down)
        return create_engine(
            st.secrets["DATABASE_URL"],
            connect_args={'connect_timeout': 10}
        )
    except Exception as e:
        st.error(f"Database Connection Error: {e}")
        return None

engine = get_engine()

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
    return datetime.now(my_tz)

def get_radio_index(prev_dict, key):
    val = prev_dict.get(key)
    if val == "Yes": return 0
    if val == "No": return 1
    return None

# --- 3. Unified Evaluation Form ---
def render_evaluation_form(applicant_name, prev_data=None, is_locked=False):
    resp = json.loads(prev_data['responses']) if prev_data and prev_data.get('responses') else {}
    
    # Small Info Header
    with st.container(border=True):
        res = pd.read_sql(text("SELECT * FROM applicants WHERE name = :n"), engine, params={"n": applicant_name})
        if not res.empty:
            app_details = res.iloc[0]
            c_img, c_info = st.columns([1, 4])
            with c_img:
                if app_details['photo']: st.image(bytes(app_details['photo']), width=120)
                else: st.image("https://cdn-icons-png.flaticon.com/512/149/149071.png", width=120)
            with c_info:
                st.subheader(applicant_name)
                st.caption(f"**Proposal:** {app_details['proposal_title']}")
                st.markdown(f"🔗 [Documents]({app_details['info_link']})")

    with st.form(f"form_{applicant_name}"):
        st.markdown("### **Section 1: Research Quality**")
        q12a = st.radio("12a) Methods achievable?", ["Yes", "No"], index=get_radio_index(resp, "12a"), horizontal=True, disabled=is_locked)
        q12b = st.radio("12b) Relevant expertise?", ["Yes", "No"], index=get_radio_index(resp, "12b"), horizontal=True, disabled=is_locked)
        q12c = st.radio("12c) Risks identified?", ["Yes", "No"], index=get_radio_index(resp, "12c"), horizontal=True, disabled=is_locked)
        j13 = st.text_area("Justification (Research Quality)", value=resp.get("13", ""), disabled=is_locked)
        
        st.divider()
        st.markdown("### **Section 2: Potential Impact**")
        q14a = st.radio("14a) Important issue?", ["Yes", "No"], index=get_radio_index(resp, "14a"), horizontal=True, disabled=is_locked)
        q14b = st.radio("14b) Significant advancements?", ["Yes", "No"], index=get_radio_index(resp, "14b"), horizontal=True, disabled=is_locked)
        j15 = st.text_area("Justification (Impact)", value=resp.get("15", ""), disabled=is_locked)

        st.divider()
        st.markdown("### **Section 3: Innovation**")
        q16a = st.radio("16a) Novel approach?", ["Yes", "No"], index=get_radio_index(resp, "16a"), horizontal=True, disabled=is_locked)
        j17 = st.text_area("Justification (Innovation)", value=resp.get("17", ""), disabled=is_locked)

        st.divider()
        st.markdown("### **Section 4: Value for Money**")
        q18a = st.radio("18a) Funds essential?", ["Yes", "No"], index=get_radio_index(resp, "18a"), horizontal=True, disabled=is_locked)
        j19 = st.text_area("Justification (Value for Money)", value=resp.get("19", ""), disabled=is_locked)

        st.divider()
        st.markdown("### **Section 5: Final Recommendation**")
        current_fr = prev_data.get('final_recommendation') if prev_data else None
        fr_idx = 0 if current_fr == "Yes" else (1 if current_fr == "No" else None)
        q20 = st.radio("20) Recommend for further consideration?", ["Yes", "No"], index=fr_idx, horizontal=True, disabled=is_locked)
        j21 = st.text_area("Final justification", value=prev_data.get('overall_justification', "") if prev_data else "", disabled=is_locked)

        if not is_locked:
            c1, c2 = st.columns(2)
            if c1.form_submit_button("💾 Save Review", use_container_width=True):
                save_draft_logic(applicant_name, q12a, q12b, q12c, j13, q14a, q14b, j15, q16a, j17, q18a, j19, q20, j21)
            if c2.form_submit_button("Cancel", use_container_width=True):
                st.session_state.active_applicant = None
                st.rerun()

def save_draft_logic(app_name, q12a, q12b, q12c, j13, q14a, q14b, j15, q16a, j17, q18a, j19, q20, j21):
    resp_json = json.dumps({"12a":q12a, "12b":q12b, "12c":q12c, "13":j13, "14a":q14a, "14b":q14b, "15":j15, "16a":q16a, "17":j17, "18a":q18a, "19":j19})
    now = get_malaysia_time()
    with engine.begin() as conn:
        existing = conn.execute(text("SELECT id FROM reviews WHERE reviewer_username = :u AND applicant_name = :a"), {"u": st.session_state.username, "a": app_name}).fetchone()
        if existing:
            conn.execute(text("UPDATE reviews SET responses=:r, final_recommendation=:fr, overall_justification=:oj, updated_at=:t WHERE id=:id"), {"r": resp_json, "fr": q20, "oj": j21, "t": now, "id": existing[0]})
        else:
            conn.execute(text("INSERT INTO reviews (reviewer_username, applicant_name, responses, final_recommendation, overall_justification, submitted_at, updated_at) VALUES (:u, :a, :r, :fr, :oj, :t, :t)"), {"u": st.session_state.username, "a": app_name, "r": resp_json, "fr": q20, "oj": j21, "t": now})
    st.session_state.active_applicant = None
    st.rerun()

# --- 4. Main Page Logic ---
st.set_page_config(page_title="RBS Secure Review", layout="wide")

# Persistent State Init
if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if 'active_applicant' not in st.session_state: st.session_state.active_applicant = None
if 'final_locked' not in st.session_state: st.session_state.final_locked = False

# Cookie Handling (Safe Initialization)
cookie_manager = stx.CookieManager()
saved_user = cookie_manager.get(cookie="rbs_user")

# Auto-Login Logic
if saved_user and not st.session_state.authenticated:
    with engine.connect() as conn:
        res = conn.execute(text("SELECT role, full_name, profile_pic FROM users WHERE username = :u UNION SELECT 'Reviewer' as role, full_name, profile_pic FROM reviewers WHERE username = :u"), {"u": saved_user}).fetchone()
        if res:
            st.session_state.update({"authenticated": True, "username": saved_user, "role": res[0], "full_name": res[1], "pic": res[2]})

# --- LOGIN SCREEN ---
if not st.session_state.authenticated:
    st.title("🔐 RBS Grant Review Login")
    with st.form("login_form"):
        u, p = st.text_input("Username"), st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            with engine.connect() as conn:
                res = conn.execute(text("SELECT password_hash, role, full_name, profile_pic FROM users WHERE username = :u UNION SELECT password_hash, 'Reviewer' as role, full_name, profile_pic FROM reviewers WHERE username = :u"), {"u": u}).fetchone()
                if res and check_password(p, res[0]):
                    cookie_manager.set("rbs_user", u, expires_at=datetime.now() + timedelta(days=7))
                    st.session_state.update({"authenticated": True, "username": u, "role": res[1], "full_name": res[2], "pic": res[3]})
                    st.rerun()
                else: st.error("Invalid credentials.")
    st.stop()

# --- SIDEBAR & NAV ---
with st.sidebar:
    if st.session_state.pic: st.image(bytes(st.session_state.pic), width=100)
    st.title(f"{st.session_state.full_name}")
    nav_opts = ["Dashboard", "User Management", "Applicant Management"] if st.session_state.role == "Admin" else ["Review Form", "My Submissions"]
    menu = st.radio("Navigation", nav_opts)
    if st.button("Logout"):
        cookie_manager.delete("rbs_user"); st.session_state.clear(); st.rerun()

# --- CONTENT ROUTING ---
if menu == "Review Form":
    st.title("Review Portal")
    if st.session_state.active_applicant:
        name = st.session_state.active_applicant
        rev_data = pd.read_sql(text("SELECT * FROM reviews WHERE reviewer_username = :u AND applicant_name = :a"), engine, params={"u": st.session_state.username, "a": name})
        render_evaluation_form(name, rev_data.iloc[0].to_dict() if not rev_data.empty else None, is_locked=st.session_state.final_locked)
    else:
        apps = pd.read_sql("SELECT * FROM applicants", engine)
        my_revs = pd.read_sql(text("SELECT applicant_name FROM reviews WHERE reviewer_username = :u"), engine, params={"u": st.session_state.username})
        reviewed = my_revs['applicant_name'].tolist()
        
        cols = st.columns(3)
        for idx, row in apps.iterrows():
            with cols[idx % 3]:
                with st.container(border=True):
                    if row['photo']: st.image(bytes(row['photo']), use_container_width=True)
                    st.markdown(f"**{row['name']}**")
                    is_done = row['name'] in reviewed
                    st.markdown(f":{'green' if is_done else 'orange'}[● {'Draft Done' if is_done else 'Awaiting'}]")
                    if st.button("Review" if not is_done else "Edit", key=f"c_{row['id']}", use_container_width=True):
                        st.session_state.active_applicant = row['name']; st.rerun()
        
        if len(reviewed) >= len(apps) and not st.session_state.final_locked:
            st.divider()
            if st.button("🚀 FINAL SUBMIT ALL REVIEWS", type="primary", use_container_width=True):
                st.session_state.final_locked = True; st.balloons(); st.rerun()

elif menu == "My Submissions":
    st.header("📋 Review History")
    my_revs = pd.read_sql(text("SELECT r.*, a.proposal_title FROM reviews r LEFT JOIN applicants a ON r.applicant_name = a.name WHERE r.reviewer_username = :u ORDER BY r.submitted_at DESC"), engine, params={"u": st.session_state.username})
    for _, row in my_revs.iterrows():
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            c1.markdown(f"#### {row['applicant_name']}")
            c2.markdown(f"<h3 style='color:{'green' if row['final_recommendation'] == 'Yes' else 'red'}; text-align:right;'>{row['final_recommendation']}</h3>", unsafe_allow_html=True)
            st.write(f"**Proposal:** {row['proposal_title']}")
            st.info(row['overall_justification'] or "No justification provided.")
