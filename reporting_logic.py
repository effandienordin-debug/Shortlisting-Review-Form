import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import text
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader

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

def generate_pdf_report(df, figs):
    """Helper to create a PDF containing text and static versions of Plotly graphs"""
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Title
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, height - 50, "RBS Grant System - Summary Report")
    
    # Simple Metrics
    p.setFont("Helvetica", 12)
    p.drawString(100, height - 80, f"Total Reviews: {len(df)}")
    p.drawString(100, height - 100, f"Approval Rate: {(len(df[df['final_recommendation']=='Yes'])/len(df)*100):.1f}%")

    # Add Graphs as Images
    # Note: Requires 'kaleido' package installed: pip install kaleido
    y_offset = height - 400
    for fig in figs:
        img_bytes = fig.to_image(format="png", width=600, height=350)
        img_reader = ImageReader(io.BytesIO(img_bytes))
        p.drawImage(img_reader, 50, y_offset, width=500, height=280)
        y_offset -= 300
        if y_offset < 100:
            p.showPage()
            y_offset = height - 350

    p.save()
    return buffer.getvalue()

def render_reporting(engine):
    st.header("📄 Professional Reporting")
    df = get_report_data(engine)

    if df.empty:
        st.info("No data available yet.")
        return

    # Filters
    with st.expander("🔍 Filter Criteria"):
        c1, c2 = st.columns(2)
        sel_rec = c1.multiselect("Recommendation", options=df['final_recommendation'].unique(), default=df['final_recommendation'].unique())
        sel_rev = c2.multiselect("Reviewer", options=df['reviewer_name'].unique(), default=df['reviewer_name'].unique())
    
    filtered_df = df[(df['final_recommendation'].isin(sel_rec)) & (df['reviewer_name'].isin(sel_rev))]

    # Visuals
    col_left, col_right = st.columns(2)
    
    fig_pie = px.pie(filtered_df, names='final_recommendation', title="Recommendation Distribution", 
                     color_discrete_map={"Yes":"#2ecc71","No":"#e74c3c"})
    col_left.plotly_chart(fig_pie, use_container_width=True)

    fig_bar = px.bar(filtered_df.groupby(['applicant_name', 'final_recommendation']).size().reset_index(name='count'), 
                     x='applicant_name', y='count', color='final_recommendation', title="Applicant Breakdown")
    col_right.plotly_chart(fig_bar, use_container_width=True)

    # Export Section
    st.divider()
    st.subheader("📥 Export Report")
    
    col_btn1, col_btn2 = st.columns(2)
    
    # PDF Download
    try:
        pdf_data = generate_pdf_report(filtered_df, [fig_pie, fig_bar])
        col_btn1.download_button(
            label="Download Graphs as PDF",
            data=pdf_data,
            file_name="RBS_Grant_Report.pdf",
            mime="application/pdf",
            use_container_width=True
        )
    except Exception as e:
        col_btn1.error("PDF engine (kaleido) not found. Please install it to enable PDF downloads.")

    # CSV Download
    csv = filtered_df.to_csv(index=False).encode('utf-8')
    col_btn2.download_button(
        label="Download Data as CSV",
        data=csv,
        file_name="RBS_Data_Export.csv",
        mime="text/csv",
        use_container_width=True
    )

    st.subheader("📋 Data Preview")
    st.dataframe(filtered_df, use_container_width=True)
