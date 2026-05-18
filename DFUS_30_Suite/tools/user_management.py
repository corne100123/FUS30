import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import os
from datetime import datetime

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, password_hash):
    return hash_password(password) == password_hash

def run(get_db):
    tenant_id = st.session_state.get('tenant_id')
    if not tenant_id:
        st.error("No tenant selected. Please log in again.")
        return

    st.header("👥 User Management")

    # Check if current user is Admin
    if st.session_state.get('role') != 'Admin':
        st.error("Access denied. Admin privileges required.")
        return

    try:
        with get_db() as conn:
            # Get all users
            users_df = pd.read_sql_query("""
                SELECT user_id, username, role, full_name, email, phone, is_active, created_at, last_login
                FROM users
                WHERE tenant_id = ?
                ORDER BY created_at DESC
            """, conn, params=(tenant_id,))

    except Exception as e:
        st.error(f"Database Error: {e}")
        return

    if users_df.empty:
        st.warning("No users found.")
        return

    # User Management Tabs
    tab1, tab2 = st.tabs(["📋 Manage Users", "➕ Add New User"])

    with tab1:
        st.subheader("Current Users")

        # Display users in a table
        st.dataframe(
            users_df[['username', 'role', 'full_name', 'email', 'is_active', 'last_login']],
            use_container_width=True
        )

        # User actions
        st.subheader("User Actions")
        selected_user = st.selectbox(
            "Select user to manage:",
            users_df['username'].tolist(),
            key="manage_user"
        )

        if selected_user:
            user_data = users_df[users_df['username'] == selected_user].iloc[0]

            col1, col2 = st.columns(2)

            with col1:
                st.write("**User Details:**")
                st.write(f"Role: {user_data['role']}")
                st.write(f"Full Name: {user_data['full_name']}")
                st.write(f"Email: {user_data['email']}")
                st.write(f"Phone: {user_data['phone']}")
                st.write(f"Active: {'Yes' if user_data['is_active'] else 'No'}")
                st.write(f"Created: {user_data['created_at']}")
                st.write(f"Last Login: {user_data['last_login'] or 'Never'}")

            with col2:
                st.write("**Actions:**")

                # Toggle active status
                if st.button("Toggle Active Status", key=f"toggle_{selected_user}"):
                    new_status = 0 if user_data['is_active'] else 1
                    try:
                        with get_db() as conn:
                            conn.execute(
                                "UPDATE users SET is_active = ? WHERE tenant_id=? AND username = ?",
                                (new_status, tenant_id, selected_user)
                            )
                            conn.commit()
                        st.success(f"User {selected_user} {'deactivated' if new_status == 0 else 'activated'}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error updating user: {e}")

                # Change password
                with st.expander("Change Password"):
                    new_password = st.text_input("New Password", type="password", key=f"pwd_{selected_user}")
                    confirm_password = st.text_input("Confirm Password", type="password", key=f"confirm_{selected_user}")

                    if st.button("Update Password", key=f"update_pwd_{selected_user}"):
                        if new_password != confirm_password:
                            st.error("Passwords do not match")
                        elif len(new_password) < 6:
                            st.error("Password must be at least 6 characters")
                        else:
                            try:
                                with get_db() as conn:
                                    conn.execute(
                                        "UPDATE users SET password_hash = ? WHERE tenant_id=? AND username = ?",
                                        (hash_password(new_password), tenant_id, selected_user)
                                    )
                                    conn.commit()
                                    st.success(f"Password updated for {selected_user}")
                            except Exception as e:
                                st.error(f"Error updating password: {e}")

                # Change role (only if not the current admin)
                if selected_user != st.session_state.get('username'):
                    with st.expander("Change Role"):
                        new_role = st.selectbox(
                            "New Role:",
                            ["Admin", "Manager", "Agent"],
                            index=["Admin", "Manager", "Agent"].index(user_data['role']),
                            key=f"role_{selected_user}"
                        )

                        if st.button("Update Role", key=f"update_role_{selected_user}"):
                            try:
                                with get_db() as conn:
                                    conn.execute(
                                        "UPDATE users SET role = ? WHERE tenant_id=? AND username = ?",
                                        (new_role, tenant_id, selected_user)
                                    )
                                    conn.commit()
                                st.success(f"Role updated for {selected_user}")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error updating role: {e}")

    with tab2:
        st.subheader("Add New User")

        with st.form("add_user_form"):
            col1, col2 = st.columns(2)

            with col1:
                username = st.text_input("Username *")
                password = st.text_input("Password *", type="password")
                confirm_password = st.text_input("Confirm Password *", type="password")
                role = st.selectbox("Role *", ["Agent", "Manager", "Admin"])

            with col2:
                full_name = st.text_input("Full Name")
                email = st.text_input("Email")
                phone = st.text_input("Phone")

            submitted = st.form_submit_button("Create User")

            if submitted:
                # Validation
                errors = []

                if not username:
                    errors.append("Username is required")
                elif len(username) < 3:
                    errors.append("Username must be at least 3 characters")

                if not password:
                    errors.append("Password is required")
                elif len(password) < 6:
                    errors.append("Password must be at least 6 characters")
                elif password != confirm_password:
                    errors.append("Passwords do not match")

                if not role:
                    errors.append("Role is required")

                # Check if username already exists
                try:
                    with get_db() as conn:
                        existing = conn.execute(
                            "SELECT username FROM users WHERE username = ?",
                            (username,)
                        ).fetchone()
                        if existing:
                            errors.append("Username already exists")
                except Exception as e:
                    errors.append(f"Database error: {e}")

                if errors:
                    for error in errors:
                        st.error(error)
                else:
                    # Create user
                    try:
                        with get_db() as conn:
                            conn.execute("""
                                INSERT INTO users (username, password_hash, role, full_name, email, phone, is_active)
                                VALUES (?, ?, ?, ?, ?, ?, 1)
                            """, (username, hash_password(password), role, full_name, email, phone))
                            conn.commit()

                        st.success(f"User {username} created successfully!")
                        st.rerun()

                    except Exception as e:
                        st.error(f"Error creating user: {e}")