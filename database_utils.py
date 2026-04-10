import streamlit as st
import bcrypt
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta, timezone

DB_URL = st.secrets["DATABASE_URL"]

@st.cache_resource
def get_engine():
    return create_engine(
        DB_URL, 
        pool_size=10, 
        max_overflow=20, 
        pool_pre_ping=True
    )

engine = get_engine()

def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed):
    try: 
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except: 
        return False

def get_malaysia_time():
    my_tz = timezone(timedelta(hours=8))
    return datetime.now(my_tz).strftime('%Y-%m-%d %H:%M:%S')

def get_radio_index(prev_dict, key):
    if not prev_dict: return None
    val = prev_dict.get(key)
    return 0 if val == "Yes" else (1 if val == "No" else None)

def delete_item(table, item_id):
    with engine.begin() as conn:
        conn.execute(text(f"DELETE FROM {table} WHERE id = :id"), {"id": item_id})
    st.cache_resource.clear() # ---> TAMBAH BARIS INI
    st.toast(f"Item deleted from {table}")
    st.rerun()

@st.cache_resource
def init_db():
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username VARCHAR(255) UNIQUE, full_name VARCHAR(255), password_hash VARCHAR(255), role VARCHAR(50))"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS reviewers (id SERIAL PRIMARY KEY, username VARCHAR(255) UNIQUE, full_name VARCHAR(255), password_hash VARCHAR(255))"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS applicants (id SERIAL PRIMARY KEY, name VARCHAR(255) UNIQUE, proposal_title TEXT, info_link TEXT, photo BYTEA)"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS reviews (
                id SERIAL PRIMARY KEY, reviewer_username VARCHAR(255), applicant_name VARCHAR(255), 
                responses TEXT, final_recommendation VARCHAR(50), overall_justification TEXT, 
                submitted_at TIMESTAMP, updated_at TIMESTAMP, is_final BOOLEAN DEFAULT FALSE
            )
        """))
        # ---> NEW TABLE: APPLICANT ASSIGNMENTS <---
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS applicant_assignments (
                id SERIAL PRIMARY KEY,
                applicant_name VARCHAR(255),
                reviewer_username VARCHAR(255),
                UNIQUE(applicant_name, reviewer_username)
            )
        """))
        
        res = conn.execute(text("SELECT COUNT(*) FROM users")).fetchone()[0]
        if res == 0:
            conn.execute(text("INSERT INTO users (username, full_name, role, password_hash) VALUES ('admin', 'Master Admin', 'Admin', :pw)"), 
                         {"pw": hash_password("Admin123!")})
    return True
