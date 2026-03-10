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
    """Converts Plotly figures to static images and builds a PDF."""
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    w, h = letter

    # --- PDF Header ---
    p.setFont("Helvetica-Bold", 18)
    p.drawString(50, h - 50, "RBS Medical Grant: Summary Report")
    p.setFont("Helvetica", 10)
    p.drawString(50, h - 70, f"Total Applications Reviewed: {len(df)}")
    
    # --- Embed Graphs ---
    # We use kaleido (engine) to convert plotly to static PNG for the PDF
    curr_h = h - 350
    for i, fig in enumerate(figs):
        # Convert Plotly to PNG bytes
        img_bytes = fig.to_image(format="png", width=600, height=300)
        img_reader = ImageReader(io.BytesIO(img_bytes))
        
        p.drawImage(img_reader, 50, curr_h, width=500, height=250)
        curr_h -= 300
        
        if curr_h < 100 and i < len(figs)-1:
            p.showPage()
            curr_h = h - 300

    p.save()
    return buffer.getvalue()

def render_reporting(engine):
    st.header("📄 Grant Reporting Center")
    df = get_report_data(engine)

    if df.empty:
        st.info("No data available yet.")
        return

    # Filter Sidebar/Expander
    with st.expander("🔍 Filter Results"):
        c1, c2 = st.columns(2)
        f_rec = c1.multiselect("Recommendation", df['final_recommendation'].unique(), default=df['final_recommendation'].unique())
        f_rev = c2.multiselect("Reviewer", df['reviewer_name'].unique(), default=df['reviewer_name'].unique())
    
    filtered_df = df[(df['final_recommendation'].isin(f_rec)) & (df['reviewer_name'].isin(f_rev))]

    # Graphs
    fig1 = px.pie(filtered_df, names='final_recommendation', title="Overall Recommendation Split")
    fig2 = px.bar(filtered_df.groupby(['applicant_name', 'final_recommendation']).size().reset_index(name='count'), 
                  x='applicant_name', y='count', color='final_recommendation', title="Applicant Breakdown")

    col1, col2 = st.columns(2)
    col1.plotly_chart(fig1, use_container_width=True)
    col2.plotly_chart(fig2, use_container_width=True)

    # Export Actions
    st.divider()
    btn_col1, btn_col2 = st.columns(2)

    try:
        pdf_data = generate_pdf_report(filtered_df, [fig1, fig2])
        btn_col1.download_button(
            "📥 Download Graphs as PDF",
            data=pdf_data,
            file_name="RBS_Grant_Visual_Report.pdf",
            mime="application/pdf",
            use_container_width=True
        )
    except Exception as e:
        btn_col1.warning("PDF Engine (Kaleido) not found. Standard PDF export disabled.")

    btn_col2.download_button(
        "📊 Download Data as CSV",
        data=filtered_df.to_csv(index=False),
        file_name="RBS_Data_Export.csv",
        mime="text/csv",
        use_container_width=True
    )

    st.subheader("📋 Data Preview")
    st.dataframe(filtered_df, use_container_width=True)
