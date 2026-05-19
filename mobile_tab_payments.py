import datetime
from pathlib import Path
from typing import List, Optional

import streamlit as st

from DFUS_30_Suite.config import get_default_db_path
from DFUS_30_Suite.db_helpers import get_db_connection, get_clients_by_agent, get_loan_details, record_payment


def _get_db_path() -> str:
    if st.session_state.get("config") and st.session_state.config.get("db_path"):
        return st.session_state.config.get("db_path")
    return get_default_db_path()


def _ensure_unallocated_eft_queue_table(db_path: str):
    with get_db_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS unallocated_eft_queue (
                queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                assigned_agent_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                bank_name TEXT,
                account_no TEXT,
                reference TEXT,
                received_date TEXT,
                status TEXT DEFAULT 'Pending',
                allocated_loan_id INTEGER,
                allocated_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def _get_unallocated_efts(db_path: str, tenant_id: int, agent_id: int) -> List[dict]:
    with get_db_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT queue_id, amount, bank_name, account_no, reference, received_date, status, allocated_loan_id, allocated_at, created_at"
            " FROM unallocated_eft_queue"
            " WHERE tenant_id = ? AND assigned_agent_id = ? AND status = 'Pending'"
            " ORDER BY created_at DESC",
            (tenant_id, agent_id),
        ).fetchall()
    return [dict(row) for row in rows]


def _get_loans_for_client(db_path: str, tenant_id: int, client_id: int) -> List[dict]:
    with get_db_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT loan_id, principal, balance, status, due_date"
            " FROM loans"
            " WHERE tenant_id = ? AND client_id = ?"
            " ORDER BY due_date ASC",
            (tenant_id, client_id),
        ).fetchall()
    return [dict(row) for row in rows]


def _create_unallocated_eft(db_path: str, tenant_id: int, agent_id: int, amount: float, bank_name: str, account_no: str, reference: str, received_date: str) -> int:
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO unallocated_eft_queue (tenant_id, assigned_agent_id, amount, bank_name, account_no, reference, received_date)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tenant_id, agent_id, amount, bank_name, account_no, reference, received_date),
        )
        conn.commit()
        return cursor.lastrowid


def _mark_eft_allocated(db_path: str, queue_id: int, loan_id: int):
    with get_db_connection(db_path) as conn:
        conn.execute(
            "UPDATE unallocated_eft_queue"
            " SET status = 'Allocated', allocated_loan_id = ?, allocated_at = ?"
            " WHERE queue_id = ?",
            (loan_id, datetime.datetime.now().isoformat(), queue_id),
        )
        conn.commit()


def render_mobile_payments(agent_id: int):
    if not agent_id:
        st.error("Payment allocation requires a valid agent_id.")
        return
    if "tenant_id" not in st.session_state or not st.session_state.get("tenant_id"):
        st.error("Tenant context is required for payment allocation.")
        return

    tenant_id = st.session_state.tenant_id
    db_path = _get_db_path()
    _ensure_unallocated_eft_queue_table(db_path)

    st.title("Unallocated EFT Payments")
    st.markdown(
        "Track incoming EFTs that have not yet been matched to a client loan, then allocate them safely to assigned borrowers."
    )

    with st.expander("Log New Unallocated EFT"):
        eft_amount = st.number_input("Amount Received (ZAR)", min_value=1.0, value=100.0, format="%.2f", key="eft_amount")
        eft_bank = st.text_input("Bank Name", key="eft_bank")
        eft_account = st.text_input("Account Number", key="eft_account")
        eft_reference = st.text_input("Transaction Reference", key="eft_reference")
        eft_date = st.date_input("Received Date", value=datetime.date.today(), key="eft_received_date")

        if st.button("Add Unallocated EFT", key="add_unallocated_eft"):
            if eft_amount <= 0:
                st.error("EFT amount must be greater than zero.")
            else:
                queue_id = _create_unallocated_eft(
                    db_path=db_path,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    amount=float(eft_amount),
                    bank_name=eft_bank,
                    account_no=eft_account,
                    reference=eft_reference,
                    received_date=eft_date.isoformat(),
                )
                st.success(f"Unallocated EFT added to queue (ID: {queue_id}).")
                st.experimental_rerun()

    unallocated_rows = _get_unallocated_efts(db_path, tenant_id, agent_id)
    if not unallocated_rows:
        st.info("No unallocated EFT queue items found for your agent. Add one above or synchronize bank receipts.")
        return

    st.markdown(f"### Pending Unallocated EFTs ({len(unallocated_rows)})")
    clients = get_clients_by_agent(db_path, tenant_id, agent_id)
    client_options = {f"{c['client_id']} - {c['first_name']} {c['last_name']}": c['client_id'] for c in clients}

    for row in unallocated_rows:
        queue_id = row["queue_id"]
        with st.container():
            st.markdown(
                f"<div style='border:1px solid #ccc; padding:16px; border-radius:12px; margin-bottom:16px;'>"
                f"<strong>EFT #{queue_id}</strong> — R{row['amount']:.2f} from {row.get('bank_name') or 'Unknown Bank'}<br>"
                f"Reference: {row.get('reference') or 'N/A'}<br>"
                f"Received: {row.get('received_date') or row.get('created_at')}"
                f"</div>",
                unsafe_allow_html=True,
            )
            if not client_options:
                st.warning("No assigned clients are available to allocate this EFT. Please onboard borrowers first.")
                continue

            selected_client_label = st.selectbox(
                "Assign to Client",
                list(client_options.keys()),
                key=f"allocate_client_{queue_id}",
            )
            selected_client_id = client_options[selected_client_label]
            loans = _get_loans_for_client(db_path, tenant_id, selected_client_id)
            loan_options = {
                f"{loan['loan_id']} - Balance R{loan['balance']:.2f} ({loan['status']})": loan['loan_id']
                for loan in loans
            }
            if not loan_options:
                st.warning("Selected client has no loans. Create or assign a loan before allocating EFT payments.")
                continue

            selected_loan_label = st.selectbox(
                "Select Loan to Allocate",
                list(loan_options.keys()),
                key=f"allocate_loan_{queue_id}",
            )
            selected_loan_id = loan_options[selected_loan_label]
            loan_value = get_loan_details(db_path, tenant_id, selected_loan_id)
            st.markdown(
                f"Balance: R{loan_value.get('balance', 0.0):.2f} | Status: {loan_value.get('status', 'Unknown')}"
            )

            if st.button("Match & Allocate", key=f"match_allocate_{queue_id}"):
                payment_date = row.get("received_date") or datetime.date.today().isoformat()
                record_payment(
                    db_path=db_path,
                    tenant_id=tenant_id,
                    loan_id=selected_loan_id,
                    agent_id=agent_id,
                    amount=float(row['amount']),
                    pay_date=payment_date,
                    payment_type="EFT Allocation",
                )
                _mark_eft_allocated(db_path, queue_id, selected_loan_id)
                st.success(f"EFT #{queue_id} allocated to loan {selected_loan_id}.")
                st.experimental_rerun()
