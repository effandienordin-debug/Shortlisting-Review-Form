import streamlit as st
import pandas as pd
import json
from sqlalchemy import text

# --- 1. CACHED DATA FETCHING ---
@st.cache_resource(ttl=60)
def get_assigned_applicants(_engine, username):
    # Fetch only applicants assigned to the logged-in reviewer
    query = text("""
        SELECT a.* FROM applicants a
        JOIN applicant_assignments aa ON a.name = aa.applicant_name
        WHERE aa.reviewer_username = :u
    """)
    df = pd.read_sql(query, _engine, params={"u": username})
    return df

# --- 2. RENDER REVIEW FORM & GALLERY ---
def render_review_form(engine, get_malaysia_time, render_evaluation_fields):
    st.markdown("## 📋 Dr Ranjeet Bhagwan Singh Medical Research Grant: Review Form")
    st.info("""
    The Dr Ranjeet Bhagwan Singh Medical Research Grant (RBS Grant) supports outstanding early-career researchers in Malaysia.
    Reviewers can access the applicants' information and supporting documents via the 'View Documents' Link.
    """)
    st.divider()
    
    # Welcome Card
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
        
        # Ambil data pemohon termasuk Institution dan Remarks
        app = pd.read_sql(text("SELECT * FROM applicants WHERE name = :n"), engine, params={"n": name}).iloc[0]
        
        # Ambil data review sedia ada
        rev = pd.read_sql(text("SELECT * FROM reviews WHERE reviewer_username = :u AND applicant_name = :a"), 
                          engine, params={"u": st.session_state.username, "a": name})
        
        # PENYELESAIAN NameError: Pastikan prev_resp sentiasa ditakrifkan
        prev_resp = {} 
        if not rev.empty and rev.iloc[0]['responses']:
            try:
                prev_resp = json.loads(rev.iloc[0]['responses'])
            except:
                prev_resp = {}

        with st.container(border=True):
            col_img, col_txt = st.columns([1, 4])
            if app['photo']: col_img.image(bytes(app['photo']), width=150)
            
            col_txt.subheader(name)
            # Paparan medan baru: Institution & Remarks
            col_txt.markdown(f"**Institution:** {app['institution'] if app['institution'] else 'N/A'}")
            col_txt.write(f"**Proposal:** {app['proposal_title']}")
            
            if app['remarks']:
                col_txt.info(f"**Admin Remarks:** {app['remarks']}")
                
            col_txt.markdown(f"🔗 [View Documents]({app['info_link']})")

        with st.form("eval_form"):
            # Panggil fungsi evaluation fields
            res = render_evaluation_fields(prev_resp, rev.iloc[0].to_dict() if not rev.empty else {}, disabled=is_locked)
            
            if not is_locked and st.form_submit_button("💾 Save Draft", use_container_width=True, type="primary"):
                mandatory_codes = ["12a", "12b", "12c", "14a", "14b", "16a", "18a"]
                is_incomplete = (
                    any(res["responses"].get(c) is None for c in mandatory_codes) or 
                    res["recommendation"] is None or 
                    not res["justification"].strip()
                )
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
                    
                    st.cache_resource.clear() 
                    st.session_state.active_review_app = None
                    st.rerun()
                    
        if st.button("⬅️ Back to Gallery"):
            st.session_state.active_review_app = None
            st.rerun()
    else:
        # --- GALLERY VIEW ---
        apps = get_assigned_applicants(engine, st.session_state.username)
        
        if apps.empty:
            st.info("You currently have no applicants assigned to you.")
        else:
            rev_records = pd.read_sql(text("SELECT applicant_name, final_recommendation, overall_justification FROM reviews WHERE reviewer_username = :u"), 
                                      engine, params={"u": st.session_state.username})
            reviews_lookup = rev_records.set_index('applicant_name').to_dict('index')
            
            st.subheader("Assigned Applicant Gallery")
            for i in range(0, len(apps), 4):
                cols = st.columns(4)
                for j in range(4):
                    if i+j < len(apps):
                        row = apps.iloc[i+j]
                        with cols[j]:
                            with st.container(border=True):
                                if row['photo']: 
                                    st.image(bytes(row['photo']), use_container_width=True)
                                else: 
                                    st.image("https://cdn-icons-png.flaticon.com/512/149/149071.png", use_container_width=True)
                                
                                st.write(f"**{row['name']}**")
                                st.caption(f"🏫 {row['institution'] if row['institution'] else 'N/A'}")
                                
                                if row['name'] in reviews_lookup:
                                    r_data = reviews_lookup[row['name']]
                                    rec = r_data['final_recommendation']
                                    color = "green" if rec == "Yes" else "red"
                                    st.markdown(f"**Status:** :green[✅ Saved]")
                                    st.markdown(f"**Final Recommendation:** :{color}[{rec}]")
                                else:
                                    st.markdown("**Status:** :orange[⏳ Awaiting Review]")
                                
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
