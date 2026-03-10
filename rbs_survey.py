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

# --- 2. Helper Functions ---
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def get_malaysia_time():
    my_tz = timezone(timedelta(hours=8))
    return datetime.now(my_tz)

def get_radio_index(prev_dict, key):
    val = prev_dict.get(key)
    if val == "Yes": return 0
    if val == "No": return 1
    return None

# --- 3. Unified Evaluation Form Component ---
def render_evaluation_form(applicant_name, prev_data=None, is_locked=False):
    """
    Standardized form used for New Reviews, Drafts, and Edit Dialogs.
    """
    # Load previous responses if editing a draft
    resp = {}
    if prev_data and prev_data.get('responses'):
        resp = json.loads(prev_data['responses'])
    
    with st.container(border=True):
        st.subheader(f"Evaluation for {applicant_name}")
        
        # Section 1: Research Quality
        st.markdown("### **Section 1: Research Quality and Feasibility**")
        q12a = st.radio("12a) Are the proposed methods and objectives appropriate and achievable within the grant period (2 years)?", 
                        ["Yes", "No"], index=get_radio_index(resp, "12a"), horizontal=True, disabled=is_locked, key=f"q12a_{applicant_name}")
        q12b = st.radio("12b) Does the applicant have relevant expertise and a strong research track record?", 
                        ["Yes", "No"], index=get_radio_index(resp, "12b"), horizontal=True, disabled=is_locked, key=f"q12b_{applicant_name}")
        q12c = st.radio("12c) Have potential risks been identified, and are there plans to address them?", 
                        ["Yes", "No"], index=get_radio_index(resp, "12c"), horizontal=True, disabled=is_locked, key=f"q12c_{applicant_name}")
        j13 = st.text_area("13) Justification for Research Quality", value=resp.get("13", ""), disabled=is_locked, key=f"j13_{applicant_name}")
        
        st.divider()
        
        # Section 2: Potential Impact
        st.markdown("### **Section 2: Potential Impact**")
        q14a = st.radio("14a) Does the research address an important issue in medical science?", 
                        ["Yes", "No"], index=get_radio_index(resp, "14a"), horizontal=True, disabled=is_locked, key=f"q14a_{applicant_name}")
        q14b = st.radio("14b) Does it have the potential to contribute to significant advancements in the medical field?", 
                        ["Yes", "No"], index=get_radio_index(resp, "14b"), horizontal=True, disabled=is_locked, key=f"q14b_{applicant_name}")
        j15 = st.text_area("15) Justification for Potential Impact", value=resp.get("15", ""), disabled=is_locked, key=f"j15_{applicant_name}")

        st.divider()

        # Section 3: Innovation and Novelty
        st.markdown("### **Section 3: Innovation and Novelty**")
        q16a = st.radio("16a) Does the research propose a novel approach or methodology?", 
                        ["Yes", "No"], index=get_radio_index(resp, "16a"), horizontal=True, disabled=is_locked, key=f"q16a_{applicant_name}")
        j17 = st.text_area("17) Justification for Innovation", value=resp.get("17", ""), disabled=is_locked, key=f"j17_{applicant_name}")

        st.divider()

        # Section 4: Value for Money
        st.markdown("### **Section 4: Value for Money**")
        q18a = st.radio("18a) Are the requested funds essential and appropriately allocated?", 
                        ["Yes", "No"], index=get_radio_index(resp, "18a"), horizontal=True, disabled=is_locked, key=f"q18a_{applicant_name}")
        j19 = st.text_area("19) Justification for Value for Money", value=resp.get("19", ""), disabled=is_locked, key=f"j19_{applicant_name}")

        st.divider()

        # Section 5: Final Recommendation
        st.markdown("### **Section 5: Final Recommendation**")
        current_fr = prev_data.get('final_recommendation') if prev_data else None
        fr_idx = 0 if current_fr == "Yes" else (1 if current_fr == "No" else None)
        q20 = st.radio("20) Considering the evaluations made, do you recommend this application for further consideration?", 
                        ["Yes", "No"], index=fr_idx, horizontal=True, disabled=is_locked, key=f"q20_{applicant_name}")
        j21 = st.text_area("21) Final justification for your choice", value=prev_data.get('overall_justification', "") if prev_data else "", disabled=is_locked, key=f"j21_{applicant_name}")

        if not is_locked:
            c1, c2 = st.columns(2)
            if c1.button("💾 Save Review", type="primary", use_container_width=True, key=f"save_{applicant_name}"):
                save_draft(applicant_name, q12a, q12b, q12c, j13, q14a, q14b, j15, q16a, j17, q18a, j19, q20, j21)
            if c2.button("Cancel", use_container_width=True, key=f"cancel_{applicant_name}"):
                st.session_state.active_applicant = None
                st.rerun()

def save_draft(app_name, q12a, q12b, q12c, j13, q14a, q14b, j15, q16a, j17, q18a, j19, q20, j21):
    resp_json = json.dumps({
        "12a": q12a, "12b": q12b, "12c": q12c, "13": j13, 
        "14a": q14a, "14b": q14b, "15": j15, 
        "16a": q16a, "17": j17, 
        "18a": q18a, "19": j19
    })
    now = get_malaysia_time()
    
    with engine.begin() as conn:
        # Check if review already exists
        existing = conn.execute(text("SELECT id FROM reviews WHERE reviewer_username = :u AND applicant_name = :a"),
                                {"u": st.session_state.username, "a": app_name}).fetchone()
        
        if existing:
            conn.execute(text("""
                UPDATE reviews SET responses=:r, final_recommendation=:fr, overall_justification=:oj, updated_at=:t
                WHERE id=:id
            """), {"r": resp_json, "fr": q20, "oj": j21, "t": now, "id": existing[0]})
        else:
            conn.execute(text("""
                INSERT INTO reviews (reviewer_username, applicant_name, responses, final_recommendation, overall_justification, submitted_at, updated_at)
                VALUES (:u, :a, :r, :fr, :oj, :t, :t)
            """), {"u": st.session_state.username, "a": app_name, "r": resp_json, "fr": q20, "oj": j21, "t": now})
    
    st.session_state.active_applicant = None
    st.success("Review saved successfully!")
    st.rerun()

# --- 4. Main App Setup ---
st.set_page_config(page_title="RBS Secure Review System", layout="wide")

# Initialize Session States
if 'active_applicant' not in st.session_state: st.session_state.active_applicant = None
if 'final_locked' not in st.session_state: st.session_state.final_locked = False

# --- (Skipping Login/Sidebar logic for brevity, assuming standard implementation) ---

# --- REVIEWER: REVIEW FORM ---
if st.session_state.get('menu_choice') == "Review Form":
    st.title("Dr Ranjeet Bhagwan Singh Grant: Review Portal")
    
    if st.session_state.active_applicant:
        # SHOW INDIVIDUAL FORM
        name = st.session_state.active_applicant
        # Fetch current data for this app if it exists
        rev_data = pd.read_sql(text("SELECT * FROM reviews WHERE reviewer_username = :u AND applicant_name = :a"), 
                               engine, params={"u": st.session_state.username, "a": name})
        
        prev_data = rev_data.iloc[0].to_dict() if not rev_data.empty else None
        render_evaluation_form(name, prev_data, is_locked=st.session_state.final_locked)
        
    else:
        # SHOW APPLICANT CARDS
        st.subheader("Select an Applicant to Review")
        
        # Load data
        apps = pd.read_sql("SELECT * FROM applicants", engine)
        my_reviews = pd.read_sql(text("SELECT applicant_name FROM reviews WHERE reviewer_username = :u"), 
                                 engine, params={"u": st.session_state.username})
        reviewed_names = my_reviews['applicant_name'].tolist()

        # Grid Layout
        cols = st.columns(3)
        for idx, row in apps.iterrows():
            with cols[idx % 3]:
                with st.container(border=True):
                    # Image
                    if row['photo']: st.image(bytes(row['photo']), use_container_width=True)
                    else: st.image("https://cdn-icons-png.flaticon.com/512/149/149071.png", use_container_width=True)
                    
                    st.markdown(f"**{row['name']}**")
                    st.caption(row['proposal_title'][:100] + "...")
                    
                    status_color = "green" if row['name'] in reviewed_names else "orange"
                    status_text = "Completed" if row['name'] in reviewed_names else "Pending"
                    st.markdown(f":{status_color}[● {status_text}]")
                    
                    if st.button("Review" if row['name'] not in reviewed_names else "Edit Review", 
                                 key=f"card_{row['id']}", use_container_width=True, disabled=st.session_state.final_locked):
                        st.session_state.active_applicant = row['name']
                        st.rerun()

        # Final Submission Logic
        if len(reviewed_names) >= len(apps) and len(apps) > 0 and not st.session_state.final_locked:
            st.divider()
            with st.container(border=True):
                st.warning("⚠️ **Final Submission:** Clicking the button below will lock all your reviews. You will not be able to edit them further.")
                if st.button("🚀 SUBMIT ALL REVIEWS", type="primary", use_container_width=True):
                    st.session_state.final_locked = True
                    st.balloons()
                    st.rerun()
        elif st.session_state.final_locked:
            st.success("✅ Your reviews have been locked and submitted to the committee.")

# --- REVIEWER: MY SUBMISSIONS ---
elif st.session_state.get('menu_choice') == "My Submissions":
    st.header("📋 My Review History")
    
    query = text("""
        SELECT r.*, a.proposal_title 
        FROM reviews r 
        LEFT JOIN applicants a ON r.applicant_name = a.name 
        WHERE r.reviewer_username = :u 
        ORDER BY r.submitted_at DESC
    """)
    my_revs = pd.read_sql(query, engine, params={"u": st.session_state.username})
    
    if my_revs.empty:
        st.info("You haven't submitted any reviews yet.")
    else:
        for _, row in my_revs.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.markdown(f"#### Applicant: {row['applicant_name']}")
                    st.caption(f"📅 Submitted: {row['submitted_at'].strftime('%d %b %Y, %H:%M')}")
                with c2:
                    color = "green" if row['final_recommendation'] == "Yes" else "red"
                    st.markdown(f"<h3 style='color:{color}; text-align:right;'>{row['final_recommendation']}</h3>", unsafe_allow_html=True)
                
                st.write(f"**Proposal:** {row['proposal_title']}")
                st.divider()
                st.write("**Overall Justification:**")
                st.info(row['overall_justification'] if row['overall_justification'] else "No justification provided.")
                
                with st.expander("View Full Assessment Details"):
                    resp = json.loads(row['responses'])
                    st.json(resp)
