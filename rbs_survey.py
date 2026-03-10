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

# --- 2. Helper Functions (Must be before Database Setup) ---
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

# --- 3. Database Schema Self-Healing & Auto-Setup ---
with engine.begin() as conn:
    # Admins Table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) UNIQUE,
            full_name VARCHAR(255),
            email VARCHAR(255),
            password_hash VARCHAR(255),
            role VARCHAR(50),
            profile_pic BYTEA
        )
    """))
    # Reviewers Table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS reviewers (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) UNIQUE,
            full_name VARCHAR(255),
            email VARCHAR(255),
            password_hash VARCHAR(255),
            profile_pic BYTEA
        )
    """))
    # Applicants Table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS applicants (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) UNIQUE,
            proposal_title TEXT,
            info_link TEXT,
            photo BYTEA
        )
    """))
    conn.execute(text("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS photo BYTEA"))
    
    # Reviews Table
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
    conn.execute(text("ALTER TABLE reviews ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP"))

    # 🚀 AUTO-CREATE DEFAULT ADMIN IF NONE EXISTS
    user_count = conn.execute(text("SELECT COUNT(*) FROM users")).fetchone()[0]
    if user_count == 0:
        default_admin_pw = hash_password("Admin123!")
        conn.execute(text("""
            INSERT INTO users (username, full_name, email, password_hash, role) 
            VALUES ('admin', 'Master Admin', 'admin@system.com', :pw, 'Admin')
        """), {"pw": default_admin_pw})

# --- 4. Popup Dialogs ---

# Admin Dialogs
@st.dialog("Edit Admin Information")
def edit_user_dialog(user_id, current_fn, current_un, current_em):
    new_fn = st.text_input("Full Name", current_fn)
    new_un = st.text_input("Username", current_un)
    new_em = st.text_input("Email (Optional)", current_em if pd.notna(current_em) else "")
    new_pw = st.text_input("New Password (Leave blank to keep current)", type="password")
    new_img = st.file_uploader("Update Profile Picture", type=['jpg', 'png'], key="img_u")
    
    if st.button("Save Changes"):
        if not new_fn.strip() or not new_un.strip():
            st.warning("Full Name and Username cannot be blank.")
            return
            
        img_data = new_img.getvalue() if new_img else None
        
        with engine.begin() as conn:
            updates = ["full_name=:fn", "username=:un", "email=:em"]
            params = {"fn": new_fn, "un": new_un, "em": new_em, "id": int(user_id)}
            if new_pw:
                updates.append("password_hash=:pw")
                params["pw"] = hash_password(new_pw)
            if img_data:
                updates.append("profile_pic=:p")
                params["p"] = img_data
                
            query = f"UPDATE users SET {', '.join(updates)} WHERE id=:id"
            conn.execute(text(query), params)
            
        st.session_state.success_msg = "Admin successfully updated!"
        st.rerun()

@st.dialog("Confirm Deletion")
def confirm_delete_user(user_id, username_str):
    st.warning(f"Are you sure you want to delete Admin **{username_str}**? This action cannot be undone.")
    c1, c2 = st.columns(2)
    if c1.button("Yes, Delete", type="primary"):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id=:id"), {"id": int(user_id)})
        st.session_state.success_msg = f"Admin {username_str} has been deleted."
        st.rerun()
    if c2.button("Cancel"):
        st.rerun()

# Reviewer Dialogs
@st.dialog("Edit Reviewer Information")
def edit_reviewer_dialog(rev_id, current_fn, current_un, current_em):
    new_fn = st.text_input("Full Name", current_fn)
    new_un = st.text_input("Username", current_un)
    new_em = st.text_input("Email (Optional)", current_em if pd.notna(current_em) else "")
    new_pw = st.text_input("New Password (Leave blank to keep current)", type="password")
    new_img = st.file_uploader("Update Profile Picture", type=['jpg', 'png'], key="img_r")
    
    if st.button("Save Changes"):
        if not new_fn.strip() or not new_un.strip():
            st.warning("Full Name and Username cannot be blank.")
            return
            
        img_data = new_img.getvalue() if new_img else None
        
        with engine.begin() as conn:
            updates = ["full_name=:fn", "username=:un", "email=:em"]
            params = {"fn": new_fn, "un": new_un, "em": new_em, "id": int(rev_id)}
            if new_pw:
                updates.append("password_hash=:pw")
                params["pw"] = hash_password(new_pw)
            if img_data:
                updates.append("profile_pic=:p")
                params["p"] = img_data
                
            query = f"UPDATE reviewers SET {', '.join(updates)} WHERE id=:id"
            conn.execute(text(query), params)
            
        st.session_state.success_msg = "Reviewer successfully updated!"
        st.rerun()

@st.dialog("Confirm Deletion")
def confirm_delete_reviewer(rev_id, username_str):
    st.warning(f"Are you sure you want to delete Reviewer **{username_str}**? This action cannot be undone.")
    c1, c2 = st.columns(2)
    if c1.button("Yes, Delete", type="primary"):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM reviewers WHERE id=:id"), {"id": int(rev_id)})
        st.session_state.success_msg = f"Reviewer {username_str} has been deleted."
        st.rerun()
    if c2.button("Cancel"):
        st.rerun()

# Applicant Dialogs
@st.dialog("Edit Applicant Record")
def edit_app_dialog(app_id, current_n, current_t, current_l):
    new_n = st.text_input("Name", current_n)
    new_t = st.text_area("Proposal Title", current_t)
    new_l = st.text_input("Information Link", current_l)
    new_photo = st.file_uploader("Update Applicant Photo", type=['jpg', 'png'])
    
    if st.button("Update Applicant"):
        if not new_n.strip() or not new_t.strip() or not new_l.strip():
            st.warning("Name, Proposal Title, and Link cannot be blank.")
            return
            
        photo_data = new_photo.getvalue() if new_photo else None
        with engine.begin() as conn:
            if photo_data:
                conn.execute(text("UPDATE applicants SET name=:n, proposal_title=:t, info_link=:l, photo=:p WHERE id=:id"),
                         {"n": new_n, "t": new_t, "l": new_l, "p": photo_data, "id": int(app_id)})
            else:
                conn.execute(text("UPDATE applicants SET name=:n, proposal_title=:t, info_link=:l WHERE id=:id"),
                         {"n": new_n, "t": new_t, "l": new_l, "id": int(app_id)})
                         
        st.session_state.success_msg = "Applicant successfully updated!"
        st.rerun()

@st.dialog("Confirm Deletion")
def confirm_delete_app(app_id, app_name):
    st.warning(f"Are you sure you want to delete **{app_name}**? This action cannot be undone.")
    c1, c2 = st.columns(2)
    if c1.button("Yes, Delete", type="primary"):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM applicants WHERE id=:id"), {"id": int(app_id)})
        st.session_state.success_msg = f"Applicant {app_name} has been deleted."
        st.rerun()
    if c2.button("Cancel"):
        st.rerun()

# Review Form Dialog
@st.dialog("Edit Evaluation Form", width="large")
def edit_review_dialog(edit_data):
    st.info(f"Editing Review for **{edit_data['applicant_name']}**")
    prev_resp = json.loads(edit_data['responses']) if edit_data['responses'] else {}

    with st.form("edit_rbs_full_form"):
        st.subheader("Research Quality and Feasibility")
        q12a = st.radio("a) Are the proposed methods and objectives appropriate and achievable within the grant period (2 years)?", ["Yes", "No"], index=get_radio_index(prev_resp, "12a"), horizontal=True)
        q12b = st.radio("b) Does the applicant have relevant expertise and a strong research track record?", ["Yes", "No"], index=get_radio_index(prev_resp, "12b"), horizontal=True)
        q12c = st.radio("c) Have potential risks been identified, and are there plans to address them?", ["Yes", "No"], index=get_radio_index(prev_resp, "12c"), horizontal=True)
        j13_val = prev_resp.get("13") if prev_resp.get("13") is not None else ""
        j13 = st.text_area("Justification (if any)", value=j13_val)

        st.subheader("Potential Impact")
        q14a = st.radio("a) Does the research address an important issue in medical science?", ["Yes", "No"], index=get_radio_index(prev_resp, "14a"), horizontal=True)
        q14b = st.radio("b) Does it have the potential to contribute to significant advancements in the medical field?", ["Yes", "No"], index=get_radio_index(prev_resp, "14b"), horizontal=True)
        j15_val = prev_resp.get("15") if prev_resp.get("15") is not None else ""
        j15 = st.text_area("Justification (if any) ", value=j15_val, key="e_j15")

        st.subheader("Innovation and Novelty")
        q16a = st.radio("a) Does the research propose a novel approach or methodology?", ["Yes", "No"], index=get_radio_index(prev_resp, "16a"), horizontal=True)
        j17_val = prev_resp.get("17") if prev_resp.get("17") is not None else ""
        j17 = st.text_area("Justification (if any) ", value=j17_val, key="e_j17")

        st.subheader("Value for Money")
        q18a = st.radio("a) Are the requested funds essential and appropriately allocated based on the importance of the research?", ["Yes", "No"], index=get_radio_index(prev_resp, "18a"), horizontal=True)
        j19_val = prev_resp.get("19") if prev_resp.get("19") is not None else ""
        j19 = st.text_area("Justification (if any) ", value=j19_val, key="e_j19")

        st.divider()
        
        fr_val = edit_data['final_recommendation']
        fr_idx = 0 if fr_val == "Yes" else (1 if fr_val == "No" else None)
        q20 = st.radio("Considering the evaluations made, do you recommend this application for further consideration?", ["Yes", "No"], index=fr_idx, horizontal=True)
        
        oj_val = edit_data.get('overall_justification', "")
        oj_val = oj_val if pd.notna(oj_val) else ""
        j21 = st.text_area("Please provide a justification for your choice.", value=oj_val)

        if st.form_submit_button("Update Evaluation"):
            if None in [q12a, q12b, q12c, q14a, q14b, q16a, q18a, q20]:
                st.warning("Please select Yes/No for all criteria before submitting.")
            else:
                resp_json = json.dumps({"12a":q12a, "12b":q12b, "12c":q12c, "13":j13, "14a":q14a, "14b":q14b, "15":j15, "16a":q16a, "17":j17, "18a":q18a, "19":j19})
                current_time = get_malaysia_time()
                
                with engine.begin() as conn:
                    conn.execute(text("""
                        UPDATE reviews SET responses=:r, final_recommendation=:fr, overall_justification=:oj, updated_at=:t 
                        WHERE id=:id
                    """), {"r": resp_json, "fr": q20, "oj": j21, "t": current_time, "id": int(edit_data['id'])})
                    
                st.session_state.success_msg = "Evaluation successfully updated!"
                st.rerun()

# --- 5. Application Logic ---
st.set_page_config(page_title="RBS Secure Review System", layout="wide")

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'menu_choice' not in st.session_state:
    st.session_state.menu_choice = "Dashboard"

# --- LOGIN ---
if not st.session_state.authenticated:
    st.title("🔐 RBS Shortlisting Review Form")
    with st.form("login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            with engine.connect() as conn:
                # 1. Check if user is an Admin
                res_admin = conn.execute(text("SELECT password_hash, full_name, profile_pic FROM users WHERE username = :u"), {"u": u}).fetchone()
                
                if res_admin and check_password(p, res_admin[0]):
                    st.session_state.authenticated = True
                    st.session_state.username = u
                    st.session_state.role = "Admin"
                    st.session_state.full_name = res_admin[1]
                    st.session_state.pic = res_admin[2]
                    st.session_state.menu_choice = "Dashboard"
                    st.rerun()
                else:
                    # 2. Check if user is a Reviewer
                    res_rev = conn.execute(text("SELECT password_hash, full_name, profile_pic FROM reviewers WHERE username = :u"), {"u": u}).fetchone()
                    if res_rev and check_password(p, res_rev[0]):
                        st.session_state.authenticated = True
                        st.session_state.username = u
                        st.session_state.role = "Reviewer"
                        st.session_state.full_name = res_rev[1]
                        st.session_state.pic = res_rev[2]
                        st.session_state.menu_choice = "Review Form"
                        st.rerun()
                    else:
                        st.error("Invalid credentials")
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    if st.session_state.pic: st.image(bytes(st.session_state.pic), width=100)
    else: st.image("https://cdn-icons-png.flaticon.com/512/149/149071.png", width=100) 
    st.title(f"{st.session_state.full_name}")
    options = ["Dashboard", "User Management", "Reviewer Management", "Applicant Management"] if st.session_state.role == "Admin" else ["Review Form", "My Submissions"]
    selection = st.radio("Navigation", options, index=options.index(st.session_state.menu_choice) if st.session_state.menu_choice in options else 0)
    st.session_state.menu_choice = selection
    if st.button("Logout"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()

menu = st.session_state.menu_choice

# GLOBAL SUCCESS MESSAGE DISPLAY
if 'success_msg' in st.session_state:
    st.success(st.session_state.success_msg)
    del st.session_state.success_msg

# --- ADMIN: DASHBOARD ---
if menu == "Dashboard":
    st.header("📊 Admin Dashboard")
    
    dashboard_query = text("""
        SELECT 
            u.full_name AS "Reviewer Name", 
            r.applicant_name AS "Applicant Name", 
            a.proposal_title AS "Proposal Title", 
            r.final_recommendation AS "Recommendation", 
            r.submitted_at AS "Submitted At", 
            r.updated_at AS "Updated At",
            r.responses AS "Raw_Responses"
        FROM reviews r
        LEFT JOIN reviewers u ON r.reviewer_username = u.username
        LEFT JOIN applicants a ON r.applicant_name = a.name
        ORDER BY r.submitted_at DESC
    """)
    
    rev_df = pd.read_sql(dashboard_query, engine)
    
    if not rev_df.empty:
        total_revs = len(rev_df)
        total_yes = len(rev_df[rev_df['Recommendation'] == 'Yes'])
        total_no = len(rev_df[rev_df['Recommendation'] == 'No'])
        
        k1, k2, k3 = st.columns(3)
        k1.metric("Total Evaluations", total_revs)
        k2.metric("Recommended (Yes)", total_yes)
        k3.metric("Not Recommended (No)", total_no)
        st.divider()
    
    st.subheader("📋 Evaluation Records")
    display_df = rev_df.drop(columns=['Raw_Responses']) if not rev_df.empty else rev_df
    st.dataframe(display_df, use_container_width=True)
    
    if not rev_df.empty:
        st.divider()
        st.subheader("📈 Recommendations Analytics")
        c1, c2 = st.columns(2)
        
        color_map = {"Yes": "#28a745", "No": "#dc3545"}

        app_stats = rev_df.groupby(['Applicant Name', 'Recommendation']).size().reset_index(name='Count')
        fig_app = px.bar(app_stats, x='Applicant Name', y='Count', color='Recommendation', 
                         title="Recommendations per Applicant", barmode='stack',
                         color_discrete_map=color_map)
        c1.plotly_chart(fig_app, use_container_width=True)
        
        fig_pie = px.pie(rev_df, names='Recommendation', hole=0.4, 
                         title="Overall Recommendation Split", color='Recommendation',
                         color_discrete_map=color_map)
        c2.plotly_chart(fig_pie, use_container_width=True)
        
        st.divider()
        st.subheader("📊 Detailed Assessment Criteria Statistics")
        
        q_stats = {"12a": {"Yes":0, "No":0}, "12b": {"Yes":0, "No":0}, "12c": {"Yes":0, "No":0}, 
                   "14a": {"Yes":0, "No":0}, "14b": {"Yes":0, "No":0}, "16a": {"Yes":0, "No":0}, "18a": {"Yes":0, "No":0}}
        
        q_labels = {
            "12a": "12a: Methods appropriate?", "12b": "12b: Relevant expertise?", "12c": "12c: Risks identified?",
            "14a": "14a: Important issue?", "14b": "14b: Significant advancements?",
            "16a": "16a: Novel approach?", "18a": "18a: Funds essential?"
        }

        for _, row in rev_df.iterrows():
            if pd.notna(row['Raw_Responses']):
                try:
                    resp = json.loads(row['Raw_Responses'])
                    for k in q_stats.keys():
                        val = resp.get(k)
                        if val in ["Yes", "No"]:
                            q_stats[k][val] += 1
                except:
                    pass
        
        stat_data = []
        for k, counts in q_stats.items():
            stat_data.append({"Criterion": q_labels[k], "Answer": "Yes", "Count": counts["Yes"]})
            stat_data.append({"Criterion": q_labels[k], "Answer": "No", "Count": counts["No"]})
        
        stat_df = pd.DataFrame(stat_data)
        fig_q = px.bar(stat_df, x="Criterion", y="Count", color="Answer", barmode="group", 
                       title="Responses per Criterion (All Reviewers)",
                       color_discrete_map=color_map)
        st.plotly_chart(fig_q, use_container_width=True)

        st.divider()
        st.subheader("📥 Export Reports")
        st.download_button("Download Evaluation Records (CSV)", data=display_df.to_csv(index=False).encode('utf-8'), file_name="RBS_Grant_Report.csv", mime="text/csv")

# --- ADMIN: REVIEWER/USER MGMT ---
elif menu in ["User Management", "Reviewer Management"]:
    is_reviewer_menu = (menu == "Reviewer Management")
    role_target = "Reviewer" if is_reviewer_menu else "Admin"
    table_target = "reviewers" if is_reviewer_menu else "users"
    
    st.header(f"👤 {menu}")
    
    t1, t2 = st.tabs(["Add Individual", "Bulk Add"])
    with t1:
        with st.expander(f"➕ Create New {role_target}"):
            with st.form(f"add_{table_target}"):
                un, fn, em, pw = st.text_input("Username"), st.text_input("Full Name"), st.text_input("Email (Optional)"), st.text_input("Password", type="password")
                pic = st.file_uploader("Profile Picture (Optional)", type=['jpg', 'png'])
                if st.form_submit_button("Add Account"):
                    if not un.strip() or not fn.strip() or not pw.strip():
                        st.warning("Username, Full Name, and Password are required!")
                    else:
                        hashed = hash_password(pw)
                        pic_data = pic.getvalue() if pic else None
                        with engine.begin() as conn:
                            if is_reviewer_menu:
                                conn.execute(text("INSERT INTO reviewers (username, full_name, email, password_hash, profile_pic) VALUES (:un, :fn, :em, :pw, :p)"),
                                             {"un": un, "fn": fn, "em": em, "pw": hashed, "p": pic_data})
                            else:
                                conn.execute(text("INSERT INTO users (username, full_name, email, password_hash, role, profile_pic) VALUES (:un, :fn, :em, :pw, :r, :p)"),
                                             {"un": un, "fn": fn, "em": em, "pw": hashed, "r": "Admin", "p": pic_data})
                        st.session_state.success_msg = f"{role_target} added successfully!"
                        st.rerun()
    with t2:
        st.info("Format: Username, Full Name, Email (Optional) - You can copy and paste directly from Excel!")
        bulk_data = st.text_area("Paste Data", key=f"bulk_{table_target}")
        if st.button("Process Bulk Add"):
            if not bulk_data.strip():
                st.warning("Please provide data to process.")
            else:
                default_pw = hash_password("RBS12345") 
                lines = bulk_data.split('\n')
                with engine.begin() as conn:
                    for line in lines:
                        line = line.strip()
                        if not line: continue
                        separator = '\t' if '\t' in line else ','
                        parts = [x.strip() for x in line.split(separator)]
                        if len(parts) >= 2:
                            un_val, fn_val = parts[0], parts[1]
                            em_val = parts[2] if len(parts) >= 3 else ""
                            if is_reviewer_menu:
                                conn.execute(text("INSERT INTO reviewers (username, full_name, email, password_hash) VALUES (:un, :fn, :em, :pw) ON CONFLICT (username) DO NOTHING"),
                                             {"un": un_val, "fn": fn_val, "em": em_val, "pw": default_pw})
                            else:
                                conn.execute(text("INSERT INTO users (username, full_name, email, password_hash, role) VALUES (:un, :fn, :em, :pw, :r) ON CONFLICT (username) DO NOTHING"),
                                             {"un": un_val, "fn": fn_val, "em": em_val, "pw": default_pw, "r": "Admin"})
                st.session_state.success_msg = "Bulk addition processed successfully!"
                st.rerun()

    st.divider()
    if is_reviewer_menu: records = pd.read_sql(text("SELECT * FROM reviewers"), engine)
    else: records = pd.read_sql(text("SELECT * FROM users WHERE role = 'Admin'"), engine)
    
    h1, h2, h3, h4, h5 = st.columns([1, 2, 2, 2, 2])
    h1.write("**Pic**"); h2.write("**Full Name**"); h3.write("**Username**"); h4.write("**Email**"); h5.write("**Action**")
    
    for _, row in records.iterrows():
        c1, c2, c3, c4, c5 = st.columns([1, 2, 2, 2, 2])
        if row['profile_pic']: c1.image(bytes(row['profile_pic']), width=40)
        else: c1.image("https://cdn-icons-png.flaticon.com/512/149/149071.png", width=40)
        c2.write(row['full_name'])
        c3.write(row['username'])
        c4.write(row['email'] if pd.notna(row['email']) else "")
        with c5:
            b1, b2 = st.columns(2)
            if is_reviewer_menu:
                if b1.button("Edit", key=f"r_{row['id']}"): edit_reviewer_dialog(row['id'], row['full_name'], row['username'], row['email'])
                if b2.button("Delete", key=f"del_r_{row['id']}"): confirm_delete_reviewer(row['id'], row['full_name'])
            else:
                if b1.button("Edit", key=f"u_{row['id']}"): edit_user_dialog(row['id'], row['full_name'], row['username'], row['email'])
                if b2.button("Delete", key=f"del_u_{row['id']}"): confirm_delete_user(row['id'], row['full_name'])

# --- ADMIN: APPLICANT MGMT ---
elif menu == "Applicant Management":
    st.header("📝 Applicant Management")
    t1, t2 = st.tabs(["Add Individual", "Bulk Add"])
    with t1:
        with st.expander("➕ Create New Applicant"):
            with st.form("add_app"):
                an, at, al = st.text_input("Name"), st.text_area("Proposal Title"), st.text_input("OneDrive Link")
                ap = st.file_uploader("Applicant Photo (Optional)", type=['jpg', 'png'])
                if st.form_submit_button("Add"):
                    if not an.strip() or not at.strip() or not al.strip():
                        st.warning("Name, Proposal Title, and OneDrive Link are required!")
                    else:
                        photo_data = ap.getvalue() if ap else None
                        with engine.begin() as conn:
                            conn.execute(text("INSERT INTO applicants (name, proposal_title, info_link, photo) VALUES (:n, :t, :l, :p)"), {"n": an, "t": at, "l": al, "p": photo_data})
                        st.session_state.success_msg = "Applicant added successfully!"
                        st.rerun()
    with t2:
        st.info("Format: Name, Proposal Title, Link - You can copy and paste directly from Excel!")
        bulk_apps = st.text_area("Paste Applicants Data")
        if st.button("Process Bulk Applicants"):
            if not bulk_apps.strip():
                st.warning("Please provide data to process.")
            else:
                lines = bulk_apps.split('\n')
                with engine.begin() as conn:
                    for line in lines:
                        line = line.strip()
                        if not line: continue
                        separator = '\t' if '\t' in line else ','
                        if separator == ',': parts = [x.strip() for x in line.split(',', 2)]
                        else: parts = [x.strip() for x in line.split('\t')]
                        if len(parts) >= 2:
                            n_val, t_val = parts[0], parts[1]
                            l_val = parts[2] if len(parts) >= 3 else ""
                            conn.execute(text("INSERT INTO applicants (name, proposal_title, info_link) VALUES (:n, :t, :l) ON CONFLICT DO NOTHING"), {"n": n_val, "t": t_val, "l": l_val})
                st.session_state.success_msg = "Bulk applicants added successfully!"
                st.rerun()

    st.divider()
    apps = pd.read_sql(text("SELECT * FROM applicants"), engine)
    ah1, ah2, ah3, ah4, ah5 = st.columns([1, 2, 3, 2, 2])
    ah1.write("**Pic**"); ah2.write("**Name**"); ah3.write("**Proposal Title**"); ah4.write("**Info Link**"); ah5.write("**Action**")
    for _, row in apps.iterrows():
        ac1, ac2, ac3, ac4, ac5 = st.columns([1, 2, 3, 2, 2])
        if row['photo']: ac1.image(bytes(row['photo']), width=50)
        else: ac1.image("https://cdn-icons-png.flaticon.com/512/149/149071.png", width=50)
        ac2.write(row['name'])
        ac3.write(row['proposal_title'])
        ac4.write(f"[Link]({row['info_link']})")
        with ac5:
            b1, b2 = st.columns(2)
            if b1.button("Edit", key=f"a_{row['id']}"): edit_app_dialog(row['id'], row['name'], row['proposal_title'], row['info_link'])
            if b2.button("Delete", key=f"del_a_{row['id']}"): confirm_delete_app(row['id'], row['name'])

# --- REVIEWER: REVIEW FORM ---
elif menu == "Review Form":
    st.title("Dr Ranjeet Bhagwan Singh Medical Research Grant Review")
    st.subheader(f"👋 Welcome, {st.session_state.full_name}!")
    pending_q = text("SELECT * FROM applicants WHERE name NOT IN (SELECT applicant_name FROM reviews WHERE reviewer_username = :u)")
    apps_df = pd.read_sql(pending_q, engine, params={"u": st.session_state.username})
    if apps_df.empty: 
        st.success("All reviews completed!")
        st.stop()
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

    with st.form("rbs_full_form"):
        st.subheader("Criteria")
        q12a = st.radio("a) Methods appropriate?", ["Yes", "No"], index=None, horizontal=True)
        q12b = st.radio("b) Expertise?", ["Yes", "No"], index=None, horizontal=True)
        q12c = st.radio("c) Risks identified?", ["Yes", "No"], index=None, horizontal=True)
        j13 = st.text_area("Justification")
        st.divider()
        q20 = st.radio("Do you recommend this application?", ["Yes", "No"], index=None, horizontal=True)
        j21 = st.text_area("Final Justification")
        if st.form_submit_button("Submit Evaluation"):
            if None in [q12a, q12b, q12c, q20]: st.warning("Fill all required fields.")
            else:
                resp_json = json.dumps({"12a":q12a, "12b":q12b, "12c":q12c, "13":j13})
                current_time = get_malaysia_time()
                with engine.begin() as conn:
                    conn.execute(text("INSERT INTO reviews (reviewer_username, applicant_name, responses, final_recommendation, overall_justification, submitted_at, updated_at) VALUES (:u, :a, :r, :fr, :oj, :t, :t)"),
                                 {"u": st.session_state.username, "a": target_applicant_name, "r": resp_json, "fr": q20, "oj": j21, "t": current_time})
                st.session_state.success_msg = "Submitted!"
                st.session_state.menu_choice = "My Submissions"
                st.rerun()

# --- REVIEWER: MY SUBMISSIONS ---
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
