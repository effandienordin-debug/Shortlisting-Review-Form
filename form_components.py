import streamlit as st

def get_radio_index(resp_dict, key, options=["Yes", "No"]):
    val = resp_dict.get(key)
    if val in options:
        return options.index(val)
    return None

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
        responses[j_key] = st.text_area(f"Justification ({title}) *", value=prev_resp.get(j_key, ""), disabled=disabled, key=f"j{j_key}", placeholder="Wajib diisi...")
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
    j21 = st.text_area("Final justification *", value=prev_data.get('overall_justification', ""), disabled=disabled, placeholder="Wajib diisi...")
    
    return {"responses": responses, "recommendation": q20, "justification": j21}


def render_scoring_fields(prev_resp=None, prev_data=None, disabled=False):
    if prev_resp is None: prev_resp = {}
    if prev_data is None: prev_data = {}

    st.subheader("📊 Phase 2: Scoring (Winner Selection)")
    
    # --- TAMBAHAN RUJUKAN KRITERIA DARI GAMBAR ---
    with st.expander("📖 Rujukan Kriteria Penilaian (Scoring Rubric)", expanded=True):
        st.markdown("""
        **1. Research Quality and Feasibility (50%)**
        * Hypothesis and objectives (10%)
        * Methodology (10%)
        * Track Record (10%)
        * Achievable within the grant period (2 years) (10%)
        * Potential risks have been identified, and there are plans to address them (10%)

        **2. Impact (20%)**
        * Addresses an important issue in medical science (10%)
        * Potential to contribute to significant advancements in the medical field (10%)

        **3. Innovation (20%)**
        * Proposes a novel approach or methodology (20%)

        **4. Value for Money (10%)**
        * Requested funds are essential and appropriately allocated based on the importance of the research (10%)
        """)
    # ----------------------------------------------

    st.caption("Sila berikan markah 1 (Paling Rendah) hingga 10 (Paling Tinggi) bagi setiap kriteria.")

    res = {"responses": {}}
    
    # Kriteria 1
    st.markdown("**1. Research Quality and Feasibility (50%)**")
    res["responses"]["q1"] = st.number_input("Score (1-10) *", min_value=1, max_value=10, value=int(prev_resp.get("q1", 1)), step=1, disabled=disabled, key="p2q1")
    st.divider()

    # Kriteria 2
    st.markdown("**2. Impact (20%)**")
    res["responses"]["q2"] = st.number_input("Score (1-10) *", min_value=1, max_value=10, value=int(prev_resp.get("q2", 1)), step=1, disabled=disabled, key="p2q2")
    st.divider()

    # Kriteria 3
    st.markdown("**3. Innovation (20%)**")
    res["responses"]["q3"] = st.number_input("Score (1-10) *", min_value=1, max_value=10, value=int(prev_resp.get("q3", 1)), step=1, disabled=disabled, key="p2q3")
    st.divider()

    # Kriteria 4
    st.markdown("**4. Value for Money (10%)**")
    res["responses"]["q4"] = st.number_input("Score (1-10) *", min_value=1, max_value=10, value=int(prev_resp.get("q4", 1)), step=1, disabled=disabled, key="p2q4")

    # Pengiraan Total (Darab dengan pemberat / weightage)
    total = (res["responses"]["q1"] * 5) + (res["responses"]["q2"] * 2) + (res["responses"]["q3"] * 2) + (res["responses"]["q4"] * 1)
    res["responses"]["total_score"] = int(total)
    
    st.markdown(f"<h3 style='text-align: right; color: #1E3A8A;'>🎯 Total Score: {res['responses']['total_score']} / 100</h3>", unsafe_allow_html=True)
    st.divider()

    rec_val = prev_data.get('final_recommendation')
    res["recommendation"] = st.radio("Final Recommendation (YES/NO) *", ["Yes", "No"], 
                                     index=(0 if rec_val in ["Yes", "YES"] else (1 if rec_val in ["No", "NO"] else None)), horizontal=True, disabled=disabled)
    res["justification"] = st.text_area("Remark / Comment *", value=prev_data.get('overall_justification', ""), disabled=disabled, placeholder="Sila berikan ulasan ringkas...")
    
    return res
