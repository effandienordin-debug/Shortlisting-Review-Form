import streamlit as st
import pandas as pd
import bcrypt
import json
from sqlalchemy import create_engine, text
import plotly.express as px
from datetime import datetime, timedelta, timezone

# --- 1. Database & Helpers ---
DB_URL = st.secrets["DATABASE_URL"]
engine = create_engine(DB_URL)

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
    if not prev_dict: 
        return None
    val = prev_dict.get(key)
    return 0 if val == "Yes" else (1 if val == "No" else None)

def delete_item(table, item_id):
    with engine.begin() as conn:
        conn.execute(text(f"DELETE FROM {table} WHERE id = :id"), {"id": item_id})
    st.toast(f"Item deleted from {table}")
    st.rerun()

# --- 2. Database Schema ---
with engine.begin() as conn:
    conn.execute(text("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username VARCHAR(255) UNIQUE, full_name VARCHAR(255), password_hash VARCHAR(255), role VARCHAR(50))"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS reviewers (id SERIAL PRIMARY KEY, username VARCHAR(255) UNIQUE, full_name VARCHAR(255), password_hash VARCHAR(255))"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS applicants (id SERIAL PRIMARY KEY, name VARCHAR(255) UNIQUE, proposal_title TEXT, info_link TEXT, photo BYTEA)"))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS reviews (
            id SERIAL PRIMARY KEY, reviewer_username VARCHAR(255), applicant_name VARCHAR(255), 
            responses TEXT, final_recommendation VARCHAR(50), overall_justification TEXT, 
            submitted_at TIMESTAMP, updated_at TIMESTAMP, is_final BOOLEAN DEFAULT FALSE
        )
    """))
    if conn.execute(text("SELECT COUNT(*) FROM users")).fetchone()[0] == 0:
        conn.execute(text("INSERT INTO users (username, full_name, role, password_hash) VALUES ('admin', 'Master Admin', 'Admin', :pw)"), {"pw": hash_password("Admin123!")})

# --- 3. Shared Form Component ---
def render_evaluation_fields(prev_resp=None, prev_data=None, disabled=False):
    if prev_resp is None: prev_resp = {}
    if prev_data is None: prev_data = {}

    sections = [
        ("Section 1 — Research Quality and Feasibility", [
            ("12a", "Are the proposed methods and objectives appropriate and achievable within the grant period (2 years)?"), 
            ("12b", "Does the applicant have relevant expertise and a strong research track record?"), 
            ("12c", "Have potential risks been identified, and are there plans to address them?")
        ]),
        ("Section 2 — Potential Impact", [
            ("14a", "Does the research address an important issue in medical science?"), 
            ("14b", "Does it have the potential to contribute to significant advancements in the medical field?")
        ]),
        ("Section 3 — Innovation and Novelty", [
            ("16a", "Does the research propose a novel approach or methodology?")
        ]),
        ("Section 4 — Value for Money", [
            ("18a", "Are the requested funds essential and appropriately allocated based on the importance of the research?")
        ]),
    ]

    responses = {}
    for title, qs in sections:
        st.subheader(title)
        for code, label in qs:
            current_idx = get_radio_index(prev_resp, code)
            responses[code] = st.radio(f"{label} *", ["Yes", "No"], index=current_idx, horizontal=True, disabled=disabled, key=f"q{code}")
        
        j_key = str(int(code[:2]) + 1) 
        responses[j_key] = st.text_area(f"Justification ({title})", value=prev_resp.get(j_key, ""), disabled=disabled, key=f"j{j_key}", placeholder="Optional reasoning...")
        st.divider()

    st.subheader("Section 5 — Final Recommendation")
    fr_val = prev_data.get('final_recommendation')
    q20 = st.radio("Considering the evaluations made above, do you recommend this application? *", ["Yes", "No"], index=(0 if fr_val=="Yes" else (1 if fr_val=="No" else None)), horizontal=True, disabled=disabled)
    j21 = st.text_area("Final justification", value=prev_data.get('overall_justification', ""), disabled=disabled, placeholder="Overall remarks...")
    
    return {"responses": responses, "recommendation": q20, "justification": j21}

# --- 4. App Setup & Auth ---
st.set_page_config(page_title="RBS Grant System", layout="wide")
if 'authenticated' not in st.session_state: st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 RBS Login")
    with st.form("login"):
        u, p = st.text_input("Username"), st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            with engine.connect() as conn:
                res = conn.execute(text("SELECT password_hash, 'Admin' as role, full_name FROM users WHERE username = :u UNION SELECT password_hash, 'Reviewer' as role, full_name FROM reviewers WHERE username = :u"), {"u": u}).fetchone()
                if res and check_password(p, res[0]):
                    st.session_state.update({"authenticated": True, "username": u, "role": res[1], "full_name": res[2]})
                    st.rerun()
                else: st.error("Invalid credentials")
    st.stop()

# --- 5. Sidebar ---
with st.sidebar:
    st.title(f"👤 {st.session_state.full_name}")
    st.write(f"Role: {st.session_state.role}")
    opts = ["Dashboard", "User Management", "Reviewer Management", "Applicant Management"] if st.session_state.role == "Admin" else ["Review Form", "My Submissions"]
    menu = st.radio("Navigation", opts)
    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

# --- 6. Modules ---
if menu == "Dashboard":
    st.header("📊 System Analytics")
    df = pd.read_sql("SELECT reviewer_username, applicant_name, final_recommendation, is_final FROM reviews", engine)
    if not df.empty:
        met1, met2, met3 = st.columns(3)
        met1.metric("Total Reviews", len(df))
        met2.metric("Completed", len(df[df['is_final'] == True]))
        met3.metric("Approval Rate", f"{(len(df[df['final_recommendation']=='Yes'])/len(df)*100):.1f}%")
        st.dataframe(df, use_container_width=True)
    else: st.info("No data yet.")

elif menu in ["User Management", "Reviewer Management", "Applicant Management"]:
    table = menu.split(" ")[0].lower() + "s"
    st.header(f"⚙️ {menu}")
    # (Note: Standard Add/Edit logic as per your snippet here...)

elif menu == "Review Form":
    st.markdown("## 📋 Dr Ranjeet Bhagwan Singh Medical Research Grant: Shortlisting Review Form")
    st.info("The RBS Grant supports outstanding early-career researchers in Malaysia... (Please refer to Sheet 1: Summary before completing this form).")
    
    with st.container(border=True):
        col_icon, col_greet = st.columns([1, 10])
        col_icon.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=65)
        col_greet.markdown(f"### Welcome back, {st.session_state.full_name}!")
        col_greet.caption(f"🔬 Logged in as: {st.session_state.username} | Role: Reviewer")

    is_locked = pd.read_sql(text("SELECT COUNT(*) FROM reviews WHERE reviewer_username = :u AND is_final = TRUE"), engine, params={"u": st.session_state.username}).iloc[0,0] > 0

    if st.session_state.get('active_review_app'):
        # --- INDIVIDUAL REVIEW PAGE ---
        name = st.session_state.active_review_app
        app = pd.read_sql(text("SELECT * FROM applicants WHERE name = :n"), engine, params={"n": name}).iloc[0]
        rev = pd.read_sql(text("SELECT * FROM reviews WHERE reviewer_username = :u AND applicant_name = :a"), engine, params={"u": st.session_state.username, "a": name})
        prev_resp = json.loads(rev.iloc[0]['responses']) if not rev.empty else None

        if st.button("⬅️ Back to Gallery", key="top_back"):
            st.session_state.active_review_app = None
            st.rerun()

        with st.form("eval_form"):
            res = render_evaluation_fields(prev_resp, rev.iloc[0].to_dict() if not rev.empty else {}, disabled=is_locked)
            if not is_locked:
                if st.form_submit_button("💾 Save Draft & Return to Gallery", use_container_width=True, type="primary"):
                    mandatory_codes = ["12a", "12b", "12c", "14a", "14b", "16a", "18a"]
                    if any(res["responses"][c] is None for c in mandatory_codes) or res["recommendation"] is None:
                        st.error("⚠️ Please answer all mandatory questions marked with *")
                    else:
                        with engine.begin() as conn:
                            if not rev.empty:
                                conn.execute(text("UPDATE reviews SET responses=:r, final_recommendation=:fr, overall_justification=:oj, updated_at=:t WHERE id=:id"), {"r":json.dumps(res["responses"]), "fr":res["recommendation"], "oj":res["justification"], "t":get_malaysia_time(), "id":int(rev.iloc[0]['id'])})
                            else:
                                conn.execute(text("INSERT INTO reviews (reviewer_username, applicant_name, responses, final_recommendation, overall_justification, submitted_at, updated_at) VALUES (:u, :a, :r, :fr, :oj, :t, :t)"), {"u":st.session_state.username, "a":name, "r":json.dumps(res["responses"]), "fr":res["recommendation"], "oj":res["justification"], "t":get_malaysia_time()})
                        st.session_state.active_review_app = None
                        st.rerun()
    else:
        # --- GALLERY VIEW ---
        apps = pd.read_sql("SELECT * FROM applicants", engine)
        rev_records = pd.read_sql(text("SELECT applicant_name, final_recommendation, overall_justification FROM reviews WHERE reviewer_username = :u"), engine, params={"u": st.session_state.username})
        reviews_lookup = rev_records.set_index('applicant_name').to_dict('index')
        
        st.subheader("Applicant Gallery")
        for i in range(0, len(apps), 4):
            cols = st.columns(4)
            for j in range(4):
                if i+j < len(apps):
                    row = apps.iloc[i+j]
                    with cols[j]:
                        with st.container(border=True):
                            if row['photo']: st.image(bytes(row['photo']), use_container_width=True)
                            st.write(f"**{row['name']}**")
                            if row['name'] in reviews_lookup:
                                r_data = reviews_lookup[row['name']]
                                color = "green" if r_data['final_recommendation'] == "Yes" else "red"
                                st.markdown(f"**Status:** :green[✅ Saved]")
                                st.markdown(f"**Rec:** :{color}[{r_data['final_recommendation']}]")
                            else:
                                st.markdown("**Status:** :orange[⏳ Pending]")
                            if st.button("Review/Edit", key=f"go_{row['id']}", use_container_width=True, disabled=is_locked):
                                st.session_state.active_review_app = row['name']
                                st.rerun()

elif menu == "My Submissions":
    st.header("📋 My Saved Submissions")
my_revs = pd.read_sql(text("""
    SELECT r.*, a.photo 
    FROM reviews r 
    JOIN applicants a ON r.applicant_name = a.name 
    WHERE r.reviewer_username = :u
"""), engine, params={"u": st.session_state.username})

if my_revs.empty:
    st.info("You haven't saved any reviews yet.")
else:
    for _, row in my_revs.iterrows():
        with st.container(border=True):
            sub1, sub2 = st.columns([1, 5])
            if row['photo']: sub1.image(bytes(row['photo']), use_container_width=True)
            sub2.write(f"### {row['applicant_name']}")
            sub2.write(f"**Final Recommendation:** {row['final_recommendation']}")
            sub2.info(f"**Final justification:** {row['overall_justification']}")











