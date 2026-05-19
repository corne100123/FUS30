import datetime
import sqlite3

import streamlit as st


def _ensure_loan_approval_history_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS loan_approval_history (
            approval_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            loan_id INTEGER NOT NULL,
            approver_user_id INTEGER,
            approver_role TEXT,
            action TEXT NOT NULL,
            comments TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id),
            FOREIGN KEY(loan_id) REFERENCES loans(loan_id)
        )
        """
    )
    conn.commit()


def _fetch_pending_loans(conn, tenant_id):
    conn.row_factory = sqlite3.Row
    query = """
        SELECT
            l.loan_id,
            l.client_id,
            l.agent_id,
            l.principal,
            l.balance,
            l.due_date,
            l.status,
            l.created_at,
            c.first_name,
            c.last_name,
            c.phone AS client_phone,
            c.address AS client_address,
            a.name AS agent_name,
            lc.contract_path,
            lc.signature_path
        FROM loans l
        LEFT JOIN clients c ON c.client_id = l.client_id AND c.tenant_id = l.tenant_id
        LEFT JOIN agents a ON a.agent_id = l.agent_id AND a.tenant_id = l.tenant_id
        LEFT JOIN loan_contracts lc ON lc.loan_id = l.loan_id AND lc.tenant_id = l.tenant_id
        WHERE l.tenant_id = ?
          AND l.status = 'Pending_Manager_Approval'
        ORDER BY l.created_at DESC
    """
    return [dict(row) for row in conn.execute(query, (tenant_id,)).fetchall()]


def _record_approval(conn, tenant_id, loan_id, action, comments):
    approver_user_id = st.session_state.get('user_id')
    approver_role = st.session_state.get('role')
    conn.execute(
        "UPDATE loans SET status = ? WHERE tenant_id = ? AND loan_id = ?",
        (action, tenant_id, loan_id),
    )
    conn.execute(
        "INSERT INTO loan_approval_history (tenant_id, loan_id, approver_user_id, approver_role, action, comments) VALUES (?, ?, ?, ?, ?, ?)",
        (tenant_id, loan_id, approver_user_id, approver_role, action, comments),
    )
    conn.commit()


def run(get_db):
    tenant_id = st.session_state.get('tenant_id')
    role = st.session_state.get('role')

    if role not in ['Admin', 'Manager']:
        st.error('Access denied. Admin or Manager privileges required.')
        return

    if not tenant_id:
        st.error('Tenant context is required. Please log in again.')
        return

    st.header('🧾 Loan Approval Queue')
    st.markdown(
        'Review loan applications submitted by field agents and approve or reject them for your tenant.'
    )

    try:
        with get_db() as conn:
            _ensure_loan_approval_history_table(conn)
            pending_loans = _fetch_pending_loans(conn, tenant_id)
    except Exception as exc:
        st.error(f'Unable to load pending loans: {exc}')
        return

    if not pending_loans:
        st.success('No pending loan applications found for approval.')
        return

    st.markdown(f'### Pending Applications ({len(pending_loans)})')

    for loan in pending_loans:
        borrower = f"{loan.get('first_name') or 'Unknown'} {loan.get('last_name') or ''}".strip()
        agent_name = loan.get('agent_name') or 'Unassigned Agent'
        loan_label = f"Loan #{loan['loan_id']} — {borrower}"

        with st.expander(loan_label, expanded=False):
            st.write(f"**Agent:** {agent_name}")
            st.write(f"**Client ID:** {loan.get('client_id')} | **Loan ID:** {loan['loan_id']}")
            st.write(f"**Principal:** ZAR {float(loan.get('principal') or 0.0):,.2f}")
            st.write(f"**Balance:** ZAR {float(loan.get('balance') or 0.0):,.2f}")
            st.write(f"**Due Date:** {loan.get('due_date') or 'N/A'}")
            st.write(f"**Submitted:** {loan.get('created_at') or 'N/A'}")
            st.write(f"**Client Phone:** {loan.get('client_phone') or 'N/A'}")
            st.write(f"**Client Address:** {loan.get('client_address') or 'N/A'}")
            if loan.get('contract_path'):
                st.write(f"Contract File: {loan.get('contract_path')}")
            if loan.get('signature_path'):
                st.write(f"Signature File: {loan.get('signature_path')}")

            comments_key = f"approval_comments_{loan['loan_id']}"
            comments = st.text_area(
                'Approval Comments (optional)',
                value=st.session_state.get(comments_key, ''),
                key=comments_key,
                height=100,
            )
            st.session_state[comments_key] = comments

            cols = st.columns([1, 1])
            with cols[0]:
                if st.button('Approve Loan', key=f"approve_{loan['loan_id']}"):
                    try:
                        with get_db() as conn:
                            _record_approval(conn, tenant_id, loan['loan_id'], 'Active', comments)
                        st.success(f"Loan #{loan['loan_id']} approved and activated.")
                        st.experimental_rerun()
                    except Exception as exc:
                        st.error(f'Unable to approve loan: {exc}')
            with cols[1]:
                if st.button('Reject Loan', key=f"reject_{loan['loan_id']}"):
                    try:
                        with get_db() as conn:
                            _record_approval(conn, tenant_id, loan['loan_id'], 'Rejected', comments)
                        st.success(f"Loan #{loan['loan_id']} rejected.")
                        st.experimental_rerun()
                    except Exception as exc:
                        st.error(f'Unable to reject loan: {exc}')
