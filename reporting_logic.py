import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import text

@st.cache_resource(ttl=60)
def get_report_data(_engine):
    query = """
        SELECT 
            r.applicant_name,
            COALESCE(rev.full_name, r.reviewer_username) as reviewer_name,
            r.final_recommendation,
            r.is_final,
            r.overall_justification
        FROM reviews r
        LEFT JOIN reviewers rev ON r.reviewer_username = rev.username
    """
    return pd.read_sql(text(query), _engine)

def render_reporting(engine):
    # --- 1. CSS PRINT HACK (Updated to hide toasts and align layout) ---
    st.markdown("""
        <style>
        @media print {
            /* Hide Sidebar, Header, Footer, and Navigation */
            [data-testid="stSidebar"], header, footer, #MainMenu {
                display: none !important;
            }
            /* HIDE TOAST NOTIFICATIONS (Prevents overlap with title) */
            [data-testid="stToast"] {
                display: none !important;
            }
            /* Hide all buttons during print */
            .stButton {
                display: none !important;
            }
            /* Adjust margins for a clean PDF layout */
            .main .block-container {
                padding-top: 1rem !important;
                max-width: 100% !important;
            }
        }
        </style>
    """, unsafe_allow_html=True)

    st.header("📄 Grant Reporting Center")
    df = get_report_data(engine)

    if df.empty:
        st.info("No data available yet.")
        return

    # --- 2. FILTERS (Hides in Print automatically due to .stButton/expander logic) ---
    with st.expander("🔍 Filter Results"):
        c1, c2 = st.columns(2)
        f_rec = c1.multiselect("Recommendation", df['final_recommendation'].unique(), default=df['final_recommendation'].unique())
        f_rev = c2.multiselect("Reviewer", df['reviewer_name'].unique(), default=df['reviewer_name'].unique())
    
    filtered_df = df[(df['final_recommendation'].isin(f_rec)) & (df['reviewer_name'].isin(f_rev))]

    # --- 3. VISUALS ---
    fig1 = px.pie(filtered_df, names='final_recommendation', title="Overall Recommendation Split")
    fig2 = px.bar(filtered_df.groupby(['applicant_name', 'final_recommendation']).size().reset_index(name='count'), 
                  x='applicant_name', y='count', color='final_recommendation', title="Applicant Breakdown")

    col1, col2 = st.columns(2)
    col1.plotly_chart(fig1, use_container_width=True)
    col2.plotly_chart(fig2, use_container_width=True)

    # --- 4. ALIGNED EXPORT BUTTONS ---
    st.divider()
    btn_col1, btn_col2 = st.columns(2)

    # Print Button
    if btn_col1.button("🖨️ Generate Professional PDF", use_container_width=True, type="primary"):
        # parent.print() escapes the iframe to print the full page
        st.components.v1.html("""
            <script>
                window.parent.print();
            </script>
        """, height=0)
        st.toast("Opening Print Dialog... Select 'Save as PDF'.")

    # CSV Button (Aligned perfectly next to Print)
    btn_col2.download_button(
        label="📊 Download Data (CSV)",
        data=filtered_df.to_csv(index=False),
        file_name="RBS_Data_Export.csv",
        mime="text/csv",
        use_container_width=True
    )

    # --- 5. DATA PREVIEW ---
    st.subheader("📋 Data Summary")
    st.dataframe(filtered_df, use_container_width=True, hide_index=True)
