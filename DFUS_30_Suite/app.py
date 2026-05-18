import streamlit as st
import sqlite3
import os
from rebuild_database import rebuild_clients
from config import load_config, save_config, get_default_db_path
from db_helpers import (
    initialize_schema,
    register_tenant,
    list_tenants,
    find_tenant,
    create_user,
    authenticate_user,
)
from fix_all_tables import run_fix

VERSION = "1.0.0"

if 'config' not in st.session_state:
    st.session_state.config = load_config()

if 'role' not in st.session_state:
    st.session_state.role = None

if 'tenant_id' not in st.session_state:
    st.session_state.tenant_id = None

if 'tenant_name' not in st.session_state:
    st.session_state.tenant_name = None

app_name = st.session_state.config['business_name'] if st.session_state.config else "FUS30"
st.set_page_config(page_title=f"{app_name} | FUS30 Suite", layout="wide")

@st.cache_data(ttl=3600)
def check_for_updates():
    try:
        update_url = "https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/version.json"
        if "YOUR_USERNAME" in update_url or "YOUR_REPO" in update_url:
            return
        import requests
        response = requests.get(update_url, timeout=2)
        if response.status_code == 200:
            remote_version = response.json().get("version")
            if remote_version and remote_version != VERSION:
                st.sidebar.info(f"✨ Update Available: {remote_version}")
    except Exception:
        pass

# --- SETUP WIZARD (First Run Only) ---
if not st.session_state.config:
    st.title("FUS30 Local Setup")
    st.markdown("### Welcome to the FUS30 Multi-Tenant Credit Management System")
    st.write("Configure your local SQLite database before registering or logging in.")

    with st.form("setup_wizard"):
        db_path = st.text_input("Local Data Storage Path (SQLite)", value=get_default_db_path())
        st.info("This file stores tenant and transaction data locally. A tenant must register with a valid NCR number before lending modules are unlocked.")

        if st.form_submit_button("Initialize Local Database"):
            if db_path:
                st.session_state.config = save_config("FUS30", db_path)
                os.makedirs(os.path.dirname(db_path), exist_ok=True)
                initialize_schema(db_path)
                st.success("Local database initialized. Continue to register or login.")
                st.rerun()
            else:
                st.error("Please provide a valid database path.")
    st.stop()


def init_db():
    if st.session_state.config:
        db_path = st.session_state.config.get('db_path', get_default_db_path())
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        initialize_schema(db_path)


def get_db():
    if not st.session_state.config or 'db_path' not in st.session_state.config:
        st.error("Database path not configured. Please complete the setup wizard.")
        st.stop()
    db_path = st.session_state.config.get('db_path', get_default_db_path())
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return sqlite3.connect(db_path)

init_db()

# Temporary: Run schema fix if needed
try:
    run_fix()
except Exception as e:
    pass  # Ignore errors, as it might fail if already fixed

# --- PRE-LOGIN TENANT ROUTING ---
if not st.session_state.tenant_id or not st.session_state.role:
    st.title(f"🔐 {app_name} Access")
    st.markdown("Select whether you are registering a new business or logging in to an existing business.")

    action = st.radio("Choose an action", ["Register New Business", "Login to Existing Business"])
    db_path = st.session_state.config['db_path']

    if action == "Register New Business":
        st.subheader("Register New Business")
        with st.form("register_business_form"):
            business_name = st.text_input("Business Name", placeholder="e.g. Centurion Microfinance")
            ncr_number = st.text_input("NCR Registration Number", placeholder="NCRxxxxxxx")
            admin_name = st.text_input("Administrator Full Name")
            admin_username = st.text_input("Administrator Username")
            password = st.text_input("Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")

            if st.form_submit_button("Create Business"):
                if not business_name or not ncr_number or not admin_username or not password:
                    st.error("All fields are required.")
                elif password != confirm_password:
                    st.error("Passwords do not match.")
                else:
                    existing = find_tenant(db_path, business_name) or find_tenant(db_path, ncr_number)
                    if existing:
                        st.error("A business with this name or NCR number already exists.")
                    else:
                        tenant_id = register_tenant(db_path, business_name, ncr_number)
                        user_id = create_user(db_path, tenant_id, admin_username, password, 'Admin', full_name=admin_name)
                        st.session_state.tenant_id = tenant_id
                        st.session_state.tenant_name = business_name
                        st.session_state.role = 'Admin'
                        st.session_state.user_id = user_id
                        st.session_state.username = admin_username
                        st.session_state.full_name = admin_name
                        st.success("Business registered successfully. You are now logged in as Admin.")
                        st.rerun()
    else:
        st.subheader("Login to Existing Business")
        tenants = list_tenants(db_path)
        if not tenants:
            st.warning("No businesses are registered yet. Please register first.")
        else:
            tenant_options = [f"{t['business_name']} ({t['ncr_registration_number']})" for t in tenants]
            selected = st.selectbox("Select Business", tenant_options)
            tenant = tenants[tenant_options.index(selected)]
            st.markdown("Only businesses with a valid NCR registration number can access lending modules.")

            with st.form("tenant_login_form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                if st.form_submit_button("Login"):
                    if not username or not password:
                        st.error("Username and password are required.")
                    else:
                        user = authenticate_user(db_path, tenant['tenant_id'], username, password)
                        if not user:
                            st.error("Invalid credentials or inactive account.")
                        else:
                            st.session_state.tenant_id = tenant['tenant_id']
                            st.session_state.tenant_name = tenant['business_name']
                            st.session_state.role = user['role']
                            st.session_state.user_id = user['user_id']
                            st.session_state.username = user['username']
                            st.session_state.full_name = user['full_name']
                            st.success(f"Logged in as {user['role']} for {tenant['business_name']}")
                            st.rerun()
    st.stop()

check_for_updates()
role = st.session_state.role

if role == "Agent":
    st.sidebar.title(f"📱 {app_name} Mobile")
    st.sidebar.caption(f"Tenant: {st.session_state.tenant_name}")
    menu = ["🏠 Today's Collections", "👤 New Client", "➕ Issue Loan", "📥 Offline Sync", "💰 Cash-Up"]
    choice = st.sidebar.radio("Main Menu", menu)

    if choice == "🏠 Today's Collections":
        from tools import payments_tool
        payments_tool.run(get_db, None)
    elif choice == "👤 New Client":
        from tools import onboarding
        onboarding.run(get_db(),selected_business)
    elif choice == "➕ Issue Loan":
        from tools import wizard
        wizard.run(get_db, None)
    elif choice == "📥 Offline Sync":
        from tools import payments_tool
        payments_tool.run(get_db, None)
    elif choice == "💰 Cash-Up":
        from tools import dashboard
        dashboard.run(get_db)
else:
    if role == "Admin":
        st.sidebar.title(f"👑 {app_name} Admin")
        st.sidebar.caption(f"Tenant: {st.session_state.tenant_name}")
        menu = ["👥 User Management", "🏠 Dashboard", "👤 Onboarding", "📝 Client Editor", "➕ Loan Wizard", "💸 Payments", "📊 Reports", "📄 Invoices", "📥 Compliance Vault"]
    else:
        st.sidebar.title(f"🏢 {app_name} Manager")
        st.sidebar.caption(f"Tenant: {st.session_state.tenant_name}")
        menu = ["🏠 Dashboard", "👤 Onboarding", "📝 Client Editor", "➕ Loan Wizard", "💸 Payments", "📊 Reports", "📄 Invoices", "📥 Compliance Vault"]

    choice = st.sidebar.radio("System Menu", menu)

    if choice == "👥 User Management" and role == "Admin":
        from tools import user_management
        user_management.run(get_db)
    elif choice == "🏠 Dashboard":
        from tools import dashboard
        dashboard.run(get_db)
    elif choice == "👤 Onboarding":
        from tools import onboarding
        onboarding.run(get_db, None)
    elif choice == "📝 Client Editor":
        from tools import client_editor
        client_editor.run(get_db)
    elif choice == "➕ Loan Wizard":
        from tools import wizard
        wizard.run(get_db, None)
    elif choice == "💸 Payments":
        from tools import payments_tool
        payments_tool.run(get_db, None)
    elif choice == "📊 Reports":
        from tools import reports
        reports.run(get_db)
    elif choice == "📄 Invoices":
        from tools import invoice_tool
        invoice_tool.run(get_db)
    elif choice == "📥 Compliance Vault":
        from tools import security_tool
        security_tool.run(get_db)

if st.sidebar.button("Logout"):
    st.session_state.role = None
    st.session_state.tenant_id = None
    st.session_state.tenant_name = None
    st.session_state.username = None
    st.session_state.user_id = None
    st.session_state.full_name = None
    st.rerun()
