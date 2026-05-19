import datetime
import os
import tempfile
from pathlib import Path
from typing import Optional

import streamlit as st
from PIL import Image
from streamlit_drawable_canvas import st_canvas

from DFUS_30_Suite.config import get_default_db_path
from DFUS_30_Suite.db_helpers import get_db_connection
from DFUS_30_Suite.invoice_modules.file_storage import get_file_storage


def _get_db_path() -> str:
    if st.session_state.get("config") and st.session_state.config.get("db_path"):
        return st.session_state.config.get("db_path")
    return get_default_db_path()


def _ensure_loan_contracts_table(db_path: str):
    with get_db_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS loan_contracts (
                contract_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                agent_id INTEGER NOT NULL,
                client_id INTEGER NOT NULL,
                loan_id INTEGER NOT NULL,
                contract_path TEXT,
                signature_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id),
                FOREIGN KEY(agent_id) REFERENCES agents(agent_id),
                FOREIGN KEY(client_id) REFERENCES clients(client_id),
                FOREIGN KEY(loan_id) REFERENCES loans(loan_id)
            )
            """
        )
        conn.commit()


def _save_signature_png(canvas_result, original_name: str) -> Optional[str]:
    if canvas_result is None or canvas_result.image_data is None:
        return None

    image_data = canvas_result.image_data
    if hasattr(image_data, "max") and image_data.max() == 0:
        return None

    image = Image.fromarray(image_data.astype("uint8"))
    file_storage = get_file_storage()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
        image.save(tmp_file.name, format="PNG")
        temp_path = Path(tmp_file.name)

    unique_filename = file_storage.save_document_file(
        temp_path,
        category="contracts",
        original_name=original_name,
    )

    try:
        temp_path.unlink()
    except Exception:
        pass

    if not unique_filename:
        return None

    return str(file_storage.storage_dir / "contracts" / unique_filename)


def _save_contract_document(term_details: str, contract_name: str) -> Optional[str]:
    file_storage = get_file_storage()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8") as tmp_file:
        tmp_file.write(term_details)
        temp_path = Path(tmp_file.name)

    unique_filename = file_storage.save_document_file(
        temp_path,
        category="contracts",
        original_name=contract_name,
    )

    try:
        temp_path.unlink()
    except Exception:
        pass

    if not unique_filename:
        return None

    return str(file_storage.storage_dir / "contracts" / unique_filename)


def _get_assigned_clients(db_path: str, tenant_id: int, agent_id: int):
    with get_db_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT client_id, first_name, last_name, phone, status"
            " FROM clients"
            " WHERE tenant_id = ? AND assigned_agent_id = ?"
            " ORDER BY last_name, first_name ASC",
            (tenant_id, agent_id),
        ).fetchall()
    return [dict(row) for row in rows]


def _create_client(db_path: str, tenant_id: int, agent_id: int, first_name: str, last_name: str, phone: str, address: str, id_number: str, bank_name: str, account_no: str) -> int:
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO clients (tenant_id, assigned_agent_id, first_name, last_name, phone, address, id_number, bank_name, account_no, status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Active')",
            (tenant_id, agent_id, first_name, last_name, phone, address, id_number, bank_name, account_no),
        )
        conn.commit()
        return cursor.lastrowid


def _create_loan(db_path: str, tenant_id: int, agent_id: int, client_id: int, principal: float, due_date: str) -> int:
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO loans (tenant_id, client_id, agent_id, due_date, principal, balance, amount_paid, status)"
            " VALUES (?, ?, ?, ?, ?, ?, 0.0, 'Pending_Manager_Approval')",
            (tenant_id, client_id, agent_id, due_date, principal, principal),
        )
        conn.commit()
        return cursor.lastrowid


def _create_contract_record(db_path: str, tenant_id: int, agent_id: int, client_id: int, loan_id: int, contract_path: Optional[str], signature_path: Optional[str]) -> int:
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO loan_contracts (tenant_id, agent_id, client_id, loan_id, contract_path, signature_path)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (tenant_id, agent_id, client_id, loan_id, contract_path, signature_path),
        )
        conn.commit()
        return cursor.lastrowid


def _get_pending_loans(db_path: str, tenant_id: int, agent_id: int):
    with get_db_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT l.loan_id, l.client_id, l.principal, l.balance, l.due_date, l.status, c.first_name, c.last_name, lc.contract_path, lc.signature_path"
            " FROM loans l"
            " JOIN clients c ON c.client_id = l.client_id"
            " LEFT JOIN loan_contracts lc ON lc.loan_id = l.loan_id"
            " WHERE l.tenant_id = ? AND l.agent_id = ? AND l.status = 'Pending_Manager_Approval'"
            " ORDER BY l.created_at DESC",
            (tenant_id, agent_id),
        ).fetchall()
    return [dict(row) for row in rows]


def render_mobile_loans(agent_id: int):
    if not agent_id:
        st.error("Loan origination requires a valid agent_id.")
        return
    if "tenant_id" not in st.session_state or not st.session_state.get("tenant_id"):
        st.error("Tenant context is required for loan origination.")
        return

    tenant_id = st.session_state.tenant_id
    db_path = _get_db_path()
    _ensure_loan_contracts_table(db_path)

    st.title("Loan Origination")
    st.markdown(
        "Use this screen to onboard a borrower, capture a digital signature, and create a pending loan application for manager approval."
    )

    with st.expander("Onboard a New Client"):
        st.write("Create a new client record before assigning a loan to them.")
        new_first_name = st.text_input("First Name", key="loan_onboard_first")
        new_last_name = st.text_input("Last Name", key="loan_onboard_last")
        new_phone = st.text_input("Phone Number", key="loan_onboard_phone")
        new_id_number = st.text_input("ID Number", key="loan_onboard_id")
        new_address = st.text_area("Address", key="loan_onboard_address")
        new_bank_name = st.text_input("Bank Name", key="loan_onboard_bank")
        new_account_no = st.text_input("Account Number", key="loan_onboard_account")

        if st.button("Create Client Record"):
            if not new_first_name or not new_last_name or not new_phone:
                st.error("First name, last name and phone are required to onboard a client.")
            else:
                client_id = _create_client(
                    db_path=db_path,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    first_name=new_first_name,
                    last_name=new_last_name,
                    phone=new_phone,
                    address=new_address,
                    id_number=new_id_number,
                    bank_name=new_bank_name,
                    account_no=new_account_no,
                )
                st.success(f"Client onboarded successfully (ID: {client_id}).")
                st.experimental_rerun()

    assigned_clients = _get_assigned_clients(db_path, tenant_id, agent_id)
    if not assigned_clients:
        st.warning("No assigned clients found. Onboard a client first before submitting a loan application.")
        return

    client_options = {
        f"{row['client_id']} - {row['first_name']} {row['last_name']}": row['client_id']
        for row in assigned_clients
    }

    st.subheader("New Loan Application")
    selected_client_label = st.selectbox("Select Borrower", list(client_options.keys()), key="loan_client_select")
    selected_client_id = client_options[selected_client_label]
    principal = st.number_input("Requested Principal (ZAR)", min_value=100.0, value=500.0, step=50.0, format="%.2f")
    term_days = st.number_input("Repayment Term (days)", min_value=7, max_value=180, value=30, step=7)
    due_date = (datetime.date.today() + datetime.timedelta(days=int(term_days))).isoformat()

    st.markdown("#### Signature Capture")
    st.caption("Use the canvas below to capture the borrower signature or acknowledgement signature.")
    canvas_result = st_canvas(
        fill_color="rgba(255, 255, 255, 0)",
        stroke_width=3,
        stroke_color="#000000",
        background_color="#ffffff",
        height=200,
        width=600,
        drawing_mode="freedraw",
        key="loan_signature_canvas",
    )

    if st.button("Submit Loan Application", key="submit_loan_application"):
        if principal <= 0:
            st.error("Loan amount must be greater than zero.")
            return

        signature_path = _save_signature_png(canvas_result, f"loan_signature_{selected_client_id}.png")
        if not signature_path:
            st.error("Please capture the client's signature before submitting the application.")
            return

        loan_id = _create_loan(db_path, tenant_id, agent_id, selected_client_id, float(principal), due_date)
        contract_body = (
            f"Loan Contract\n"
            f"Tenant ID: {tenant_id}\n"
            f"Agent ID: {agent_id}\n"
            f"Borrower Client ID: {selected_client_id}\n"
            f"Loan ID: {loan_id}\n"
            f"Principal: ZAR {principal:.2f}\n"
            f"Due Date: {due_date}\n"
            f"Status: Pending_Manager_Approval\n"
            f"Signature File: {signature_path}\n"
            f"Created At: {datetime.datetime.now().isoformat()}\n"
        )
        contract_path = _save_contract_document(contract_body, f"loan_contract_{loan_id}.txt")
        _create_contract_record(db_path, tenant_id, agent_id, selected_client_id, loan_id, contract_path, signature_path)

        st.success(f"Loan application created with ID {loan_id} and pending manager approval.")
        if contract_path:
            st.markdown(f"**Contract file:** {contract_path}")
            try:
                with open(contract_path, "rb") as fh:
                    st.download_button(
                        label="Download Loan Contract",
                        data=fh.read(),
                        file_name=f"loan_contract_{loan_id}.txt",
                        mime="text/plain",
                    )
            except FileNotFoundError:
                st.info("Loan contract file was saved, but it cannot be downloaded from this session.")

    pending_loans = _get_pending_loans(db_path, tenant_id, agent_id)
    if pending_loans:
        st.markdown("---")
        st.subheader("Pending Manager Approval")
        for loan in pending_loans:
            st.markdown(
                f"**Loan {loan['loan_id']}** — {loan['first_name']} {loan['last_name']} | "
                f"Principal: ZAR {loan['principal']:.2f} | Due: {loan['due_date']}"
            )
            if loan.get("contract_path"):
                st.write(f"Contract: {loan['contract_path']}")
            if loan.get("signature_path"):
                st.write(f"Signature file: {loan['signature_path']}")
            st.markdown("---")
