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
    # --- 1. CSS PRINT HACK ---
    # This hides Streamlit-specific UI elements during printing
    st.markdown("""
        <style>
        @media print {
            /* Hide Sidebar */
            [data-testid="stSidebar"] {
                display: none !important;
            }
            /* Hide Top Header/Nav */
            header {
                visibility: hidden !important;
            }
            /* Hide Streamlit Footer/Menu */
            #MainMenu, footer {
                visibility: hidden !important;
            }
            /* Adjust padding for the main report */
            .main .block-container {
                padding-top: 1rem !important;
                padding-left: 1rem !important;
                padding-right: 1rem !important;
            }
            /* Force charts to stay visible */
            .element-container {
                page-break-inside: avoid;
            }
        }
        </style>
    """, unsafe_allow_html=True)

    st.header("📄 Grant Reporting Center")
    df = get_report_data(engine)

    if df.empty:
        st.info("No data available yet.")
        return

    # --- 2. FILTER SECTION ---
    # Wrap filters in a container so we can identify them (optional)
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

    # --- 4. EXPORT ACTIONS ---
    st.divider()
    btn_col1, btn_col2 = st.columns(2)

    # This triggers the window.print() command via Javascript
    if btn_col1.button("🖨️ Generate Professional PDF", use_container_width=True, type="primary"):
        st.components.v1.html("""
            <script>
                window.print();
            </script>
        """, height=0)
        st.toast("Print dialog opened! Remember to select 'Save as PDF'.")

    btn_col2.download_button(
        "📊 Download Data (CSV)",
        data=filtered_df.to_csv(index=False),
        file_name="RBS_Data_Export.csv",
        mime="text/csv",
        use_container_width=True
    )

    # --- 5. DATA PREVIEW ---
    st.subheader("📋 Data Summary")
    st.dataframe(filtered_df, use_container_width=True, hide_index=True)
