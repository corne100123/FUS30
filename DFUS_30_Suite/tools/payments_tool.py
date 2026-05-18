import streamlit as st
import pandas as pd
from datetime import datetime
import sqlite3
import os

# --- 2. MAIN PAYMENTS TOOL ---
def run(get_db, audit_tool_ignored):
    st.header("💸 Payments")
    tenant_id = st.session_state.tenant_id

    # --- STEP 1: SELECT LOAN ---
    with get_db() as conn:
        query = """
            SELECT l.loan_id, c.first_name, c.last_name, l.principal, l.balance 
            FROM loans l
            JOIN clients c ON l.client_id = c.client_id
            WHERE l.status = 'Active' AND l.tenant_id = ?
        """
        # Filter for agents
        if st.session_state.get('role') == 'Agent':
            query += f" AND c.assigned_agent_id = {st.session_state.user_id}"
        
        active_loans = pd.read_sql_query(query, conn, params=(tenant_id,))

    if active_loans.empty:
        st.info("No active loans found.")
        return

    active_loans['display'] = (
        active_loans['first_name'] + " " + 
        active_loans['last_name'] + " (Owes: R" + 
        active_loans['balance'].astype(str) + ")"
    )
    
    selected_loan_str = st.selectbox("Select Loan", active_loans['display'])
    loan_data = active_loans[active_loans['display'] == selected_loan_str].iloc[0]
    loan_id = int(loan_data['loan_id'])

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("💳 Record Payment")
        with st.form("pay_form"):
            pay_amount = st.number_input("Amount Paid (R)", min_value=1.0, value=float(loan_data['balance']))
            # Changed 'method' to 'type' to match your DB column name
            pay_type = st.selectbox("Method", ["Bank EFT", "Cash", "Debit Order", "Stop Order"])
            pay_date = st.date_input("Date of Payment", datetime.now())
            
            if st.form_submit_button("Confirm Payment"):
                try:
                    with get_db() as conn:
                        cursor = conn.cursor()

                        # Get current agent ID from session state
                        agent_username = st.session_state.get('username')
                        if agent_username:
                            agent_id = cursor.execute("SELECT user_id FROM users WHERE tenant_id=? AND username = ?", (tenant_id, agent_username)).fetchone()
                            agent_id = agent_id[0] if agent_id else None
                        else:
                            agent_id = None

                        # UPDATED: Using 'date' and 'type' to match your existing table
                        cursor.execute("""
                            INSERT INTO payment_history (tenant_id, loan_id, amount, date, type, agent_id)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (tenant_id, loan_id, pay_amount, pay_date.strftime('%Y-%m-%d'), pay_type, agent_id))

                        # Update balance
                        new_balance = float(loan_data['balance']) - pay_amount
                        new_status = 'Settled' if new_balance <= 0 else 'Active'

                        cursor.execute("UPDATE loans SET balance = ?, status = ? WHERE tenant_id=? AND loan_id = ?",
                                     (new_balance, new_status, tenant_id, loan_id))

                        conn.commit()
                        st.success("✅ Payment Recorded!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Payment Error: {e}")

    with col2:
        st.subheader("📄 History")
        with get_db() as conn:
            # UPDATED: Selecting 'date' and 'type' instead of 'date_paid' and 'method'
            hist_query = f"SELECT date, amount, type FROM payment_history WHERE tenant_id = {tenant_id} AND loan_id = {loan_id}"
            history = pd.read_sql_query(hist_query, conn)
        
        if not history.empty:
            st.dataframe(history, use_container_width=True)
        else:
            st.info("No payments recorded yet.")