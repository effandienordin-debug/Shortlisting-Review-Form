# --- reviewer_logic.py (Kemaskini) ---
import streamlit as st
import pandas as pd
import json
from sqlalchemy import text

@st.cache_resource(ttl=60)
def get_assigned_applicants(_engine, username):
    query = text("""
        SELECT a.* FROM applicants a
        JOIN applicant_assignments aa ON a.name = aa.applicant_name
        WHERE aa.reviewer_username = :u
    """)
    df = pd.read_sql(query, _engine, params={"u": username})
    return df

def render_review_form(engine, get_malaysia_time, render_evaluation_fields):
    # ... (Header & Welcome card sama)
    
    # [KOD ASAL DIKEKALKAN SEHINGGA BAHAGIAN INDIVIDUAL REVIEW PAGE]

    if st.session_state.get('active_review_app'):
        name = st.session_state.active_review_app
        app = pd.read_sql(text("SELECT * FROM applicants WHERE name = :n"), engine, params={"n": name}).iloc[0]
        # ... (Fetch review record sama)

        with st.container(border=True):
            col_img, col_txt = st.columns([1, 4])
            if app['photo']: col_img.image(bytes(app['photo']), width=150)
            
            col_txt.subheader(name)
            col_txt.markdown(f"**Institution:** {app['institution'] if app['institution'] else 'N/A'}") # Baru
            col_txt.write(f"**Proposal Title:** {app['proposal_title']}")
            
            if app['remarks']:
                col_txt.info(f"**Admin Remarks:** {app['remarks']}") # Baru (Papar jika ada)
                
            col_txt.markdown(f"🔗 [View Documents]({app['info_link']})")

        # ... (Borang penilaian sama)
