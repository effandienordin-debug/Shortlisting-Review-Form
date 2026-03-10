import streamlit as st
from database_utils import get_radio_index

def render_evaluation_fields(prev_resp=None, prev_data=None, disabled=False):
    if prev_resp is None: prev_resp = {}
    if prev_data is None: prev_data = {}
    
    sections = [
        ("Section 1 — Research Quality and Feasibility", [
            ("12a", "Are the proposed methods and objectives appropriate and achievable within the grant period (2 years)?"), 
            ("12b", "Does the applicant have relevant expertise and a strong research track record?"), 
            ("12c", "Have potential risks been identified, and are there plans to address them?")
        ]),
        ("Section 2 — Potential Impact", [
            ("14a", "Does the research address an important issue in medical science?"), 
            ("14b", "Does it have the potential to contribute to significant advancements in the medical field?")
        ]),
        ("Section 3 — Innovation and Novelty", [
            ("16a", "Does the research propose a novel approach or methodology?")
        ]),
        ("Section 4 — Value for Money", [
            ("18a", "Are the requested funds essential and appropriately allocated based on the importance of the research?")
        ]),
    ]
    
    responses = {}
    for title, qs in sections:
        st.subheader(title)
        for code, label in qs:
            current_idx = get_radio_index(prev_resp, code)
            responses[code] = st.radio(
                f"{label} *", 
                ["Yes", "No"], 
                index=current_idx, 
                horizontal=True, 
                disabled=disabled, 
                key=f"q{code}"
            )
        
        j_key = str(int(code[:2]) + 1) 
        responses[j_key] = st.text_area(f"Justification ({title})", value=prev_resp.get(j_key, ""), disabled=disabled, key=f"j{j_key}")
        st.divider()

    st.subheader("Section 5 — Final Recommendation")
    fr_val = prev_data.get('final_recommendation')
    
    q20 = st.radio(
        "Considering the evaluations made above, do you recommend this application for further consideration? *", 
        ["Yes", "No"], 
        index=(0 if fr_val=="Yes" else (1 if fr_val=="No" else None)), 
        horizontal=True, 
        disabled=disabled
    )
    j21 = st.text_area("Final justification", value=prev_data.get('overall_justification', ""), disabled=disabled)
    
    return {"responses": responses, "recommendation": q20, "justification": j21}
