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

# --- 5. Admin CRUD with Confirmation Dialogs ---
if menu in ["User Management", "Reviewer Management", "Applicant Management"]:
    table = menu.split(" ")[0].lower() + "s"
    st.header(f"⚙️ {menu}")

    # ADD NEW
    with st.expander(f"➕ Create New {menu[:-1]}"):
        with st.form(f"add_{table}"):
            if table == "applicants":
                n, t, l = st.text_input("Name"), st.text_area("Proposal Title"), st.text_input("OneDrive/Doc Link")
                p = st.file_uploader("Passport Photo", type=['png', 'jpg', 'jpeg'])
            else:
                un, fn, pw = st.text_input("Username"), st.text_input("Full Name"), st.text_input("Password", type="password")
            
            if st.form_submit_button("Submit"):
                with engine.begin() as conn:
                    if table == "applicants":
                        conn.execute(text("INSERT INTO applicants (name, proposal_title, info_link, photo) VALUES (:n, :t, :l, :p)"), {"n":n,"t":t,"l":l,"p":p.getvalue() if p else None})
                    elif table == "users":
                        conn.execute(text("INSERT INTO users (username, full_name, role, password_hash) VALUES (:u, :f, 'Admin', :p)"), {"u":un,"f":fn,"p":hash_password(pw)})
                    else:
                        conn.execute(text("INSERT INTO reviewers (username, full_name, password_hash) VALUES (:u, :f, :p)"), {"u":un,"f":fn,"p":hash_password(pw)})
                st.success("Record Created!"); st.rerun()

    # LIST & DELETE WITH CONFIRMATION
    st.subheader(f"Existing {menu}")
    data = pd.read_sql(f"SELECT * FROM {table} ORDER BY id DESC", engine)
    
    for _, row in data.iterrows():
        with st.container(border=True):
            c1, c2, c3 = st.columns([1, 4, 2])
            
            # Passport-style Preview
            if table == "applicants":
                if row['photo']: c1.image(bytes(row['photo']), width=100)
                else: c1.image("https://cdn-icons-png.flaticon.com/512/149/149071.png", width=100)
                c2.write(f"**{row['name']}**")
                c2.caption(row['proposal_title'])
            else:
                c2.write(f"**{row['full_name']}** (@{row['username']})")
            
            # Safe Delete Logic
            delete_key = f"del_req_{table}_{row['id']}"
            if delete_key not in st.session_state: st.session_state[delete_key] = False

            if not st.session_state[delete_key]:
                if c3.button("🗑️ Delete", key=f"btn_{table}_{row['id']}", use_container_width=True):
                    st.session_state[delete_key] = True
                    st.rerun()
            else:
                c3.warning("Are you sure?")
                col_confirm, col_cancel = c3.columns(2)
                if col_confirm.button("✅ Yes", key=f"conf_{table}_{row['id']}", use_container_width=True):
                    with engine.begin() as conn:
                        conn.execute(text(f"DELETE FROM {table} WHERE id = :id"), {"id": row['id']})
                    st.session_state[delete_key] = False
                    st.rerun()
                if col_cancel.button("❌ No", key=f"canc_{table}_{row['id']}", use_container_width=True):
                    st.session_state[delete_key] = False
                    st.rerun()

# --- 6. Reviewer Form & Gallery ---
elif menu == "Review Form":
    st.title("📋 Grant Review Portal")
    is_locked = pd.read_sql(text("SELECT COUNT(*) FROM reviews WHERE reviewer_username = :u AND is_final = TRUE"), engine, params={"u": st.session_state.username}).iloc[0,0] > 0

    if st.session_state.get('active_review_app'):
        # Individual Form View
        name = st.session_state.active_review_app
        app = pd.read_sql(text("SELECT * FROM applicants WHERE name = :n"), engine, params={"n": name}).iloc[0]
        # (Remaining form logic follows your previous structure...)
        st.subheader(f"Evaluating: {name}")
        if app['photo']: st.image(bytes(app['photo']), width=150, caption="Passport Zoom (Click to expand)")
        if st.button("⬅️ Back to Gallery"):
            st.session_state.active_review_app = None
            st.rerun()
        # [Form Fields Here...]
    else:
        # Gallery with Zoomable Passport Photos
        apps = pd.read_sql("SELECT * FROM applicants", engine)
        for i in range(0, len(apps), 4):
            cols = st.columns(4)
            for j in range(4):
                if i+j < len(apps):
                    row = apps.iloc[i+j]
                    with cols[j]:
                        with st.container(border=True):
                            if row['photo']: st.image(bytes(row['photo']), use_container_width=True)
                            else: st.image("https://cdn-icons-png.flaticon.com/512/149/149071.png", use_container_width=True)
                            st.write(f"**{row['name']}**")
                            if st.button("Review", key=f"go_{row['id']}", use_container_width=True):
                                st.session_state.active_review_app = row['name']
                                st.rerun()

# --- 7. Dashboard ---
elif menu == "Dashboard":
    st.header("📊 Analytics Dashboard")
    df = pd.read_sql("SELECT final_recommendation, applicant_name FROM reviews", engine)
    if not df.empty:
        c1, c2 = st.columns([1, 1])
        with c1:
            st.metric("Total Reviews", len(df))
            fig = px.pie(df, names='final_recommendation', title="Recommendations", color_discrete_map={"Yes":"green","No":"red"})
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.write("**Recent Activity**")
            st.dataframe(df.tail(10), use_container_width=True)
