import streamlit as st
import pandas as pd
import bcrypt
from sqlalchemy import create_engine, text
import plotly.express as px
import json
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

def get_radio_index(prev_dict, key):
    if not prev_dict: return None
    val = prev_dict.get(key)
    return 0 if val == "Yes" else (1 if val == "No" else None)

# --- 2. Admin CRUD Helper ---
def delete_item(table, item_id):
    with engine.begin() as conn:
        conn.execute(text(f"DELETE FROM {table} WHERE id = :id"), {"id": item_id})
    st.toast(f"Item deleted from {table}")
    st.rerun()

# --- 3. Database Schema ---
with engine.begin() as conn:
    conn.execute(text("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username VARCHAR(255) UNIQUE, full_name VARCHAR(255), password_hash VARCHAR(255), role VARCHAR(50))"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS reviewers (id SERIAL PRIMARY KEY, username VARCHAR(255) UNIQUE, full_name VARCHAR(255), password_hash VARCHAR(255))"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS applicants (id SERIAL PRIMARY KEY, name VARCHAR(255) UNIQUE, proposal_title TEXT, info_link TEXT, photo BYTEA)"))
    # Ensure admin exists
    if conn.execute(text("SELECT COUNT(*) FROM users")).fetchone()[0] == 0:
        conn.execute(text("INSERT INTO users (username, full_name, role, password_hash) VALUES ('admin', 'Master Admin', 'Admin', :pw)"), {"pw": hash_password("Admin123!")})

# --- 4. Shared Form Component ---
def render_evaluation_fields(prev_resp=None, prev_data=None, disabled=False):
    if prev_resp is None: prev_resp = {}
    if prev_data is None: prev_data = {}
    
    sections = [
        ("Section 1 — Research Quality", [("12a", "Methods achievable?"), ("12b", "Expertise?"), ("12c", "Risks identified?")]),
        ("Section 2 — Potential Impact", [("14a", "Important issue?"), ("14b", "Advancements?")]),
        ("Section 3 — Innovation", [("16a", "Novel approach?")]),
        ("Section 4 — Value", [("18a", "Funds essential?")]),
    ]
    
    responses = {}
    for title, qs in sections:
        st.subheader(title)
        for code, label in qs:
            responses[code] = st.radio(label, ["Yes", "No"], index=get_radio_index(prev_resp, code), horizontal=True, disabled=disabled, key=f"q{code}")
        
        # Mapping justifications to original keys (13, 15, 17, 19)
        j_key = str(int(code[:2]) + 1) 
        responses[j_key] = st.text_area(f"Justification ({title})", value=prev_resp.get(j_key, ""), disabled=disabled, key=f"j{j_key}")
        st.divider()

    st.subheader("Section 5 — Final Recommendation")
    fr_val = prev_data.get('final_recommendation')
    q20 = st.radio("Recommend this application?", ["Yes", "No"], index=0 if fr_val=="Yes" else (1 if fr_val=="No" else None), horizontal=True, disabled=disabled)
    j21 = st.text_area("Final justification", value=prev_data.get('overall_justification', ""), disabled=disabled)
    
    return {"responses": responses, "recommendation": q20, "justification": j21}

# --- 5. App Setup ---
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

# --- 6. Sidebar ---
with st.sidebar:
    st.title(f"👤 {st.session_state.full_name}")
    st.write(f"Role: {st.session_state.role}")
    opts = ["Dashboard", "User Management", "Reviewer Management", "Applicant Management"] if st.session_state.role == "Admin" else ["Review Form", "My Submissions"]
    menu = st.radio("Navigation", opts)
    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

# --- 7. Modules ---
if menu == "Dashboard":
    st.header("📊 System Analytics")
    df = pd.read_sql("SELECT reviewer_username, applicant_name, final_recommendation, is_final FROM reviews", engine)
    
    if not df.empty:
        met1, met2, met3 = st.columns(3)
        met1.metric("Total Reviews", len(df))
        met2.metric("Completed (Final)", len(df[df['is_final'] == True]))
        met3.metric("Approval Rate", f"{(len(df[df['final_recommendation']=='Yes'])/len(df)*100):.1f}%")
        
        st.divider()
        col_a, col_b = st.columns(2)
        with col_a:
            fig1 = px.pie(df, names='final_recommendation', title="Recommendation Split", color_discrete_map={"Yes":"#2ecc71","No":"#e74c3c"})
            st.plotly_chart(fig1)
        with col_b:
            fig2 = px.histogram(df, x='reviewer_username', color='final_recommendation', barmode='group', title="Reviews per Reviewer")
            st.plotly_chart(fig2)
    else: st.info("No data yet.")

elif menu in ["User Management", "Reviewer Management", "Applicant Management"]:
    table = menu.split(" ")[0].lower() + "s"
    st.header(f"⚙️ {menu} (CRUD)")
    
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
                    elif table == "users":
                        conn.execute(text("INSERT INTO users (username, full_name, role, password_hash) VALUES (:u, :f, 'Admin', :p)"), {"u":un,"f":fn,"p":hash_password(pw)})
                    else:
                        conn.execute(text("INSERT INTO reviewers (username, full_name, password_hash) VALUES (:u, :f, :p)"), {"u":un,"f":fn,"p":hash_password(pw)})
                st.rerun()

    # List/Update/Delete Section
    data = pd.read_sql(f"SELECT * FROM {table}", engine)
    for _, row in data.iterrows():
        with st.container(border=True):
            c1, c2, c3 = st.columns([1, 4, 1.5])
            if table == "applicants" and row['photo']:
                c1.image(bytes(row['photo']), width=100) # Passport style display
            
            c2.write(f"**ID:** {row['id']} | **Primary:** {row['name'] if table=='applicants' else row['username']}")
            if table == "applicants": c2.caption(row['proposal_title'])
            
            if c3.button("🗑️ Delete", key=f"del_{table}_{row['id']}", use_container_width=True):
                delete_item(table, row['id'])

elif menu == "Review Form":
    st.title("📋 Grant Review Portal")
    is_locked = pd.read_sql(text("SELECT COUNT(*) FROM reviews WHERE reviewer_username = :u AND is_final = TRUE"), engine, params={"u": st.session_state.username}).iloc[0,0] > 0

    if st.session_state.get('active_review_app'):
        # Individual Form View
        name = st.session_state.active_review_app
        app = pd.read_sql(text("SELECT * FROM applicants WHERE name = :n"), engine, params={"n": name}).iloc[0]
        rev = pd.read_sql(text("SELECT * FROM reviews WHERE reviewer_username = :u AND applicant_name = :a"), engine, params={"u": st.session_state.username, "a": name})
        prev_resp = json.loads(rev.iloc[0]['responses']) if not rev.empty else None

        with st.container(border=True):
            col_img, col_txt = st.columns([1, 4])
            with col_img:
                if app['photo']:
                    st.image(bytes(app['photo']), width=150, caption="Passport (Click to Zoom)")
            with col_txt:
                st.subheader(name)
                st.write(app['proposal_title'])
                st.markdown(f"🔗 [Documents]({app['info_link']})")

        with st.form("eval_form"):
            res = render_evaluation_fields(prev_resp, rev.iloc[0].to_dict() if not rev.empty else {}, disabled=is_locked)
            if not is_locked and st.form_submit_button("💾 Save Draft"):
                with engine.begin() as conn:
                    if not rev.empty:
                        conn.execute(text("UPDATE reviews SET responses=:r, final_recommendation=:fr, overall_justification=:oj, updated_at=:t WHERE id=:id"), {"r":json.dumps(res["responses"]), "fr":res["recommendation"], "oj":res["justification"], "t":get_malaysia_time(), "id":int(rev.iloc[0]['id'])})
                    else:
                        conn.execute(text("INSERT INTO reviews (reviewer_username, applicant_name, responses, final_recommendation, overall_justification, submitted_at, updated_at) VALUES (:u, :a, :r, :fr, :oj, :t, :t)"), {"u":st.session_state.username, "a":name, "r":json.dumps(res["responses"]), "fr":res["recommendation"], "oj":res["justification"], "t":get_malaysia_time()})
                st.session_state.active_review_app = None
                st.rerun()
        if st.button("⬅️ Back"):
            st.session_state.active_review_app = None
            st.rerun()

    else:
        # Gallery View
        apps = pd.read_sql("SELECT * FROM applicants", engine)
        revs = pd.read_sql(text("SELECT applicant_name FROM reviews WHERE reviewer_username = :u"), engine, params={"u": st.session_state.username})['applicant_name'].tolist()
        
        for i in range(0, len(apps), 4):
            cols = st.columns(4)
            for j in range(4):
                if i+j < len(apps):
                    row = apps.iloc[i+j]
                    with cols[j]:
                        with st.container(border=True):
                            if row['photo']:
                                st.image(bytes(row['photo']), width=120) # Passport Size Gallery
                            st.write(f"**{row['name']}**")
                            done = row['name'] in revs
                            if st.button("Edit" if done else "Start", key=f"go_{row['id']}", use_container_width=True, disabled=is_locked):
                                st.session_state.active_review_app = row['name']
                                st.rerun()

        if not is_locked and len(revs) >= len(apps) > 0:
            if st.button("🚀 FINAL SUBMIT ALL", type="primary", use_container_width=True):
                with engine.begin() as conn:
                    conn.execute(text("UPDATE reviews SET is_final = TRUE WHERE reviewer_username = :u"), {"u": st.session_state.username})
                st.rerun()
