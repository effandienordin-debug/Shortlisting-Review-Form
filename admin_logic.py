import streamlit as st
import pandas as pd
import os
import time
import base64
from sqlalchemy import text

# --- LOCAL STORAGE SETUP ---
PHOTO_DIR = "evaluator_photos"
os.makedirs(PHOTO_DIR, exist_ok=True)

def get_local_image_base64(username):
    file_path = os.path.join(PHOTO_DIR, f"{username.replace(' ', '_')}.png")
    if os.path.exists(file_path):
        with open(file_path, "rb") as img_file:
            b64 = base64.b64encode(img_file.read()).decode()
            return f"data:image/png;base64,{b64}"
    return "https://cdn-icons-png.flaticon.com/512/149/149071.png"

# --- 1. RENDER DASHBOARD (TRACKER) ---
def render_dashboard(engine):
    st.header("📊 Live Evaluation Tracker")
    
    revs_df = pd.read_sql("SELECT username, full_name FROM reviewers", engine)
    reviews_df = pd.read_sql("SELECT reviewer_username, is_final FROM reviews", engine)
    
    try:
        assign_df = pd.read_sql("SELECT applicant_name, reviewer_username FROM applicant_assignments", engine)
    except:
        assign_df = pd.DataFrame(columns=['applicant_name', 'reviewer_username'])
        
    if revs_df.empty:
        st.info("ℹ️ Awaiting reviewers setup.")
        return
        
    st.subheader("Evaluator Status")
    cols = st.columns(4)
    for i, row in revs_df.iterrows():
        u_name = row['username']
        f_name = row['full_name']
        
        # Calculate based on assignments
        assigned_count = len(assign_df[assign_df['reviewer_username'] == u_name])
        done_count = len(reviews_df[(reviews_df['reviewer_username'] == u_name)])
        is_done = (done_count >= assigned_count) and assigned_count > 0
        
        bg, border_col = ("#E6FFFA", '#38B2AC') if is_done else ("#FFFBEB", '#ECC94B')
        img_data_uri = get_local_image_base64(u_name)
        
        with cols[i % 4]:
            st.markdown(f"""
                <div style="background-color:{bg}; border-top: 5px solid {border_col}; padding:15px; border-radius:8px; text-align:center; margin-bottom:10px;">
                    <img src="{img_data_uri}" style="width:60px; height:60px; border-radius:50%; object-fit:cover;" 
                    onerror="this.src='https://cdn-icons-png.flaticon.com/512/149/149071.png'; this.style.filter='grayscale(1)';" >
                    <p style="font-weight:bold; margin:5px 0 0 0; color:#333;">{f_name}</p>
                    <p style="font-size:1.1em; font-weight:bold; color:#1E3A8A;">{done_count} / {assigned_count} Assigned</p>
                </div>
            """, unsafe_allow_html=True)

# --- 2. RENDER MANAGEMENT MENUS ---
def render_management(menu, engine, hash_password, delete_item):
    
    if menu == "Applicant Management":
        st.header("📋 Manage Proposals & Applicants")
        
        with st.expander("➕ Add Single Proposal"):
            with st.form("add_p", clear_on_submit=True):
                a_name = st.text_input("Applicant Name*")
                p_title = st.text_input("Proposal Title*")
                p_link = st.text_input("OneDrive/Info Link")
                p_photo = st.file_uploader("Photo (Optional)", type=['png', 'jpg'])
                if st.form_submit_button("Add"):
                    if a_name and p_title:
                        photo_bytes = p_photo.getvalue() if p_photo else None
                        with engine.begin() as conn:
                            conn.execute(text("INSERT INTO applicants (name, proposal_title, info_link, photo) VALUES (:n, :t, :l, :p) ON CONFLICT DO NOTHING"),
                                         {"n": a_name.strip(), "t": p_title.strip(), "l": p_link, "p": photo_bytes})
                        st.success("✅ Added Successfully!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("🚨 Name and Title are required.")
        
        st.divider()
        st.subheader("🔗 Assign Reviewers to Applicants")
        
        apps_df = pd.read_sql("SELECT id, name, proposal_title, info_link FROM applicants ORDER BY id ASC", engine)
        revs_df = pd.read_sql("SELECT username, full_name FROM reviewers", engine)
        
        try:
            assign_df = pd.read_sql("SELECT applicant_name, reviewer_username FROM applicant_assignments", engine)
        except:
            assign_df = pd.DataFrame(columns=['applicant_name', 'reviewer_username'])
            
        reviewer_options = revs_df['username'].tolist() if not revs_df.empty else []
        reviewer_map = dict(zip(revs_df['username'], revs_df['full_name']))
        
        for idx, row in apps_df.iterrows():
            app_name = row['name']
            
            with st.container(border=True):
                c1, c2, c3 = st.columns([4, 3, 1])
                c1.write(f"**{app_name}**")
                c1.caption(f"Proposal: {row['proposal_title']}")
                
                # Get current assignments
                current_assigned = assign_df[assign_df['applicant_name'] == app_name]['reviewer_username'].tolist()
                current_assigned = [r for r in current_assigned if r in reviewer_options]
                
                # Assign Interface
                selected_revs = c2.multiselect(
                    "Assigned Reviewers:", 
                    options=reviewer_options, 
                    default=current_assigned, 
                    format_func=lambda x: f"{reviewer_map.get(x, x)} ({x})",
                    key=f"assign_{app_name}"
                )
                
                if c2.button("💾 Save Assignment", key=f"save_{app_name}"):
                    with engine.begin() as conn:
                        conn.execute(text("DELETE FROM applicant_assignments WHERE applicant_name = :a"), {"a": app_name})
                        for rev in selected_revs:
                            conn.execute(text("INSERT INTO applicant_assignments (applicant_name, reviewer_username) VALUES (:a, :r)"), 
                                         {"a": app_name, "r": rev})
                    st.success(f"Assignments updated for {app_name}!")
                    time.sleep(1)
                    st.rerun()
                
                if c3.button("🗑️ Delete Applicant", key=f"del_app_{row['id']}"):
                    with engine.begin() as conn:
                        conn.execute(text("DELETE FROM applicant_assignments WHERE applicant_name = :a"), {"a": app_name})
                    delete_item("applicants", row['id'])

    elif menu == "Reviewer Management":
        st.header("👤 Evaluators & Access Links")
        
        with st.expander("➕ Add Single Evaluator"):
            with st.form("add_rev", clear_on_submit=True):
                r_name = st.text_input("Full Name*")
                r_user = st.text_input("Username (Email/Staff ID)*")
                r_pass = st.text_input("Password*", type="password") 
                e_file = st.file_uploader("Photo (Optional)", type=['png', 'jpg'])
                if st.form_submit_button("Save Evaluator"):
                    if r_name and r_user and r_pass:
                        with engine.begin() as conn:
                            conn.execute(text("INSERT INTO reviewers (username, full_name, password_hash) VALUES (:u, :n, :p) ON CONFLICT DO NOTHING"),
                                         {"u": r_user.strip(), "n": r_name.strip(), "p": hash_password(r_pass)})
                        if e_file:
                            save_path = os.path.join(PHOTO_DIR, f"{r_user.strip().replace(' ', '_')}.png")
                            with open(save_path, "wb") as f:
                                f.write(e_file.getvalue())
                        st.success("✅ Evaluator Added!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("🚨 All fields are required.")
        
        st.divider()
        df = pd.read_sql("SELECT id, username, full_name FROM reviewers ORDER BY id ASC", engine)
        for idx, row in df.iterrows():
            c1, c2, c3, c4 = st.columns([1, 4, 1, 1])
            img_data_uri = get_local_image_base64(row['username'])
            c1.markdown(f"<img src='{img_data_uri}' width='40' height='40' style='border-radius:50%; object-fit:cover;'>", unsafe_allow_html=True)
            with c2:
                st.write(f"**{row['full_name']}**")
                st.caption(f"Username: {row['username']}")
            c3.write("`********`") 
            if c4.button("🗑️", key=f"del_rev_{row['id']}"):
                delete_item("reviewers", row['id'])

    elif menu == "User Management":
        st.header("🔑 System Admin Accounts")
        with st.expander("➕ Add Admin"):
            with st.form("add_admin", clear_on_submit=True):
                u = st.text_input("Username*")
                n = st.text_input("Full Name*")
                p = st.text_input("Password*", type="password") 
                r = st.selectbox("Role", ["Admin", "Viewer"])
                if st.form_submit_button("Create Account"):
                    if u and p and n:
                        with engine.begin() as conn:
                            conn.execute(text("INSERT INTO users (username, full_name, role, password_hash) VALUES (:u, :n, :r, :p) ON CONFLICT DO NOTHING"),
                                         {"u": u.strip(), "n": n.strip(), "r": r, "p": hash_password(p)})
                        st.success("✅ Admin Added!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("🚨 Username, Name, and Password are required.")
        st.divider()
        df = pd.read_sql("SELECT id, username, full_name, role FROM users ORDER BY id ASC", engine)
        for idx, row in df.iterrows():
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.write(f"👤 **{row['full_name']}** ({row['username']})")
            c2.write(f"Role: `{row['role']}`")
            if row['username'] != st.session_state.get('username'):
                if c3.button("🗑️", key=f"del_usr_{row['id']}"):
                    delete_item("users", row['id'])
