import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import text

@st.cache_resource(ttl=60)
def get_analytics_data(_engine):
    df = pd.read_sql("SELECT reviewer_username, applicant_name, final_recommendation, is_final FROM reviews", _engine)
    return df

def render_dashboard(engine):
    st.header("📊 System Analytics")
    df = get_analytics_data(engine)
    
    if not df.empty:
        met1, met2, met3 = st.columns(3)
        met1.metric("Total Reviews", len(df))
        met2.metric("Completed (Final)", len(df[df['is_final'] == True]))
        met3.metric("Approval Rate", f"{(len(df[df['final_recommendation']=='Yes'])/len(df)*100):.1f}%")
        
        st.divider()
        c_a, c_b = st.columns(2)
        with c_a:
            fig1 = px.pie(df, names='final_recommendation', title="Overall Recommendation Split", color_discrete_map={"Yes":"#2ecc71","No":"#e74c3c"})
            st.plotly_chart(fig1, use_container_width=True)
        with c_b:
            app_stats = df.groupby(['applicant_name', 'final_recommendation']).size().reset_index(name='count')
            fig2 = px.bar(app_stats, x='applicant_name', y='count', color='final_recommendation', title="Applicant Analysis", barmode='group')
            st.plotly_chart(fig2, use_container_width=True)
        
        st.subheader("📋 Master Reviewer Results Table")
        st.dataframe(df, use_container_width=True)
    else: 
        st.info("No data yet.")

def render_management(menu_title, engine, hash_password, delete_item):
    mapping = {"User Management": "users", "Reviewer Management": "reviewers", "Applicant Management": "applicants"}
    table = mapping[menu_title]
    st.header(f"⚙️ {menu_title}")
    
    with st.expander(f"➕ Add New Entry"):
        with st.form(f"add_{table}"):
            if table == "applicants":
                n = st.text_input("Full Name *")
                t = st.text_area("Proposal Title *")
                l = st.text_input("Document Link")
                p = st.file_uploader("Photo", type=['png', 'jpg'])
            else:
                un = st.text_input("Username *")
                fn = st.text_input("Full Name *")
                pw = st.text_input("Password *", type="password")
            
            if st.form_submit_button("Save"):
                # VALIDATION: Prevent blank entry
                if table == "applicants":
                    if not n.strip() or not t.strip():
                        st.error("⚠️ Fields cannot be blank.")
                        st.stop()
                else:
                    if not un.strip() or not fn.strip() or not pw.strip():
                        st.error("⚠️ All fields are mandatory.")
                        st.stop()

                with engine.begin() as conn:
                    if table == "applicants":
                        conn.execute(text("INSERT INTO applicants (name, proposal_title, info_link, photo) VALUES (:n, :t, :l, :p)"), {"n":n,"t":t,"l":l,"p":p.getvalue() if p else None})
                    else:
                        conn.execute(text(f"INSERT INTO {table} (username, full_name, password_hash) VALUES (:u, :fn, :p)"), {"u":un, "fn":fn, "p":hash_password(pw)})
                
                st.cache_resource.clear()
                st.rerun()

    data = pd.read_sql(f"SELECT * FROM {table}", engine)
    for _, row in data.iterrows():
        with st.container(border=True):
            e1, e2, e3 = st.columns([1, 4, 2])
            if table == "applicants" and row['photo']: e1.image(bytes(row['photo']), width=100)
            e2.write(f"**Name:** {row['name'] if table=='applicants' else row['username']}")
            
            with e3.expander("📝 Edit Details"):
                with st.form(f"edit_{table}_{row['id']}"):
                    if table == "applicants":
                        new_n = st.text_input("Name", value=row['name'])
                        new_t = st.text_area("Title", value=row['proposal_title'])
                        new_l = st.text_input("Link", value=row['info_link'])
                        new_p = st.file_uploader("Update Photo", type=['png', 'jpg'])
                        if st.form_submit_button("Update"):
                            if not new_n.strip() or not new_t.strip():
                                st.error("⚠️ Cannot save blank fields.")
                            else:
                                p_val = new_p.getvalue() if new_p else row['photo']
                                with engine.begin() as conn:
                                    conn.execute(text("UPDATE applicants SET name=:n, proposal_title=:t, info_link=:l, photo=:p WHERE id=:id"), {"n":new_n,"t":new_t,"l":new_l,"p":p_val, "id":row['id']})
                                st.cache_resource.clear()
                                st.rerun()
                    else:
                        new_fn = st.text_input("Full Name", value=row['full_name'])
                        new_pw = st.text_input("New Password (Optional)", type="password")
                        if st.form_submit_button("Update"):
                            if not new_fn.strip():
                                st.error("⚠️ Full Name is required.")
                            else:
                                with engine.begin() as conn:
                                    if new_pw:
                                        conn.execute(text(f"UPDATE {table} SET full_name=:fn, password_hash=:p WHERE id=:id"), {"fn":new_fn, "p":hash_password(new_pw), "id":row['id']})
                                    else:
                                        conn.execute(text(f"UPDATE {table} SET full_name=:fn WHERE id=:id"), {"fn":new_fn, "id":row['id']})
                                st.cache_resource.clear()
                                st.rerun()
            
            if e3.button("🗑️ Delete", key=f"del_{table}_{row['id']}", use_container_width=True):
                delete_item(table, row['id'])
                st.cache_resource.clear()
