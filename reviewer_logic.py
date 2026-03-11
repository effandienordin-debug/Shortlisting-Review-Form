import streamlit as st
import pandas as pd
import json
from sqlalchemy import text

# --- 1. CACHED DATA FETCHING ---
# We use cache_resource because it handles DataFrames with BYTEA (photos) 
# and DB metadata without the "Unserializable" (Pickle) error.
@st.cache_resource(ttl=60)
def get_applicants_list(_engine):
    query = "SELECT * FROM applicants"
    df = pd.read_sql(query, _engine)
    return df

def render_review_form(engine, get_malaysia_time, render_evaluation_fields):
    st.markdown("## 📋 Dr Ranjeet Bhagwan Singh Medical Research Grant: Review Form")
    st.info("""
    The Dr Ranjeet Bhagwan Singh Medical Research Grant (RBS Grant) supports outstanding early-career researchers in Malaysia conducting innovative and impactful medical research. 
    This shortlisting review form is to evaluate applications based on key criteria.
    
    **Instructions:**
    Reviewers can access the applicants' information and supporting documents via the 'View Documents' Link provided in the applicant detail. 
    Please refer to **Sheet 1: Summary** (the OneDrive link is provided in the table assigned to your name) before completing this form. 
    Kindly review all materials thoroughly before making your recommendation.
    """)
    st.divider()
    
    # 2. Welcome Card
    with st.container(border=True):
        col_icon, col_greet = st.columns([1, 10])
        col_icon.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=65)
        col_greet.markdown(f"### Welcome back, {st.session_state.full_name}!")
        col_greet.caption(f"🔬 Logged in as: {st.session_state.username} | Role: Reviewer")

    # Check if the reviewer has finalized their batch
    is_locked = pd.read_sql(text("SELECT COUNT(*) FROM reviews WHERE reviewer_username = :u AND is_final = TRUE"), 
                            engine, params={"u": st.session_state.username}).iloc[0,0] > 0

    if st.session_state.get('active_review_app'):
        # --- INDIVIDUAL REVIEW PAGE ---
        name = st.session_state.active_review_app
        app = pd.read_sql(text("SELECT * FROM applicants WHERE name = :n"), engine, params={"n": name}).iloc[0]
        rev = pd.read_sql(text("SELECT * FROM reviews WHERE reviewer_username = :u AND applicant_name = :a"), 
                          engine, params={"u": st.session_state.username, "a": name})
        prev_resp = json.loads(rev.iloc[0]['responses']) if not rev.empty else None

        with st.container(border=True):
            col_img, col_txt = st.columns([1, 4])
            if app['photo']: col_img.image(bytes(app['photo']), width=150)
            col_txt.subheader(name)
            col_txt.write(f"**Proposal:** {app['proposal_title']}")
            col_txt.markdown(f"🔗 [View Documents]({app['info_link']})")

        with st.form("eval_form"):
            res = render_evaluation_fields(prev_resp, rev.iloc[0].to_dict() if not rev.empty else {}, disabled=is_locked)
            
            if not is_locked and st.form_submit_button("💾 Save Draft", use_container_width=True, type="primary"):
                # VALIDATION: Check for blank mandatory questions
                mandatory_codes = ["12a", "12b", "12c", "14a", "14b", "16a", "18a"]
                is_incomplete = any(res["responses"].get(c) is None for c in mandatory_codes) or res["recommendation"] is None
                
                if is_incomplete:
                    st.error("⚠️ Please answer all mandatory questions marked with * before saving.")
                else:
                    with engine.begin() as conn:
                        if not rev.empty:
                            conn.execute(text("UPDATE reviews SET responses=:r, final_recommendation=:fr, overall_justification=:oj, updated_at=:t WHERE id=:id"), 
                                         {"r":json.dumps(res["responses"]), "fr":res["recommendation"], "oj":res["justification"], "t":get_malaysia_time(), "id":int(rev.iloc[0]['id'])})
                        else:
                            conn.execute(text("INSERT INTO reviews (reviewer_username, applicant_name, responses, final_recommendation, overall_justification, submitted_at, updated_at) VALUES (:u, :a, :r, :fr, :oj, :t, :t)"), 
                                         {"u":st.session_state.username, "a":name, "r":json.dumps(res["responses"]), "fr":res["recommendation"], "oj":res["justification"], "t":get_malaysia_time()})
                    
                    st.cache_resource.clear() # Sync Gallery immediately
                    st.session_state.active_review_app = None
                    st.rerun()
                    
        if st.button("⬅️ Back to Gallery"):
            st.session_state.active_review_app = None
            st.rerun()
    else:
        # --- GALLERY VIEW ---
        apps = get_applicants_list(engine)
        rev_records = pd.read_sql(text("SELECT applicant_name, final_recommendation, overall_justification FROM reviews WHERE reviewer_username = :u"), 
                                  engine, params={"u": st.session_state.username})
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
                            if row['photo']: 
                                st.image(bytes(row['photo']), use_container_width=True)
                            else: 
                                st.image("https://cdn-icons-png.flaticon.com/512/149/149071.png", use_container_width=True)
                            
                            st.write(f"**{row['name']}**")
                            
                            if row['name'] in reviews_lookup:
                                r_data = reviews_lookup[row['name']]
                                rec = r_data['final_recommendation']
                                color = "green" if rec == "Yes" else "red"
                                
                                st.markdown(f"**Status:** :green[✅ Saved]")
                                st.markdown(f"**Final Recommendation:** :{color}[{rec}]")
                                
                                justification = r_data['overall_justification'] or "No text provided."
                                st.caption(f"**💬Final Justification:** {justification[:80]}...")
                            else:
                                st.markdown("**Status:** :orange[⏳ Awaiting Review]")
                                st.caption("No final justification saved yet.")
                            
                            if st.button("Review/Edit", key=f"go_{row['id']}", use_container_width=True, disabled=is_locked):
                                st.session_state.active_review_app = row['name']
                                st.rerun()

        if not is_locked and len(reviews_lookup) >= len(apps) > 0:
            st.divider()
            if st.button("🚀 FINAL SUBMIT ALL REVIEWS", type="primary", use_container_width=True):
                with engine.begin() as conn:
                    conn.execute(text("UPDATE reviews SET is_final = TRUE WHERE reviewer_username = :u"), {"u": st.session_state.username})
                st.cache_resource.clear()
                st.balloons(); st.rerun()

def render_submissions(engine):
    st.header("📋 Your Saved Submissions")
    my_revs = pd.read_sql(text("SELECT r.*, a.photo FROM reviews r JOIN applicants a ON r.applicant_name = a.name WHERE r.reviewer_username = :u"), 
                          engine, params={"u": st.session_state.username})
    if my_revs.empty:
        st.info("No submissions found.")
    else:
        for _, row in my_revs.iterrows():
            with st.container(border=True):
                s1, s2 = st.columns([1, 5])
                if row['photo']: s1.image(bytes(row['photo']), use_container_width=True)
                s2.subheader(row['applicant_name'])
                s2.write(f"**Recommendation:** {row['final_recommendation']}")
                s2.info(f"**Justification:** {row['overall_justification']}")
