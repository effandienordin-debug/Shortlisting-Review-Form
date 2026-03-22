import streamlit as st
import pandas as pd
import os
import base64
from sqlalchemy import text

# --- LOCAL STORAGE SETUP ---
PHOTO_DIR = "evaluator_photos"
os.makedirs(PHOTO_DIR, exist_ok=True)

def get_local_image_base64(username):
    # Uses the username to find the photo locally
    file_path = os.path.join(PHOTO_DIR, f"{username.replace(' ', '_')}.png")
    if os.path.exists(file_path):
        with open(file_path, "rb") as img_file:
            b64 = base64.b64encode(img_file.read()).decode()
            return f"data:image/png;base64,{b64}"
    return "https://cdn-icons-png.flaticon.com/512/149/149071.png"

# --- 1. RENDER DASHBOARD (TRACKER) ---
def render_dashboard(engine):
    st.header("📊 Live Evaluation Tracker")
    
    # Fetch data using your database_utils tables
    apps_df = pd.read_sql("SELECT name FROM applicants", engine)
    revs_df = pd.read_sql("SELECT username, full_name FROM reviewers", engine)
    reviews_df = pd.read_sql("SELECT reviewer_username, is_final FROM reviews", engine)
    
    if revs_df.empty or apps_df.empty:
        st.info("ℹ️ Awaiting applicants and reviewers setup.")
        return
        
    total_apps = len(apps_df)
    
    st.subheader("Evaluator Status")
    cols = st.columns(4)
    for i, row in revs_df.iterrows():
        u_name = row['username']
        f_name = row['full_name']
        
        # Count how many reviews this specific reviewer has done
        done_count = len(reviews_df[(reviews_df['reviewer_username'] == u_name)])
        is_done = (done_count >= total_apps) and total_apps > 0
        
        bg, border_col = ("#E6FFFA", '#38B2AC') if is_done else ("#FFFBEB", '#ECC94B')
        img_data_uri = get_local_image_base64(u_name)
        
        with cols[i % 4]:
            st.markdown(f"""
                <div style="background-color:{bg}; border-top: 5px solid {border_col}; padding:15px; border-radius:8px; text-align:center; margin-bottom:10px;">
                    <img src="{img_data_uri}" style="width:60px; height:60px; border-radius:50%; object-fit:cover;" 
                    onerror="this.src='https://cdn-icons-png.flaticon.com/512/149/149071.png'; this.style.filter='grayscale(1)';" >
                    <p style="font-weight:bold; margin:5px 0 0 0; color:#333;">{f_name}</p>
                    <p style="font-size:1.1em; font-weight:bold; color:#1E3A8A;">{done_count} / {total_apps}</p>
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
        df = pd.read_sql("SELECT id, name, proposal_title, info_link FROM applicants ORDER BY id ASC", engine)
        for idx, row in df.iterrows():
            c1, c2, c3 = st.columns([5, 1, 1])
            c1.write(f"**{row['name']}** - {row['proposal_title']}")
            if c3.button("🗑️", key=f"del_app_{row['id']}"):
                delete_item("applicants", row['id'])

    elif menu == "Reviewer Management":
        st.header("👤 Evaluators & Access Links")
        
        with st.expander("➕ Add Single Evaluator"):
            with st.form("add_rev", clear_on_submit=True):
                r_name = st.text_input("Full Name*")
                r_user = st.text_input("Username (Email/Staff ID)*")
                r_pass = st.text_input("Password*", type="password") # HIDDEN PASSWORD
                e_file = st.file_uploader("Photo (Optional)", type=['png', 'jpg'])
                if st.form_submit_button("Save Evaluator"):
                    if r_name and r_user and r_pass:
                        with engine.begin() as conn:
                            # Save to Database using bcrypt hashing from database_utils
                            conn.execute(text("INSERT INTO reviewers (username, full_name, password_hash) VALUES (:u, :n, :p) ON CONFLICT DO NOTHING"),
                                         {"u": r_user.strip(), "n": r_name.strip(), "p": hash_password(r_pass)})
                        # Save photo locally
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
            c3.write("`********`") # HIDDEN PASSWORD IN TABLE
            if c4.button("🗑️", key=f"del_rev_{row['id']}"):
                delete_item("reviewers", row['id'])

    elif menu == "User Management":
        st.header("🔑 System Admin Accounts")
        with st.expander("➕ Add Admin"):
            with st.form("add_admin", clear_on_submit=True):
                u = st.text_input("Username*")
                n = st.text_input("Full Name*")
                p = st.text_input("Password*", type="password") # HIDDEN PASSWORD
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
            # Prevent the user from deleting themselves
            if row['username'] != st.session_state.get('username'):
                if c3.button("🗑️", key=f"del_usr_{row['id']}"):
                    delete_item("users", row['id'])
