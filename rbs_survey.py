import streamlit as st
import pandas as pd
import json
import plotly.express as px
from sqlalchemy import text
from database_utils import engine, init_db, check_password, hash_password, get_malaysia_time, delete_item
from form_components import render_evaluation_fields

# Initializing DB
init_db()

st.set_page_config(page_title="RBS Grant System", layout="wide")
if 'authenticated' not in st.session_state: st.session_state.authenticated = False

# --- Authentication ---
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
                else: 
                    st.error("Invalid credentials")
    st.stop()

# --- Sidebar ---
with st.sidebar:
    st.title(f"👤 {st.session_state.full_name}")
    st.write(f"Role: {st.session_state.role}")
    opts = ["Dashboard", "User Management", "Reviewer Management", "Applicant Management"] if st.session_state.role == "Admin" else ["Review Form", "My Submissions"]
    menu = st.radio("Navigation", opts)
    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

# --- Modules ---
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
            app_stats = df.groupby(['applicant_name', 'final_recommendation']).size().reset_index(name='count')
            fig2 = px.bar(app_stats, x='applicant_name', y='count', color='final_recommendation', title="Applicant Analysis", barmode='group')
            st.plotly_chart(fig2)
        
        st.subheader("📋 Master Reviewer Results Table")
        st.dataframe(df, use_container_width=True)
    else: 
        st.info("No data yet.")

elif menu in ["User Management", "Reviewer Management", "Applicant Management"]:
    table = menu.split(" ")[0].lower() + "s"
    st.header(f"⚙️ {menu}")
    
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

    data = pd.read_sql(f"SELECT * FROM {table}", engine)
    for _, row in data.iterrows():
        with st.container(border=True):
            e_col1, e_col2, e_col3 = st.columns([1, 4, 2])
            if table == "applicants" and row['photo']: 
                e_col1.image(bytes(row['photo']), width=100)
            e_col2.write(f"**ID:** {row['id']} | **Name:** {row['name'] if table=='applicants' else row['username']}")
            
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
                with engine.begin() as conn:
                    if not rev.empty:
                        conn.execute(text("UPDATE reviews SET responses=:r, final_recommendation=:fr, overall_justification=:oj, updated_at=:t WHERE id=:id"), 
                                     {"r":json.dumps(res["responses"]), "fr":res["recommendation"], "oj":res["justification"], "t":get_malaysia_time(), "id":int(rev.iloc[0]['id'])})
                    else:
                        conn.execute(text("INSERT INTO reviews (reviewer_username, applicant_name, responses, final_recommendation, overall_justification, submitted_at, updated_at) VALUES (:u, :a, :r, :fr, :oj, :t, :t)"), 
                                     {"u":st.session_state.username, "a":name, "r":json.dumps(res["responses"]), "fr":res["recommendation"], "oj":res["justification"], "t":get_malaysia_time()})
                st.session_state.active_review_app = None
                st.rerun()
        
        if st.button("⬅️ Back to Gallery", use_container_width=True):
            st.session_state.active_review_app = None
            st.rerun()

    else:
        # --- Gallery View ---
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
                                st.markdown("**Status:** :green[✅ Saved]")
                            else:
                                st.markdown("**Status:** :orange[⏳ Pending]")
                            if st.button("Review", key=f"go_{row['id']}", use_container_width=True, disabled=is_locked):
                                st.session_state.active_review_app = row['name']
                                st.rerun()

        if not is_locked and len(reviews_lookup) >= len(apps) > 0:
            if st.button("🚀 FINAL SUBMIT ALL", type="primary", use_container_width=True):
                with engine.begin() as conn:
                    conn.execute(text("UPDATE reviews SET is_final = TRUE WHERE reviewer_username = :u"), {"u": st.session_state.username})
                st.balloons(); st.rerun()

elif menu == "My Submissions":
    st.header("📋 My Saved Submissions")
    my_revs = pd.read_sql(text("SELECT r.*, a.photo FROM reviews r JOIN applicants a ON r.applicant_name = a.name WHERE r.reviewer_username = :u"), engine, params={"u": st.session_state.username})
    if my_revs.empty:
        st.info("You haven't saved any reviews yet.")
    else:
        for _, row in my_revs.iterrows():
            with st.container(border=True):
                s1, s2 = st.columns([1, 5])
                if row['photo']: s1.image(bytes(row['photo']), use_container_width=True)
                s2.write(f"### {row['applicant_name']}")
                s2.write(f"**Recommendation:** {row['final_recommendation']}")
                s2.info(f"**Justification:** {row['overall_justification']}")

