import streamlit as st
import sqlite3
import os
from datetime import datetime
from db_helpers import get_active_agents

# --- MAIN APP ---
def run(get_db, audit_tool_ignored):
    st.header("📝 Client Onboarding")
    st.markdown("Enter full KYC, Employment, and Compliance details below.")
    tenant_id = st.session_state.tenant_id

    # Navigation Tabs
    tab_personal, tab_employer, tab_compliance, tab_files, tab_notes = st.tabs([
        "👤 Personal Details", 
        "🏢 Employment History", 
        "⚖️ NCR Compliance", 
        "📂 Files", 
        "📝 Notes"
    ])

    # Get active agents for assignment
    db_path = st.session_state.config['db_path']
    tenant_id = st.session_state.tenant_id
    active_agents = get_active_agents(db_path, tenant_id)
    agent_options = ["Unassigned"] + [f"{agent['full_name']} ({agent['username']})" for agent in active_agents]
    agent_ids = [None] + [agent['user_id'] for agent in active_agents]

    # For agents, default to themselves
    default_index = 0
    if st.session_state.get('role') == 'Agent' and st.session_state.get('user_id'):
        for i, aid in enumerate(agent_ids):
            if aid == st.session_state.user_id:
                default_index = i
                break

    with st.form("onboarding_form"):
        # --- TAB 1: PERSONAL DETAILS ---
        with tab_personal:
            c1, c2 = st.columns(2)
            with c1:
                first_name = st.text_input("First Name")
                id_number = st.text_input("SA ID Number (Required)")
                phone = st.text_input("Primary Phone")
                marital = st.selectbox("Marital Status", ["Single", "Married (COP)", "Married (ANC)", "Widowed"])
            with c2:
                last_name = st.text_input("Last Name")
                email = st.text_input("Email Address")
                alt_phone = st.text_input("Alternative Phone")
                dependants = st.number_input("Number of Dependants", min_value=0, value=0)
            
            address = st.text_area("Residential Address", height=80)

            # Agent Assignment
            selected_agent_index = st.selectbox("Assign to Agent", range(len(agent_options)), 
                                               format_func=lambda x: agent_options[x], index=default_index)
            assigned_agent_id = agent_ids[selected_agent_index]

       # --- TAB 2: EMPLOYER DETAILS ---
        with tab_employer:
            st.markdown("### 1️⃣ Primary Employer")
            col_a, col_b = st.columns(2)
            
            # KEY EMPLOYMENT FIELDS
            with col_a:
                emp1_name = st.text_input("Employer / Company Name")
                emp1_phone = st.text_input("Work Phone Number")
                emp1_supervisor = st.text_input("Supervisor Name")
                
                # NEW: Which days do they work?
                work_days = st.multiselect(
                    "Which days do they work?",
                    ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                    default=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
                )

            with col_b:
                emp1_job = st.text_input("Job Title / Position")
                
                # NEW: Pay Day Selection
                pay_day = st.selectbox(
                    "Income Pay Day", 
                    ["25th of the Month", "Last Day of Month", "15th of the Month", "Weekly (Friday)", "Fortnightly"]
                )
                
                # How long (Start Date)
                emp1_date = st.date_input("Employment Start Date", value=None, help="Used to calculate how long they have worked there.")

            st.markdown("---")
            
            # SECONDARY EMPLOYER (Side Hustle)
            has_second_job = st.checkbox("➕ Add Secondary Employer / Side Hustle")
            
            # Initialize empty variables for safety
            emp2_name, emp2_payday = "", ""

            if has_second_job:
                st.markdown("### 2️⃣ Secondary Employer")
                col_c, col_d = st.columns(2)
                with col_c:
                    emp2_name = st.text_input("Sec. Employer Name")
                    emp2_phone = st.text_input("Sec. Work Phone")
                with col_d:
                    emp2_job = st.text_input("Sec. Job Title")
                    emp2_payday = st.text_input("Sec. Pay Day", placeholder="e.g. 1st of Month")

            st.markdown("---")
            st.subheader("💰 Income & Banking")
            ic1, ic2 = st.columns(2)
            with ic1:
                total_gross = st.number_input("Total Gross Monthly Income (R)", min_value=0.0)
                net_income = st.number_input("Net Income (Take Home) (R)", min_value=0.0)
            with ic2:
                bank_name = st.text_input("Bank Name")
                account_no = st.text_input("Account Number")

      # --- TAB 3: NCR COMPLIANCE & AFFORDABILITY ---
        with tab_compliance:
            st.markdown("### 🧮 Manual Affordability Assessment")
            st.info("Enter monthly values below to calculate Discretionary Income (NCR Regulation 23A).")

            col_inc, col_exp = st.columns(2)
            
            # 1. INCOME
            with col_inc:
                st.subheader("1. Income")
                # We pull the value from the Employer tab if entered, otherwise 0
                gross_input = st.number_input("Gross Income (R)", value=total_gross, disabled=True, help="Edit this in the Employer Tab")
                deductions = st.number_input("Statutory Deductions (PAYE/UIF)", min_value=0.0)
                other_income = st.number_input("Other Income", min_value=0.0)
                
                net_calc = gross_input - deductions + other_income
                st.metric("Net Income", f"R {net_calc:,.2f}")

            # 2. EXPENSES
            with col_exp:
                st.subheader("2. Living Expenses")
                rent_rates = st.number_input("Rent / Rates & Taxes", min_value=0.0)
                groceries = st.number_input("Groceries / Food", min_value=0.0)
                transport = st.number_input("Transport / Petrol", min_value=0.0)
                other_living = st.number_input("Other Living Expenses", min_value=0.0)
                
                st.subheader("3. Debt Obligations")
                existing_debt = st.number_input("Total Existing Loan Installments", min_value=0.0, help="Sum of all other credit commitments")

            st.markdown("---")
            
            # 3. FINAL CALCULATION
            total_expenses = rent_rates + groceries + transport + other_living + existing_debt
            discretionary_income = net_calc - total_expenses
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Expenses", f"R {total_expenses:,.2f}")
            
            # Logic: Green if positive, Red if negative
            c2.metric("Discretionary Income", f"R {discretionary_income:,.2f}", 
                     delta=f"{discretionary_income:,.2f}", 
                     delta_color="normal" if discretionary_income > 0 else "inverse")
            
            with c3:
                st.write("### Result:")
                if discretionary_income > 0:
                    st.success("✅ AFFORDABLE")
                else:
                    st.error("❌ RECKLESS (Deficit)")

            # Compliance Checkboxes (Bottom)
            st.markdown("---")
            st.caption("Compliance Checklist")
            cc1, cc2 = st.columns(2)
            with cc1:
                chk_id_copy = st.checkbox("ID Copy Verified")
                chk_payslip = st.checkbox("Latest Payslip Collected")
            with cc2:
                chk_consent = st.checkbox("Credit Check Consent Signed")
                chk_marketing = st.checkbox("Client Opted-in for Marketing")

        # --- TAB 4: FILES ---
        with tab_files:
            st.warning("Note: File upload saving is currently disabled until folder permissions are set.")
            uploaded_files = st.file_uploader("Upload KYC Documents (PDF/Img)", accept_multiple_files=True)

        # --- TAB 5: NOTES ---
        with tab_notes:
            general_notes = st.text_area("Internal Notes / Risk Profile", height=150)

        # --- SUBMIT BUTTON ---
        st.markdown("---")
        submitted = st.form_submit_button("💾 Create Client Profile")

    if submitted:
        if not first_name or not last_name or not id_number:
            st.error("⚠️ Error: First Name, Last Name, and ID Number are mandatory.")
        else:
            try:
                with get_db() as conn:
                    cursor = conn.cursor()
                    
                    # 1. Check for duplicates
                    cursor.execute("SELECT * FROM clients WHERE id_number = ?", (id_number,))
                    if cursor.fetchone():
                        st.error("❌ Client with this ID already exists.")
                    else:
                        # 2. Format the Employer Data (combining both into one string)
                        emp_string = f"PRIMARY: {emp1_name} ({emp1_job}) - {emp1_phone}"
                        if has_second_job:
                            emp_string += f" || SECONDARY: {emp2_name} ({emp2_job}) - {emp2_phone}"

                        # 3. Combine Data for Storage (Stuffing into Address/Notes to avoid DB errors)
                        full_address = f"{address} || [EMPLOYMENT]: {emp_string}"
                        full_notes = f"{general_notes} || Bank: {bank_name} ({account_no})"

                        # 4. Insert into Database
                        cursor.execute("""
                            INSERT INTO clients (
                                tenant_id, first_name, last_name, id_number, phone, email, address, total_gross, 
                                salary, employer, work_days, pay_day, bank_name, account_no, status, assigned_agent_id
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Active', ?)
                        """, (tenant_id, first_name, last_name, id_number, phone, email, full_address, total_gross,
                              net_income, emp1_name, ','.join(work_days), pay_day, bank_name, account_no, assigned_agent_id))
                        
                        conn.commit()
                        st.success(f"✅ Client {first_name} {last_name} successfully onboarded!")
                        if has_second_job:
                            st.info(f"ℹ️ Recorded both {emp1_name} and {emp2_name} in employment history.")

            except sqlite3.OperationalError as e:
                st.error(f"Database Error: {e}")
            except Exception as e:
                st.error(f"An unexpected error occurred: {e}")