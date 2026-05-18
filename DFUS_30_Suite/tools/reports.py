import streamlit as st
import pandas as pd
import io
import os
import sqlite3
from datetime import datetime

def run(get_db):
    tenant_id = st.session_state.get('tenant_id')
    if not tenant_id:
        st.error("No tenant selected. Please log in again.")
        return

    st.header("📊 Reports & Exports")

    try:
        with get_db() as conn:
            # Fixed: Changed 'surname' to 'last_name' to match the database
            df_clients = pd.read_sql_query("""
                SELECT client_id, first_name, last_name, id_number, phone, status as client_status 
                FROM clients
                WHERE tenant_id = ?
            """, conn, params=(tenant_id,))
            
            # Simplified query to pull essential loan data
            df_loans = pd.read_sql_query("""
                SELECT loan_id, client_id, balance, status as loan_status, principal, due_date 
                FROM loans
                WHERE tenant_id = ?
            """, conn, params=(tenant_id,))

    except Exception as e:
        st.error(f"Database Error: {e}")
        return

    if df_clients.empty:
        st.warning("No client data found.")
        return

    # Identify Active vs Non-Active clients
    active_client_ids = df_loans[df_loans['loan_status'] == 'Active']['client_id'].unique()
    
    active_mask = df_clients['client_id'].isin(active_client_ids)
    df_active_clients = df_clients[active_mask].copy()
    df_non_active_clients = df_clients[~active_mask].copy()

    tab1, tab2 = st.tabs(["✅ Active & Outstanding", "📁 Non-Active / Available"])

    # --- TAB 1: ACTIVE LEDGER ---
    with tab1:
        st.subheader("Current Active Loan Book")
        
        # 
        active_loans_detail = df_loans[df_loans['loan_status'] == 'Active'].merge(
            df_active_clients, on='client_id'
        )
        
        if not active_loans_detail.empty:
            # Map columns to user-friendly headers
            disp_active = active_loans_detail[['client_id', 'first_name', 'last_name', 'id_number', 'principal', 'balance', 'due_date']]
            disp_active.columns = ['ID', 'First Name', 'Last Name', 'Identity No', 'Principal', 'Current Balance', 'Due Date']
            
            st.write(f"**Total Active Loans:** {len(disp_active)}")
            st.dataframe(disp_active, width='stretch')

            # Excel Export Logic
            output_a = io.BytesIO()
            with pd.ExcelWriter(output_a, engine='xlsxwriter') as writer:
                disp_active.to_excel(writer, index=False, sheet_name='Active_Ledger')
            st.download_button("📥 Export Active List", output_a.getvalue(), "Active_Ledger.xlsx", "application/vnd.ms-excel")
        else:
            st.info("No active loans to report.")

    # --- TAB 2: NON-ACTIVE ---
    with tab2:
        st.subheader("Database Clients with No Active Debt")
        
        if not df_non_active_clients.empty:
            disp_non_active = df_non_active_clients[['client_id', 'first_name', 'last_name', 'id_number', 'phone', 'client_status']]
            disp_non_active.columns = ['ID', 'First Name', 'Last Name', 'Identity No', 'Phone Number', 'System Status']
            
            st.write(f"**Total Available Clients:** {len(disp_non_active)}")
            st.dataframe(disp_non_active, width='stretch')

            # Excel Export Logic
            output_na = io.BytesIO()
            with pd.ExcelWriter(output_na, engine='xlsxwriter') as writer:
                disp_non_active.to_excel(writer, index=False, sheet_name='Non_Active_List')
            st.download_button("📥 Export Non-Active List", output_na.getvalue(), "Non_Active_Ledger.xlsx", "application/vnd.ms-excel")
        else:
            st.info("All clients currently have active loans.")

    # --- SUMMARY METRICS ---
    st.markdown("---")
    if not df_loans.empty:
        total_book = df_loans[df_loans['loan_status'] == 'Active']['balance'].sum()
        st.metric("Total Outstanding Book Value", f"R {total_book:,.2f}")