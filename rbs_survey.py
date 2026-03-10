import streamlit as st
import pandas as pd
import bcrypt
import json
from sqlalchemy import create_engine, text
import plotly.express as px
from datetime import datetime, timedelta, timezone

# --- 1. Database & Helpers ---
DB_URL = st.secrets["DATABASE_URL"]

@st.cache_resource
def get_engine():
    # Pooling prevents the "slowness" by keeping connections ready
    return create_engine(
        DB_URL, 
        pool_size=10, 
        max_overflow=20, 
        pool_pre_ping=True
    )

engine = get_engine()
# -- engine = create_engine(DB_URL) --

def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed):
    try: return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except: return False

def get_malaysia_time():
    my_tz = timezone(timedelta(hours=8))
    return datetime.now(my_tz).strftime('%Y-%m-%d %H:%M:%S')

def get_radio_index(prev_dict, key):
    if not prev_dict: return None
    val = prev_dict.get(key)
    return 0 if val == "Yes" else (1 if val == "No" else None)

def delete_item(table, item_id):
    with engine.begin() as conn:
        conn.execute(text(f"DELETE FROM {table} WHERE id = :id"), {"id": item_id})
    st.toast(f"Item deleted from {table}")
    st.rerun()

# --- 2. Database Schema (Maintained) ---
@st.cache_resource
def init_db():
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
        # Check for default admin
        res = conn.execute(text("SELECT COUNT(*) FROM users")).fetchone()[0]
        if res == 0:
            conn.execute(text("INSERT INTO users (username, full_name, role, password_hash) VALUES ('admin', 'Master Admin', 'Admin', :pw)"), 
                         {"pw": hash_password("Admin123!")})
    return True

# --- 3. Shared Form Component (Strict Question Set) ---
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
            # Setting index=None forces the user to pick an option (Mandatory)
            current_idx = get_radio_index(prev_resp, code)
            responses[code] = st.radio(
                f"{label} *", 
                ["Yes", "No"], 
                index=current_idx, 
                horizontal=True, 
                disabled=disabled, 
                key=f"q{code}"
            )
        
        # Justification remains optional
        j_key = str(int(code[:2]) + 1) 
        responses[j_key] = st.text_area(f"Justification ({title})", value=prev_resp.get(j_key, ""), disabled=disabled, key=f"j{j_key}")
        st.divider()

    st.subheader("Section 5 — Final Recommendation")
    fr_val = prev_data.get('final_recommendation')
    
    # Mandatory Final Recommendation
    q20 = st.radio(
        "Considering the evaluations made above, do you recommend this application for further consideration? *", 
        ["Yes", "No"], 
        index=(0 if fr_val=="Yes" else (1 if fr_val=="No" else None)), 
        horizontal=True, 
        disabled=disabled
    )
    j21 = st.text_area("Final justification", value=prev_data.get('overall_justification', ""), disabled=disabled)
    
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
                    st.session_state.update({"authenticated": True, "username": u, "role": res[1], "full_name": res[2], "menu_choice": "Dashboard"})
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
        met2.metric("Completed (Final)", len(df[df['is_final'] == True]))
        met3.metric("Approval Rate", f"{(len(df[df['final_recommendation']=='Yes'])/len(df)*100):.1f}%")
        
        st.divider()
        c_a, c_b = st.columns(2)
        with c_a:
            fig1 = px.pie(df, names='final_recommendation', title="Overall Recommendation Split", color_discrete_map={"Yes":"#2ecc71","No":"#e74c3c"})
            st.plotly_chart(fig1)
        with c_b:
            # Upgrade 1: Applicant Analysis
            app_stats = df.groupby(['applicant_name', 'final_recommendation']).size().reset_index(name='count')
            fig2 = px.bar(app_stats, x='applicant_name', y='count', color='final_recommendation', title="Applicant Analysis", barmode='group')
            st.plotly_chart(fig2)
        
        st.subheader("📋 Master Reviewer Results Table")
        st.dataframe(df, use_container_width=True)
    else: st.info("No data yet.")

elif menu in ["User Management", "Reviewer Management", "Applicant Management"]:
    table = menu.split(" ")[0].lower() + "s"
    st.header(f"⚙️ {menu}")
    
    # Create Section
    with st.expander(f"➕ Add New {menu[:-1]}"):
        with st.form(f"add_{table}"):
            if table == "applicants":
                n, t, l = st.text_input("Name"), st.text_area("Title"), st.text_input("Link")
                p = st.file_uploader("Photo", type=['png', 'jpg'])
            else:
                un, fn, pw = st.text_input("Username"), st.text_input("Full Name"), st.text_input("Password", type="password")
            if st.form_submit_button("Save"):
                with engine.begin() as conn:
                    if table == "applicants":
                        conn.execute(text("INSERT INTO applicants (name, proposal_title, info_link, photo) VALUES (:n, :t, :l, :p)"), {"n":n,"t":t,"l":l,"p":p.getvalue() if p else None})
                    else:
                        conn.execute(text(f"INSERT INTO {table} (username, full_name, role, password_hash) VALUES (:u, :fn, 'Admin', :p)") if table == 'users' else text(f"INSERT INTO {table} (username, full_name, password_hash) VALUES (:u, :fn, :p)"), {"u":un, "fn":fn, "p":hash_password(pw)})
                st.rerun()

    # Upgrade 2: Edit Logic for all modules
    data = pd.read_sql(f"SELECT * FROM {table}", engine)
    for _, row in data.iterrows():
        with st.container(border=True):
            e_col1, e_col2, e_col3 = st.columns([1, 4, 2])
            if table == "applicants" and row['photo']: e_col1.image(bytes(row['photo']), width=100)
            e_col2.write(f"**ID:** {row['id']} | **Name:** {row['name'] if table=='applicants' else row['username']}")
            
            # Edit Button Logic
            with e_col3.expander("📝 Edit Details"):
                with st.form(f"edit_{table}_{row['id']}"):
                    if table == "applicants":
                        new_n = st.text_input("Name", value=row['name'])
                        new_t = st.text_area("Title", value=row['proposal_title'])
                        new_l = st.text_input("Link", value=row['info_link'])
                        new_p = st.file_uploader("Update Photo", type=['png', 'jpg'])
                        if st.form_submit_button("Update Applicant"):
                            p_data = new_p.getvalue() if new_p else row['photo']
                            with engine.begin() as conn:
                                conn.execute(text("UPDATE applicants SET name=:n, proposal_title=:t, info_link=:l, photo=:p WHERE id=:id"), {"n":new_n,"t":new_t,"l":new_l,"p":p_data, "id":row['id']})
                            st.rerun()
                    else:
                        new_fn = st.text_input("Full Name", value=row['full_name'])
                        new_pw = st.text_input("New Password (Leave blank to keep)", type="password")
                        if st.form_submit_button("Update User"):
                            with engine.begin() as conn:
                                if new_pw:
                                    conn.execute(text(f"UPDATE {table} SET full_name=:fn, password_hash=:p WHERE id=:id"), {"fn":new_fn, "p":hash_password(new_pw), "id":row['id']})
                                else:
                                    conn.execute(text(f"UPDATE {table} SET full_name=:fn WHERE id=:id"), {"fn":new_fn, "id":row['id']})
                            st.rerun()
            
            if e_col3.button("🗑️ Delete", key=f"del_{table}_{row['id']}", use_container_width=True):
                delete_item(table, row['id'])
                
elif menu == "Review Form":
    st.markdown("## 📋 Dr Ranjeet Bhagwan Singh Medical Research Grant: Shortlisting Review Form")
    # -- st.title("📋 Dr Ranjeet Bhagwan Singh Medical Research Grant: Shortlisting Review Form ") --
    # --st.subheader(f"Welcome, {st.session_state.full_name}!")--
    # --- New Instructions Section ---
    st.info("""
    The Dr Ranjeet Bhagwan Singh Medical Research Grant (RBS Grant) supports outstanding early-career researchers in Malaysia conducting innovative and impactful medical research. 
    This shortlisting review form is to evaluate applications based on key criteria.
    
    **Instructions:**
    Reviewers can access the applicants' information and supporting documents via the 'View Documents' Link provided in the applicant detail. 
    Please refer to **Sheet 1: Summary** (the OneDrive link is provided in the table assigned to your name) before completing this form. 
    Kindly review all materials thoroughly before making your recommendation.
    """)
    st.divider()
    # 2. Modern Avatar Welcome Card
    with st.container(border=True):
        col_icon, col_greet = st.columns([1, 10])
        with col_icon:
            # Using a clean, professional researcher/medical avatar icon
            st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=65)
        with col_greet:
            st.markdown(f"### Welcome back, {st.session_state.full_name}!")
            st.caption(f"🔬 Logged in as: {st.session_state.username} | Role: Reviewer")
            # -- st.markdown("🔬 *You are authorized to evaluate early-career medical research applications.*") --
    # Check if the reviewer has already finalized their entire batch
    is_locked = pd.read_sql(text("SELECT COUNT(*) FROM reviews WHERE reviewer_username = :u AND is_final = TRUE"), engine, params={"u": st.session_state.username}).iloc[0,0] > 0

    if st.session_state.get('active_review_app'):
        # --- INDIVIDUAL REVIEW PAGE ---
        name = st.session_state.active_review_app
        app = pd.read_sql(text("SELECT * FROM applicants WHERE name = :n"), engine, params={"n": name}).iloc[0]
        rev = pd.read_sql(text("SELECT * FROM reviews WHERE reviewer_username = :u AND applicant_name = :a"), engine, params={"u": st.session_state.username, "a": name})
        prev_resp = json.loads(rev.iloc[0]['responses']) if not rev.empty else None

        with st.container(border=True):
            col_img, col_txt = st.columns([1, 4])
            with col_img:
                if app['photo']: 
                    st.image(bytes(app['photo']), width=150, caption="Passport Size (Click to Zoom)")
            with col_txt:
                st.subheader(name)
                st.write(f"**Proposal:** {app['proposal_title']}")
                st.markdown(f"🔗 [View Documents]({app['info_link']})")

        with st.form("eval_form"):
            # Uses your strict 4-section question engine
            res = render_evaluation_fields(prev_resp, rev.iloc[0].to_dict() if not rev.empty else {}, disabled=is_locked)
            
if not is_locked and st.form_submit_button("💾 Save Draft", use_container_width=True, type="primary"):
    # VALIDATION: List of all mandatory Yes/No codes
    mandatory_codes = ["12a", "12b", "12c", "14a", "14b", "16a", "18a"]
    
    # Check if any radio button returned None (not selected)
    is_incomplete = any(res["responses"][c] is None for c in mandatory_codes) or res["recommendation"] is None
    
    if is_incomplete:
        st.error("⚠️ Please answer all mandatory questions marked with an asterisk (*) before saving.")
    else:
        with engine.begin() as conn:
            # ... (Existing database Save/Update code) ...
            if not rev.empty:
                conn.execute(text("UPDATE reviews SET responses=:r, final_recommendation=:fr, overall_justification=:oj, updated_at=:t WHERE id=:id"), 
                             {"r":json.dumps(res["responses"]), "fr":res["recommendation"], "oj":res["justification"], "t":get_malaysia_time(), "id":int(rev.iloc[0]['id'])})
            else:
                conn.execute(text("INSERT INTO reviews (reviewer_username, applicant_name, responses, final_recommendation, overall_justification, submitted_at, updated_at) VALUES (:u, :a, :r, :fr, :oj, :t, :t)"), 
                             {"u":st.session_state.username, "a":name, "r":json.dumps(res["responses"]), "fr":res["recommendation"], "oj":res["justification"], "t":get_malaysia_time()})
        st.session_state.active_review_app = None
        st.rerun()

          else:
        # --- APPLICANT GALLERY VIEW ---
        apps = pd.read_sql("SELECT * FROM applicants", engine)
        # Fetch existing reviews to show Recommendation and Justification on the card
        rev_records = pd.read_sql(text("SELECT applicant_name, final_recommendation, overall_justification FROM reviews WHERE reviewer_username = :u"), engine, params={"u": st.session_state.username})
        
        # Create a lookup dictionary for quick access
        reviews_lookup = rev_records.set_index('applicant_name').to_dict('index')
        
        st.subheader("Applicant Gallery")
        for i in range(0, len(apps), 4):
            cols = st.columns(4)
            for j in range(4):
                if i+j < len(apps):
                    row = apps.iloc[i+j]
                    with cols[j]:
                        with st.container(border=True):
                            # Passport Photo
                            if row['photo']: st.image(bytes(row['photo']), use_container_width=True)
                            else: st.image("https://cdn-icons-png.flaticon.com/512/149/149071.png", use_container_width=True)
                            
                            st.write(f"**{row['name']}**")
                            
                            # Show Status, Recommendation, and Last Justification
                            if row['name'] in reviews_lookup:
                                rev_data = reviews_lookup[row['name']]
                                rec = rev_data['final_recommendation']
                                color = "green" if rec == "Yes" else "red"
                                
                                st.markdown(f"**Status:** :green[✅ Saved]")
                                st.markdown(f"**Final Recommendation:** :{color}[{rec}]")
                                
                                # Show snippet of the last justification
                                justification = rev_data['overall_justification'] or "No text provided."
                                # Limit text to 80 characters for the card view
                                st.caption(f"💬**Final justification:**  {justification[:80]}{'...' if len(justification) > 80 else ''}")
                            else:
                                st.markdown("**Status:** :orange[⏳ Awaiting Review]")
                                st.caption("No justification saved yet.")
                            
                            if st.button("Review/Edit", key=f"go_{row['id']}", use_container_width=True, disabled=is_locked):
                                st.session_state.active_review_app = row['name']
                                st.rerun()

        # Final Batch Submission logic
        if not is_locked and len(reviews_lookup) >= len(apps) > 0:
            st.divider()
            if st.button("🚀 FINAL SUBMIT ALL REVIEWS", type="primary", use_container_width=True):
                with engine.begin() as conn:
                    conn.execute(text("UPDATE reviews SET is_final = TRUE WHERE reviewer_username = :u"), {"u": st.session_state.username})
                st.balloons()
                st.rerun()

elif menu == "My Submissions":
    # Upgrade 4: Submissions with Photos and Justification
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





