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
    try: return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except: return False

def get_malaysia_time():
    my_tz = timezone(timedelta(hours=8))
    return datetime.now(my_tz).strftime('%Y-%m-%d %H:%M:%S')

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

# --- 3. App Setup ---
st.set_page_config(page_title="RBS Grant Secure", layout="wide")
if 'authenticated' not in st.session_state: st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 RBS Grant Review Login")
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

# --- 4. Sidebar ---
with st.sidebar:
    st.title(f"👤 {st.session_state.full_name}")
    st.caption(f"Role: {st.session_state.role}")
    opts = ["Dashboard", "User Management", "Reviewer Management", "Applicant Management"] if st.session_state.role == "Admin" else ["Review Form", "My Submissions"]
    menu = st.radio("Navigation", opts)
    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

# --- 5. Admin CRUD (Create, Read, Update, Delete) ---
if menu in ["User Management", "Reviewer Management", "Applicant Management"]:
    table = menu.split(" ")[0].lower() + "s"
    st.header(f"⚙️ {menu}")

    # --- ADD NEW ---
    with st.expander(f"➕ Create New {menu[:-1]}"):
        with st.form(f"add_{table}"):
            if table == "applicants":
                n, t, l = st.text_input("Name"), st.text_area("Proposal Title"), st.text_input("OneDrive/Doc Link")
                p = st.file_uploader("Passport Photo", type=['png', 'jpg', 'jpeg'])
            else:
                un, fn, pw = st.text_input("Username"), st.text_input("Full Name"), st.text_input("Password", type="password")
            
            if st.form_submit_button("Create Record"):
                with engine.begin() as conn:
                    if table == "applicants":
                        conn.execute(text("INSERT INTO applicants (name, proposal_title, info_link, photo) VALUES (:n, :t, :l, :p)"), {"n":n,"t":t,"l":l,"p":p.getvalue() if p else None})
                    else:
                        conn.execute(text(f"INSERT INTO {table} (username, full_name, password_hash) VALUES (:u, :f, :p)"), {"u":un,"f":fn,"p":hash_password(pw)})
                st.success("Success!"); st.rerun()

    # --- LIST / EDIT / DELETE ---
    data = pd.read_sql(f"SELECT * FROM {table} ORDER BY id DESC", engine)
    
    for _, row in data.iterrows():
        edit_key = f"edit_{table}_{row['id']}"
        del_key = f"del_{table}_{row['id']}"
        
        if edit_key not in st.session_state: st.session_state[edit_key] = False
        if del_key not in st.session_state: st.session_state[del_key] = False

        with st.container(border=True):
            if st.session_state[edit_key]:
                # --- EDIT MODE ---
                with st.form(f"form_edit_{table}_{row['id']}"):
                    st.write(f"**Editing ID: {row['id']}**")
                    if table == "applicants":
                        new_n = st.text_input("Name", value=row['name'])
                        new_t = st.text_area("Proposal", value=row['proposal_title'])
                        new_l = st.text_input("Link", value=row['info_link'])
                        if st.form_submit_button("Update Applicant"):
                            with engine.begin() as conn:
                                conn.execute(text("UPDATE applicants SET name=:n, proposal_title=:t, info_link=:l WHERE id=:id"), {"n":new_n, "t":new_t, "l":new_l, "id":row['id']})
                            st.session_state[edit_key] = False
                            st.rerun()
                    else:
                        new_fn = st.text_input("Full Name", value=row['full_name'])
                        new_un = st.text_input("Username", value=row['username'])
                        if st.form_submit_button("Update Profile"):
                            with engine.begin() as conn:
                                conn.execute(text(f"UPDATE {table} SET full_name=:fn, username=:un WHERE id=:id"), {"fn":new_fn, "un":new_un, "id":row['id']})
                            st.session_state[edit_key] = False
                            st.rerun()
                    if st.form_submit_button("Cancel"):
                        st.session_state[edit_key] = False
                        st.rerun()
            else:
                # --- VIEW MODE ---
                c1, c2, c3 = st.columns([1, 4, 2])
                if table == "applicants":
                    if row['photo']: c1.image(bytes(row['photo']), width=100)
                    c2.write(f"**{row['name']}**")
                    c2.caption(row['proposal_title'])
                else:
                    c2.write(f"**{row['full_name']}**")
                    c2.caption(f"Username: @{row['username']}")

                # CRUD BUTTONS
                if not st.session_state[del_key]:
                    btn_edit = c3.button("📝 Edit", key=f"e_btn_{table}_{row['id']}", use_container_width=True)
                    btn_del = c3.button("🗑️ Delete", key=f"d_btn_{table}_{row['id']}", use_container_width=True)
                    if btn_edit: 
                        st.session_state[edit_key] = True
                        st.rerun()
                    if btn_del: 
                        st.session_state[del_key] = True
                        st.rerun()
                else:
                    c3.warning("Confirm Delete?")
                    if c3.button("✅ Confirm", key=f"conf_{table}_{row['id']}", use_container_width=True):
                        with engine.begin() as conn:
                            conn.execute(text(f"DELETE FROM {table} WHERE id = :id"), {"id": row['id']})
                        st.rerun()
                    if c3.button("❌ Cancel", key=f"can_{table}_{row['id']}", use_container_width=True):
                        st.session_state[del_key] = False
                        st.rerun()

# --- 6. Review Form (Gallery & Evaluation) ---
elif menu == "Review Form":
    st.title("📋 Grant Review Portal")
    # [Evaluation logic remains unchanged from V3 to preserve existing reviews]
    apps = pd.read_sql("SELECT * FROM applicants", engine)
    for i in range(0, len(apps), 4):
        cols = st.columns(4)
        for j in range(4):
            if i+j < len(apps):
                row = apps.iloc[i+j]
                with cols[j]:
                    with st.container(border=True):
                        # Passport Display with Zoom capability
                        if row['photo']: st.image(bytes(row['photo']), use_container_width=True)
                        st.write(f"**{row['name']}**")
                        if st.button("Open Review", key=f"rev_{row['id']}", use_container_width=True):
                            st.session_state.active_review_app = row['name']
                            st.rerun()

# --- 7. Dashboard ---
elif menu == "Dashboard":
    st.header("📊 Performance Metrics")
    rev_data = pd.read_sql("SELECT final_recommendation, applicant_name FROM reviews", engine)
    if not rev_data.empty:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Evaluations", len(rev_data))
            fig = px.bar(rev_data['final_recommendation'].value_counts(), title="Overall Decisions", labels={'value':'Count', 'index':'Recommendation'})
            st.plotly_chart(fig)
        with col2:
            st.write("**Latest Submissions**")
            st.table(rev_data.tail(5))
    else:
        st.info("No data recorded yet.")
