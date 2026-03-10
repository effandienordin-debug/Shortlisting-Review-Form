import streamlit as st
import pandas as pd
import json
from sqlalchemy import text

# 1. We use an underscore before 'engine' to tell Streamlit: 
# "Don't track changes to this object, just use it as a tool."
@st.cache_data(ttl=60)
def get_applicants_list(_engine):
    query = "SELECT * FROM applicants"
    # Wrapping the read_sql in a standard DataFrame constructor 
    # ensures the return value is a clean, serializable object.
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
        name = st.session_state.active_review_app
        app = pd.read_sql(text("SELECT * FROM applicants WHERE name = :n"), engine, params={"n": name}).iloc[0]
        rev = pd.read_sql(text("SELECT * FROM reviews WHERE reviewer_username = :u AND applicant_name = :a"), engine, params={"u": st.session_state.username, "a": name})
        prev_resp = json.loads(rev.iloc[0]['responses']) if not rev.empty else None

        with st.form("eval_form"):
            res = render_evaluation_fields(prev_resp, rev.iloc[0].to_dict() if not rev.empty else {}, disabled=is_locked)
            if not is_locked and st.form_submit_button("💾 Save Draft", use_container_width=True, type="primary"):
                mandatory_codes = ["12a", "12b", "12c", "14a", "14b", "16a", "18a"]
                if any(res["responses"].get(c) is None for c in mandatory_codes) or res["recommendation"] is None:
                    st.error("⚠️ Please answer all mandatory questions marked with *")
                else:
                    with engine.begin() as conn:
                        if not rev.empty:
                            conn.execute(text("UPDATE reviews SET responses=:r, final_recommendation=:fr, overall_justification=:oj, updated_at=:t WHERE id=:id"), {"r":json.dumps(res["responses"]), "fr":res["recommendation"], "oj":res["justification"], "t":get_malaysia_time(), "id":int(rev.iloc[0]['id'])})
                        else:
                            conn.execute(text("INSERT INTO reviews (reviewer_username, applicant_name, responses, final_recommendation, overall_justification, submitted_at, updated_at) VALUES (:u, :a, :r, :fr, :oj, :t, :t)"), {"u":st.session_state.username, "a":name, "r":json.dumps(res["responses"]), "fr":res["recommendation"], "oj":res["justification"], "t":get_malaysia_time()})
                    st.session_state.active_review_app = None
                    st.rerun()
        if st.button("⬅️ Back to Gallery"):
            st.session_state.active_review_app = None
            st.rerun()
            pass
    else:
        apps = get_applicants_list(engine)
        # -- apps = pd.read_sql("SELECT * FROM applicants", engine)--
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
                            if row['photo']: st.image(bytes(row['photo']), width=150)
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
                st.balloons(); st.rerun()

def render_submissions(engine):
    st.header("📋 Your Evaluations")
    my_revs = pd.read_sql(text("SELECT r.*, a.photo FROM reviews r JOIN applicants a ON r.applicant_name = a.name WHERE r.reviewer_username = :u"), engine, params={"u": st.session_state.username})
    for _, row in my_revs.iterrows():
        with st.container(border=True):
            s1, s2 = st.columns([1, 5])
            if row['photo']: s1.image(bytes(row['photo']), use_container_width=True)
            s2.subheader(row['applicant_name'])
            s2.write(f"**Recommendation:** {row['final_recommendation']}")
            s2.info(f"**Justification:** {row['overall_justification']}")
