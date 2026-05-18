import streamlit as st
import hashlib
import pandas as pd
from db_helpers import create_user

def run(get_db):
    st.header("👥 User Admin")
    if st.session_state.role != "Admin": st.error("Admin Only"); return
    
    tenant_id = st.session_state.tenant_id
    
    with st.form("new_u"):
        nu = st.text_input("Username")
        np = st.text_input("Password", type="password")
        role = st.selectbox("Role", ["Agent", "Manager", "Admin"])
        full_name = st.text_input("Full Name")
        if st.form_submit_button("Add User"):
            try:
                db_path = st.session_state.config['db_path']
                user_id = create_user(db_path, tenant_id, nu, np, role, full_name=full_name)
                st.success(f"User {nu} added successfully")
            except Exception as e:
                st.error(f"Error creating user: {e}")