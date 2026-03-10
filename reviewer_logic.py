import streamlit as st
import pandas as pd
import json
from sqlalchemy import text

# USE CACHE_RESOURCE: This bypasses the 'Pickle' serialization error entirely.
# It stores the live DataFrame in memory without trying to 'save' it to disk.
@st.cache_resource(ttl=60)
def get_applicants_list(_engine):
    query = "SELECT * FROM applicants"
    df = pd.read_sql(query, _engine)
    return df

def render_review_form(engine, get_malaysia_time, render_evaluation_fields):
    st.markdown("## 📋 Dr Ranjeet Bhagwan Singh Medical Research Grant: Review Form")
    st.info("Review materials thoroughly before making your recommendation.")
    
    with st.container(border=True):
        c1, c2 = st.columns([1, 10])
        c1.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=65)
        c2.markdown(f"### Welcome back, {st.session_state.full_name}!")
        c2.caption(f"🔬 Logged in as: {st.session_state.username}")

    is_locked = pd.read_sql(text("SELECT COUNT(*) FROM reviews WHERE reviewer_username = :u AND is_final = TRUE"), engine, params={"u": st.session_state.username}).iloc[0,0] > 0

    if st.session_state.get('active_review_app'):
        # --- INDIVIDUAL REVIEW PAGE ---
        name = st.session_state.active_review_app
        app = pd.read_sql(text("SELECT * FROM applicants WHERE name = :n"), engine, params={"n": name}).iloc[0]
        rev = pd.read_sql(text("SELECT * FROM reviews WHERE reviewer_username = :u AND applicant_name = :a"), engine, params={"u": st.session_state.username, "a": name})
        prev_resp = json.loads(rev.iloc[0]['responses']) if not rev.empty else None

        with st.form("eval_form"):
            res = render_evaluation_fields(prev_resp, rev.iloc[0].to_dict() if not rev.empty else {}, disabled=is_locked)
            
            if not is_locked and st.form_submit_button("💾 Save Draft", use_container_width=True, type="primary"):
                # VALIDATION: Check for blank radio selections
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
                    
                    st.success("Draft saved successfully!")
                    st.session_state.active_review_app = None
                    # Clear resource cache to show 'Saved' status
                    st.cache_resource.clear()
                    st.rerun()
                    
        if st.button("⬅️ Back to Gallery"):
            st.session_state.active_review_app = None
            st.rerun()
    else:
        # --- GALLERY VIEW ---
        apps = get_applicants_list(engine)
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
                                st.success(f"✅ Saved")
                            if st.button("Review", key=f"go_{row['id']}", use_container_width=True, disabled=is_locked):
                                st.session_state.active_review_app = row['name']
                                st.rerun()

        if not is_locked and len(reviews_lookup) >= len(apps) > 0:
            if st.button("🚀 FINAL SUBMIT ALL", type="primary", use_container_width=True):
                with engine.begin() as conn:
                    conn.execute(text("UPDATE reviews SET is_final = TRUE WHERE reviewer_username = :u"), {"u": st.session_state.username})
                st.cache_resource.clear()
                st.balloons()
                st.rerun()
