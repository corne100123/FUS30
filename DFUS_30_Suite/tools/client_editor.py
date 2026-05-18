import os
import streamlit as st
import pandas as pd
import sqlite3

def run(get_db):
    tenant_id = st.session_state.get('tenant_id')
    if not tenant_id:
        st.error("Tenant session not found. Please log in again.")
        return

    st.header("🛠️ Loan Editor")

    # Main tabs
    main_tab_edit, main_tab_import = st.tabs(["🔍 Edit Client", "📤 Bulk Import"])

    with main_tab_edit:
        # --- 1. SEARCH & SELECT ---
        search_term = st.text_input("🔍 Search Client (Name, Last Name, or ID)", placeholder="Search...")

        if not search_term:
            st.info("Please search for a client to begin editing.")
        else:
            with get_db() as conn:
                query = """
                    SELECT * FROM clients 
                    WHERE tenant_id = ? AND (
                        first_name LIKE ? 
                        OR last_name LIKE ? 
                        OR id_number LIKE ?
                    )
                """
                search_param = f"%{search_term}%"
                results = pd.read_sql_query(query, conn, params=(tenant_id, search_param, search_param, search_param))

            if results.empty:
                st.warning("No clients found.")
            else:
                results['display'] = results['first_name'] + " " + results['last_name'] + " (" + results['id_number'] + ")"
                selected_display = st.selectbox("Select Client", results['display'])
                client = results[results['display'] == selected_display].iloc[0]
                client_id = int(client['client_id'])

                st.markdown("---")

                # --- 2. MULTI-FUNCTION TABS ---
                tab_personal, tab_employment, tab_loans = st.tabs([
                    "👤 Personal Details", 
                    "🏢 Employment & Bank", 
                    "💰 Loan Adjustments & Fees"
                ])

                # TAB 1: PERSONAL DETAILS
                with tab_personal:
                    with st.form("personal_form"):
                        c1, c2 = st.columns(2)
                        new_first = c1.text_input("First Name", value=client['first_name'])
                        new_last = c2.text_input("Last Name", value=client['last_name'])
                        new_id = c1.text_input("ID Number", value=client['id_number'])
                        new_phone = c2.text_input("Phone", value=client['phone'])
                        new_addr = st.text_area("Address", value=client['address'])
                        
                        if st.form_submit_button("💾 Update Personal Info"):
                            with get_db() as conn:
                                conn.execute("UPDATE clients SET first_name=?, last_name=?, id_number=?, phone=?, address=? WHERE tenant_id=? AND client_id=?",
                                            (new_first, new_last, new_id, new_phone, new_addr, tenant_id, client_id))
                                conn.commit()
                            st.success("Personal details updated.")

                # TAB 2: EMPLOYMENT & BANK
                with tab_employment:
                    with st.form("employment_form"):
                        e1, e2 = st.columns(2)
                        new_emp = e1.text_input("Employer", value=client['employer'] if 'employer' in client else "")
                        new_gross = e1.number_input("Gross Income", value=float(client['total_gross']) if 'total_gross' in client else 0.0)
                        new_bank = e2.text_input("Bank", value=client['bank_name'] if 'bank_name' in client else "")
                        new_acc = e2.text_input("Account No", value=client['account_no'] if 'account_no' in client else "")
                        
                        if st.form_submit_button("💾 Update Employment/Bank"):
                            with get_db() as conn:
                                conn.execute("UPDATE clients SET employer=?, total_gross=?, bank_name=?, account_no=? WHERE tenant_id=? AND client_id=?",
                                            (new_emp, new_gross, new_bank, new_acc, tenant_id, client_id))
                                conn.commit()
                            st.success("Employment and Banking info updated.")

                # TAB 3: LOAN ADJUSTMENTS & FEES
                with tab_loans:
                    st.subheader("Manage Active Loans")
                    
                    with get_db() as conn:
                        loans = pd.read_sql_query("SELECT * FROM loans WHERE tenant_id = ? AND client_id = ?", conn, params=(tenant_id, client_id))
                    
                    if loans.empty:
                        st.info("This client has no existing loans.")
                    else:
                        # Select which loan to adjust
                        loans['loan_display'] = "Loan #" + loans['loan_id'].astype(str) + " (Bal: R" + loans['balance'].astype(str) + ")"
                        target_loan_str = st.selectbox("Select Loan to Edit", loans['loan_display'])
                        target_loan = loans[loans['loan_display'] == target_loan_str].iloc[0]
                        target_id = int(target_loan['loan_id'])

                        st.markdown("#### Adjustments")
                        with st.form("balance_adj_form"):
                            col_bal1, col_bal2 = st.columns(2)
                            
                            # Manual Balance Overwrite
                            new_bal = col_bal1.number_input("Overwrite Current Balance (R)", value=float(target_loan['balance']))
                            
                            # Status Change
                            new_status = col_bal2.selectbox("Loan Status", ["Active", "Settled", "Bad Debt", "Default"], 
                                                           index=["Active", "Settled", "Bad Debt", "Default"].index(target_loan['status']))
                            
                            st.caption("Warning: Changing the balance here directly overrides the ledger calculations.")
                            
                            if st.form_submit_button("⚠️ Apply Balance/Status Change"):
                                with get_db() as conn:
                                    conn.execute("UPDATE loans SET balance=?, status=? WHERE tenant_id=? AND loan_id=?", (new_bal, new_status, tenant_id, target_id))
                                    conn.commit()
                                st.success("Loan balance and status updated.")
                                st.rerun()

                        st.markdown("#### Apply Additional Fees")
                        with st.form("fee_form"):
                            f1, f2 = st.columns(2)
                            fee_amount = f1.number_input("Fee Amount to Add (R)", min_value=0.0, step=10.0)
                            fee_type = f2.selectbox("Fee Type", ["Admin Fee", "Arrears Penalty", "Legal Fee", "Service Fee"])
                            
                            if st.form_submit_button("➕ Add Fee to Balance"):
                                if fee_amount > 0:
                                    with get_db() as conn:
                                        # 1. Increase the loan balance
                                        conn.execute("UPDATE loans SET balance = balance + ? WHERE tenant_id=? AND loan_id = ?", (fee_amount, tenant_id, target_id))
                                        # 2. Record it in payment history as a negative 'Adjustment' for record-keeping if needed, 
                                        # or just update the balance as we did here.
                                        conn.commit()
                                    st.success(f"Added R{fee_amount} {fee_type} to the loan balance.")
                                    st.rerun()

    with main_tab_import:
        st.subheader("📤 Bulk Import Clients")
        
        # Import configuration
        col_file_type, col_list_type = st.columns(2)
        with col_file_type:
            file_type = st.selectbox("📄 File Type", ["Excel (.xlsx)", "CSV (.csv)"], help="Select the format of your upload file")
        with col_list_type:
            list_type = st.selectbox("📋 Client List Type", ["Active Clients", "Non-Active/Zero Balance"], 
                                     help="Active: clients with loans. Non-Active: zero-balance clients")
        
        st.markdown("---")
        
        # Sub-tabs for different import types
        import_tab_client, import_tab_payments = st.tabs(["👥 Bulk Client Import", "💰 Payment Sheet"])
        
        with import_tab_client:
            # Show expected columns based on list type
            if list_type == "Active Clients":
                st.info("**Expected Columns for Active List:**\nClient, No, Name & Surname, Due Date, Mobile, Work Phone, Employers Name, Address, Area, Sal Freq, Received, Balance, S")
            else:
                st.info("**Expected Columns for Non-Active List:**\nClient, No, Initials, Surname, Identity No, Gender, Tel No (H), Cell No, Employers Name, Tel No (W), Department, Status")
            
            # File uploader
            if file_type == "Excel (.xlsx)":
                uploaded_file = st.file_uploader("Choose Excel file", type="xlsx", key="client_file")
            else:
                uploaded_file = st.file_uploader("Choose CSV file", type="csv", key="client_file")
            
            if uploaded_file is not None:
                try:
                    # Read file based on type
                    if file_type == "Excel (.xlsx)":
                        import openpyxl
                        df = pd.read_excel(uploaded_file)
                    else:
                        df = pd.read_csv(uploaded_file)
                    
                    st.write(f"✅ Loaded {len(df)} records")
                    st.dataframe(df.head(10))
                    
                    # Processing function
                    def parse_and_validate(df, list_type):
                        """Parse and validate client data based on list type"""
                        clients = []
                        loans = []
                        errors = []
                        
                        # Define column mappings based on list type
                        if list_type == "Active Clients":
                            # Active list columns
                            col_map = {
                                'client_no': ['Client', 'No', 'Client No', 'ClientNo'],
                                'name_surname': ['Name & Surname', 'Name and Surname', 'Name'],
                                'due_date': ['Due Date', 'DueDate'],
                                'mobile': ['Mobile', 'Cell No', 'CellNo', 'Phone'],
                                'work_phone': ['Work Phone', 'WorkPhone', 'Phone'],
                                'employer': ['Employers Name', 'EmployersName', 'Employer'],
                                'address': ['Address'],
                                'area': ['Area'],
                                'sal_freq': ['Sal Freq', 'SalFreq', 'Salary Frequency'],
                                'received': ['Received'],
                                'balance': ['Balance'],
                                'status': ['S', 'Status', 'Loan Status']
                            }
                        else:
                            # Non-active list columns
                            col_map = {
                                'client_no': ['Client', 'No', 'Client No', 'ClientNo'],
                                'initials': ['Initials'],
                                'surname': ['Surname'],
                                'id_number': ['Identity No', 'IdentityNo', 'ID Number'],
                                'gender': ['Gender'],
                                'tel_home': ['Tel No (H)', 'TelNo(H)', 'Tel No Home'],
                                'cell_no': ['Cell No', 'CellNo', 'Mobile'],
                                'employer': ['Employers Name', 'EmployersName', 'Employer'],
                                'tel_work': ['Tel No (W)', 'TelNo(W)', 'Tel No Work'],
                                'department': ['Department', 'Dept'],
                                'status': ['Status']
                            }
                        
                        # Find actual columns (case-insensitive, flexible)
                        df.columns = df.columns.str.strip()
                        actual_cols = {col: col for col in df.columns}
                        
                        for idx, row in df.iterrows():
                            try:
                                row_num = idx + 2  # Excel row number (1-indexed + header)
                                
                                if list_type == "Active Clients":
                                    # Parse active list
                                    client_no = None
                                    for col_variant in col_map['client_no']:
                                        if col_variant in df.columns:
                                            client_no = str(row[col_variant]).strip() if pd.notna(row[col_variant]) else None
                                            break
                                    
                                    name_surname = None
                                    for col_variant in col_map['name_surname']:
                                        if col_variant in df.columns:
                                            name_surname = str(row[col_variant]).strip() if pd.notna(row[col_variant]) else ""
                                            break
                                    
                                    mobile = None
                                    for col_variant in col_map['mobile']:
                                        if col_variant in df.columns:
                                            mobile = str(row[col_variant]).strip() if pd.notna(row[col_variant]) else None
                                            break
                                    
                                    due_date = None
                                    for col_variant in col_map['due_date']:
                                        if col_variant in df.columns:
                                            due_date_val = row[col_variant]
                                            if pd.notna(due_date_val):
                                                due_date = str(due_date_val).strip()
                                            break
                                    
                                    balance = 0.0
                                    for col_variant in col_map['balance']:
                                        if col_variant in df.columns:
                                            try:
                                                balance = float(row[col_variant]) if pd.notna(row[col_variant]) else 0.0
                                            except:
                                                balance = 0.0
                                            break
                                    
                                    status_code = 'A'
                                    for col_variant in col_map['status']:
                                        if col_variant in df.columns:
                                            status_code = str(row[col_variant]).strip().upper() if pd.notna(row[col_variant]) else 'A'
                                            break
                                    
                                    # Validate required fields
                                    if not client_no or not client_no.strip():
                                        errors.append(f"Row {row_num}: Missing Client No")
                                        continue
                                    
                                    if not name_surname or not name_surname.strip():
                                        errors.append(f"Row {row_num}: Missing Name & Surname")
                                        continue
                                    
                                    if not mobile or not mobile.strip():
                                        errors.append(f"Row {row_num}: Missing Mobile number")
                                        continue
                                    
                                    # Parse name
                                    name_parts = name_surname.split(' ', 1)
                                    first_name = name_parts[0]
                                    last_name = name_parts[1] if len(name_parts) > 1 else ''
                                    
                                    # Get optional fields
                                    address = ""
                                    for col_variant in col_map['address']:
                                        if col_variant in df.columns:
                                            address = str(row[col_variant]).strip() if pd.notna(row[col_variant]) else ""
                                            break
                                    
                                    employer = ""
                                    for col_variant in col_map['employer']:
                                        if col_variant in df.columns:
                                            employer = str(row[col_variant]).strip() if pd.notna(row[col_variant]) else ""
                                            break
                                    
                                    client_data = {
                                        'first_name': first_name,
                                        'last_name': last_name,
                                        'id_number': client_no,
                                        'phone': mobile,
                                        'email': '',
                                        'address': address,
                                        'total_gross': 0.0,
                                        'salary': 0.0,
                                        'employer': employer,
                                        'work_days': '',
                                        'pay_day': '',
                                        'bank_name': '',
                                        'account_no': '',
                                        'status': 'Active'
                                    }
                                    
                                    client_data['row_num'] = row_num
                                    clients.append(client_data)
                                    
                                    # Create loan record if balance > 0
                                    if balance > 0 or due_date:
                                        loan_status = 'Active' if status_code == 'A' else 'Settled'
                                        loan_data = {
                                            'due_date': due_date or '2099-12-31',
                                            'principal': balance,
                                            'balance': balance,
                                            'amount_paid': 0.0,
                                            'status': loan_status,
                                            'client_row': row_num  # Link to client by row
                                        }
                                        loans.append(loan_data)
                                    
                                else:
                                    # Parse non-active list
                                    client_no = None
                                    for col_variant in col_map['client_no']:
                                        if col_variant in df.columns:
                                            client_no = str(row[col_variant]).strip() if pd.notna(row[col_variant]) else None
                                            break
                                    
                                    initials = ""
                                    for col_variant in col_map['initials']:
                                        if col_variant in df.columns:
                                            initials = str(row[col_variant]).strip() if pd.notna(row[col_variant]) else ""
                                            break
                                    
                                    surname = ""
                                    for col_variant in col_map['surname']:
                                        if col_variant in df.columns:
                                            surname = str(row[col_variant]).strip() if pd.notna(row[col_variant]) else ""
                                            break
                                    
                                    id_number = ""
                                    for col_variant in col_map['id_number']:
                                        if col_variant in df.columns:
                                            id_number = str(row[col_variant]).strip() if pd.notna(row[col_variant]) else client_no
                                            break
                                    
                                    cell_no = None
                                    for col_variant in col_map['cell_no']:
                                        if col_variant in df.columns:
                                            cell_no = str(row[col_variant]).strip() if pd.notna(row[col_variant]) else None
                                            break
                                    
                                    tel_home = None
                                    if not cell_no:
                                        for col_variant in col_map['tel_home']:
                                            if col_variant in df.columns:
                                                tel_home = str(row[col_variant]).strip() if pd.notna(row[col_variant]) else None
                                                break
                                    
                                    mobile = cell_no or tel_home or ""
                                    
                                    employer = ""
                                    for col_variant in col_map['employer']:
                                        if col_variant in df.columns:
                                            employer = str(row[col_variant]).strip() if pd.notna(row[col_variant]) else ""
                                            break
                                    
                                    # Validate required fields
                                    if not client_no or not client_no.strip():
                                        errors.append(f"Row {row_num}: Missing Client No")
                                        continue
                                    
                                    if not surname or not surname.strip():
                                        errors.append(f"Row {row_num}: Missing Surname")
                                        continue
                                    
                                    if not mobile or not mobile.strip():
                                        errors.append(f"Row {row_num}: Missing phone number (Cell No or Tel No)")
                                        continue
                                    
                                    # Build name from initials + surname or use surname only
                                    first_name = initials if initials else surname[:1]
                                    last_name = surname
                                    
                                    client_data = {
                                        'first_name': first_name,
                                        'last_name': last_name,
                                        'id_number': id_number or client_no,
                                        'phone': mobile,
                                        'email': '',
                                        'address': '',
                                        'total_gross': 0.0,
                                        'salary': 0.0,
                                        'employer': employer,
                                        'work_days': '',
                                        'pay_day': '',
                                        'bank_name': '',
                                        'account_no': '',
                                        'status': 'Active'
                                    }
                                    
                                    client_data['row_num'] = row_num
                                    clients.append(client_data)
                                    # Non-active clients don't get loans created
                            
                            except Exception as e:
                                errors.append(f"Row {row_num}: {str(e)}")
                        
                        return clients, loans, errors
                    
                    # Parse data
                    with st.spinner("Parsing and validating data..."):
                        clients, loans, errors = parse_and_validate(df, list_type)
                    
                    # Display validation results
                    if errors:
                        st.error(f"⚠️ Found {len(errors)} validation errors:")
                        for error in errors[:10]:
                            st.write(f"  • {error}")
                        if len(errors) > 10:
                            st.write(f"  ... and {len(errors) - 10} more errors")
                    
                    st.success(f"✅ Ready to import {len(clients)} clients{' with ' + str(len(loans)) + ' loans' if loans else ''}")
                    
                    if clients and st.button("🚀 Import Clients", key="import_clients"):
                        with st.spinner(f"Importing {len(clients)} clients..."):
                            imported_count = 0
                            failed_count = 0
                            skipped_duplicates = 0
                            
                            with get_db() as conn:
                                # Get existing phones and IDs for duplicate checking
                                existing_phones = set(conn.execute("SELECT phone FROM clients WHERE tenant_id=? AND phone != ''", (tenant_id,)).fetchall())
                                existing_phones = {phone[0] for phone in existing_phones}
                                existing_ids = set(conn.execute("SELECT id_number FROM clients WHERE tenant_id=? AND id_number != ''", (tenant_id,)).fetchall())
                                existing_ids = {id_num[0] for id_num in existing_ids}
                                
                                # Batch insert clients (every 50 records)
                                batch_size = 50
                                client_id_map = {}  # Map from row_num to inserted client_id
                                
                                for i in range(0, len(clients), batch_size):
                                    batch = clients[i:i+batch_size]
                                    batch_to_insert = []
                                    
                                    for client_data in batch:
                                        row_num = client_data.pop('row_num')
                                        
                                        # Check for duplicates
                                        if client_data['phone'] in existing_phones:
                                            skipped_duplicates += 1
                                            continue
                                        if client_data['id_number'] in existing_ids:
                                            skipped_duplicates += 1
                                            continue
                                        
                                        batch_to_insert.append((
                                            client_data['first_name'], client_data['last_name'],
                                            client_data['id_number'], client_data['phone'],
                                            client_data['email'], client_data['address'],
                                            client_data['total_gross'], client_data['salary'],
                                            client_data['employer'], client_data['work_days'],
                                            client_data['pay_day'], client_data['bank_name'],
                                            client_data['account_no'], client_data['status'],
                                            row_num
                                        ))
                                        
                                        existing_phones.add(client_data['phone'])
                                        existing_ids.add(client_data['id_number'])
                                    
                                    if batch_to_insert:
                                        try:
                                            cursor = conn.cursor()
                                            # Insert and get IDs
                                            for row_data in batch_to_insert:
                                                row_num = row_data[-1]
                                                insert_data = row_data[:-1]
                                                cursor.execute("""
                                                    INSERT INTO clients (tenant_id, first_name, last_name, id_number, phone, email, address,
                                                                       total_gross, salary, employer, work_days, pay_day,
                                                                       bank_name, account_no, status)
                                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                                """, (tenant_id,) + insert_data)
                                                client_id_map[row_num] = cursor.lastrowid
                                                imported_count += 1
                                            conn.commit()
                                        except Exception as e:
                                            st.error(f"Batch import error: {str(e)}")
                                            failed_count += len(batch_to_insert)
                                
                                # Insert loans linked to imported clients (for active lists)
                                if loans:
                                    for loan_data in loans:
                                        try:
                                            client_row = loan_data.pop('client_row')
                                            if client_row in client_id_map:
                                                loan_data['client_id'] = client_id_map[client_row]
                                                conn.execute("""
                                                    INSERT INTO loans (tenant_id, client_id, due_date, principal, balance, amount_paid, status)
                                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                                """, (tenant_id, loan_data['client_id'], loan_data['due_date'], loan_data['principal'],
                                                      loan_data['balance'], loan_data['amount_paid'], loan_data['status']))
                                        except Exception as e:
                                            st.error(f"Loan creation error: {str(e)}")
                                    conn.commit()
                            
                            # Show results
                            st.success(f"✅ Import Complete!")
                            st.write(f"  • Imported: {imported_count} clients")
                            if loans:
                                st.write(f"  • Loans created: {len(loans)}")
                            if skipped_duplicates > 0:
                                st.write(f"  • Skipped (duplicates): {skipped_duplicates}")
                            if failed_count > 0:
                                st.write(f"  • Failed: {failed_count}")
                            
                            st.rerun()
                
                except Exception as e:
                    st.error(f"❌ Error processing file: {str(e)}")
        
        
        with import_tab_payments:
            st.markdown("**Payment Sheet Import** - Upload payment records. Required columns: Client No/Mobile, Amount, Date. Optional: Type, Loan ID.")
            
            payment_file = st.file_uploader("Choose Payment CSV file", type="csv", key="payment_file")
            
            if payment_file is not None:
                df_payment = pd.read_csv(payment_file)
                st.write("Preview of payment data:")
                st.dataframe(df_payment.head())
                
                # Check required columns - flexible, can use Client No or Mobile
                has_client_no = 'Client No' in df_payment.columns
                has_mobile = 'Mobile' in df_payment.columns
                has_amount = 'Amount' in df_payment.columns
                has_date = 'Date' in df_payment.columns
                
                if not ((has_client_no or has_mobile) and has_amount and has_date):
                    st.error("Missing required columns. Need: Client identifier (Client No or Mobile), Amount, Date")
                else:
                    # Validate data
                    errors_payment = []
                    for idx, row in df_payment.iterrows():
                        client_id = None
                        if has_client_no and pd.notna(row.get('Client No')):
                            client_id = str(row['Client No']).strip()
                        elif has_mobile and pd.notna(row.get('Mobile')):
                            client_id = str(row['Mobile']).strip()
                        
                        if not client_id:
                            errors_payment.append(f"Row {idx+1}: Missing client identifier (Client No or Mobile)")
                        if pd.isna(row['Amount']) or float(row['Amount']) <= 0:
                            errors_payment.append(f"Row {idx+1}: Invalid or missing amount")
                        if pd.isna(row['Date']):
                            errors_payment.append(f"Row {idx+1}: Missing date")
                    
                    if errors_payment:
                        st.error("Data validation errors:")
                        for error in errors_payment[:5]:  # Show first 5 errors
                            st.write(error)
                        if len(errors_payment) > 5:
                            st.write(f"... and {len(errors_payment) - 5} more errors")
                    else:
                        if st.button("🚀 Import Payments", key="import_payments"):
                            imported_payments = 0
                            failed_payments = 0
                            with get_db() as conn:
                                for _, row in df_payment.iterrows():
                                    try:
                                        # Find client and their loan
                                        client_identifier = None
                                        if has_client_no and pd.notna(row.get('Client No')):
                                            client_identifier = str(row['Client No']).strip()
                                            client_query = "SELECT client_id FROM clients WHERE tenant_id=? AND id_number = ?"
                                        elif has_mobile:
                                            client_identifier = str(row['Mobile']).strip()
                                            client_query = "SELECT client_id FROM clients WHERE tenant_id=? AND phone = ?"
                                        
                                        client_result = conn.execute(client_query, (tenant_id, client_identifier)).fetchone()
                                        
                                        if client_result:
                                            client_id = client_result[0]
                                            
                                            # Find active loan for this client
                                            loan_result = conn.execute(
                                                "SELECT loan_id FROM loans WHERE tenant_id=? AND client_id = ? AND status = 'Active' ORDER BY created_at DESC LIMIT 1",
                                                (tenant_id, client_id)
                                            ).fetchone()
                                            
                                            if loan_result:
                                                loan_id = loan_result[0]
                                                
                                                # Insert payment
                                                payment_data = {
                                                    'loan_id': loan_id,
                                                    'amount': float(row['Amount']),
                                                    'date': str(row['Date']).strip(),
                                                    'type': str(row.get('Type', 'Payment')).strip()
                                                }
                                                
                                                conn.execute("""
                                                    INSERT INTO payment_history (tenant_id, loan_id, amount, date, type)
                                                    VALUES (?, ?, ?, ?, ?)
                                                """, (tenant_id,) + tuple(payment_data.values()))
                                                
                                                # Update loan balance
                                                conn.execute(
                                                    "UPDATE loans SET balance = balance - ?, amount_paid = amount_paid + ? WHERE tenant_id=? AND loan_id = ?",
                                                    (payment_data['amount'], payment_data['amount'], tenant_id, loan_id)
                                                )
                                                
                                                imported_payments += 1
                                            else:
                                                failed_payments += 1
                                                st.warning(f"No active loan found for client {client_identifier}")
                                        else:
                                            failed_payments += 1
                                            st.warning(f"Client not found: {client_identifier}")
                                    
                                    except Exception as e:
                                        st.error(f"Failed to import payment for row {idx+1}: {str(e)}")
                                        failed_payments += 1
                                
                                conn.commit()
                            
                            st.success(f"Payment Import complete! Imported: {imported_payments}, Failed: {failed_payments}")
                            if imported_payments > 0:
                                st.rerun()