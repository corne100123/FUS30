import base64
import hashlib
import os
import tempfile
from datetime import datetime
from pathlib import Path

import streamlit as st
from cryptography.fernet import Fernet

from DFUS_30_Suite.config import get_default_db_path
from DFUS_30_Suite.db_helpers import get_cashup_summary, get_db_connection
from DFUS_30_Suite.invoice_modules.file_storage import get_file_storage


def _get_db_path() -> str:
    if st.session_state.get("config") and st.session_state.config.get("db_path"):
        return st.session_state.config.get("db_path")
    return get_default_db_path()


def _build_encryption_key() -> bytes:
    secret = os.environ.get("FUS30_FILE_STORAGE_SECRET")
    if not secret:
        raise RuntimeError(
            "Encryption key not configured. Set FUS30_FILE_STORAGE_SECRET to a secure value."
        )
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _encrypt_bytes(payload: bytes) -> bytes:
    key = _build_encryption_key()
    return Fernet(key).encrypt(payload)


def _save_receipt_file(uploaded_file) -> str | None:
    if uploaded_file is None:
        return None

    file_storage = get_file_storage()
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix) as tmp:
        file_bytes = uploaded_file.read()
        encrypted_bytes = _encrypt_bytes(file_bytes)
        tmp.write(encrypted_bytes)
        temp_path = Path(tmp.name)

    unique_filename = file_storage.save_document_file(
        temp_path,
        category="expenses",
        original_name=uploaded_file.name,
    )

    try:
        temp_path.unlink()
    except Exception:
        pass

    if unique_filename:
        return f"expenses/{unique_filename}"
    return None


def _ensure_cashup_receipt_column(db_path: str):
    with get_db_connection(db_path) as conn:
        existing_columns = [row[1] for row in conn.execute("PRAGMA table_info(cashups)").fetchall()]
        if "receipt_path" not in existing_columns:
            conn.execute("ALTER TABLE cashups ADD COLUMN receipt_path TEXT")
            conn.commit()


def _submit_cashup_record(db_path: str, tenant_id: int, agent_id: int, cashup_data: dict) -> int:
    _ensure_cashup_receipt_column(db_path)
    columns = [
        "tenant_id", "agent_id", "cash_on_hand_open", "withdraw", "rente", "single",
        "double", "returns", "zero", "new", "top_up", "petrol", "transport",
        "melon_mobile", "deposit_general", "deposit_fnb", "deposit_capitec",
        "active_accounts", "outstanding", "single_outstanding", "cash_on_hand_end",
        "new_loans_text",
    ]
    values = [
        tenant_id,
        agent_id,
        cashup_data.get("cash_on_hand_open", 0.0),
        cashup_data.get("withdraw", 0.0),
        cashup_data.get("rente", 0.0),
        cashup_data.get("single", 0.0),
        cashup_data.get("double", 0.0),
        cashup_data.get("returns", 0.0),
        cashup_data.get("zero", 0.0),
        cashup_data.get("new", 0.0),
        cashup_data.get("top_up", 0.0),
        cashup_data.get("petrol", 0.0),
        cashup_data.get("transport", 0.0),
        cashup_data.get("melon_mobile", 0.0),
        cashup_data.get("deposit_general", 0.0),
        cashup_data.get("deposit_fnb", 0.0),
        cashup_data.get("deposit_capitec", 0.0),
        int(cashup_data.get("active_accounts", 0)),
        int(cashup_data.get("outstanding", 0)),
        int(cashup_data.get("single_outstanding", 0)),
        cashup_data.get("cash_on_hand_end", 0.0),
        cashup_data.get("new_loans_text", ""),
    ]

    if cashup_data.get("receipt_path"):
        columns.append("receipt_path")
        values.append(cashup_data["receipt_path"])

    placeholders = ", ".join("?" for _ in values)
    column_list = ", ".join(columns)
    query = f"INSERT INTO cashups ({column_list}) VALUES ({placeholders})"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, tuple(values))
        conn.commit()
        return cursor.lastrowid


def _get_defaulted_clients(db_path: str, tenant_id: int, agent_id: int):
    with get_db_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT c.client_id, c.first_name, c.last_name, l.loan_id, l.due_date"
            " FROM clients c"
            " JOIN loans l ON l.client_id = c.client_id"
            " WHERE c.tenant_id = ?"
            " AND c.assigned_agent_id = ?"
            " AND l.tenant_id = ?"
            " AND l.agent_id = ?"
            " AND l.status = 'Default'"
            " AND DATE(l.created_at) >= DATE('now', '-60 days')"
            " ORDER BY l.created_at DESC",
            (tenant_id, agent_id, tenant_id, agent_id),
        ).fetchall()
        return [dict(row) for row in rows]


def render_mobile_dashboard(agent_id: int, tenant_id: int):
    db_path = _get_db_path()
    if agent_id is None or tenant_id is None:
        st.error("Agent dashboard requires both agent_id and tenant_id.")
        return

    defaulted_clients = _get_defaulted_clients(db_path, tenant_id, agent_id)
    if defaulted_clients:
        with st.container():
            st.markdown(
                "<div style='border: 3px solid #900; background: #ffe6e6; padding: 18px; color: #900;'>"
                "<strong style='font-size:1.2rem;'>Defaulted Clients (First 60 Days)</strong>"
                "</div>",
                unsafe_allow_html=True,
            )
            st.table(
                [
                    {
                        "Client ID": row["client_id"],
                        "Name": f"{row['first_name']} {row['last_name']}",
                        "Loan ID": row["loan_id"],
                        "Due Date": row["due_date"],
                    }
                    for row in defaulted_clients
                ]
            )
    else:
        st.info("No defaulted clients in the last 60 days for your assigned portfolio.")

    cashup_history = get_cashup_summary(db_path, tenant_id, agent_id)
    latest_summary = cashup_history[0] if cashup_history else {}

    st.subheader("Daily Cash-Up")
    with st.form("daily_cashup_form"):
        st.markdown("### Inflow")
        inflow_col1, inflow_col2 = st.columns(2)
        with inflow_col1:
            cash_on_hand_open = st.number_input("Brought Forward", min_value=0.0, value=latest_summary.get("cash_on_hand_open", 0.0), format="%.2f")
            withdraw = st.number_input("Withdraw", min_value=0.0, value=latest_summary.get("withdraw", 0.0), format="%.2f")
            rente = st.number_input("Rente (%)", min_value=0.0, value=latest_summary.get("rente", 0.0), format="%.2f")
            single = st.number_input("Single", min_value=0.0, value=latest_summary.get("single", 0.0), format="%.2f")
            double = st.number_input("Double", min_value=0.0, value=latest_summary.get("double", 0.0), format="%.2f")
        with inflow_col2:
            returns_value = st.number_input("Returns", min_value=0.0, value=latest_summary.get("returns", 0.0), format="%.2f")
            zero = st.number_input("Zero", min_value=0.0, value=latest_summary.get("zero", 0.0), format="%.2f")
            new_value = st.number_input("New", min_value=0.0, value=latest_summary.get("new", 0.0), format="%.2f")
            top_up = st.number_input("Top up", min_value=0.0, value=latest_summary.get("top_up", 0.0), format="%.2f")

        st.markdown("### Bank/Digital")
        bank_col1, bank_col2, bank_col3 = st.columns(3)
        with bank_col1:
            deposit_general = st.number_input("Cash deposit", min_value=0.0, value=latest_summary.get("deposit_general", 0.0), format="%.2f")
        with bank_col2:
            deposit_fnb = st.number_input("FNB Customer", min_value=0.0, value=latest_summary.get("deposit_fnb", 0.0), format="%.2f")
        with bank_col3:
            deposit_capitec = st.number_input("Capitec transfers", min_value=0.0, value=latest_summary.get("deposit_capitec", 0.0), format="%.2f")

        st.markdown("### Metrics")
        metric_col1, metric_col2, metric_col3 = st.columns(3)
        with metric_col1:
            st.number_input(
                "Active",
                value=int(latest_summary.get("active_accounts", 0)),
                disabled=True,
                format="%d",
                step=1,
            )
        with metric_col2:
            st.number_input(
                "Outstanding",
                value=int(latest_summary.get("outstanding", 0)),
                disabled=True,
                format="%d",
                step=1,
            )
        with metric_col3:
            st.number_input(
                "Single Outstanding",
                value=int(latest_summary.get("single_outstanding", 0)),
                disabled=True,
                format="%d",
                step=1,
            )

        with st.expander("Log Expenses"):
            petrol = st.number_input("Petrol", min_value=0.0, value=latest_summary.get("petrol", 0.0), format="%.2f")
            transport = st.number_input("Transport", min_value=0.0, value=latest_summary.get("transport", 0.0), format="%.2f")
            melon_mobile = st.number_input("Melon mobile", min_value=0.0, value=latest_summary.get("melon_mobile", 0.0), format="%.2f")
            uploaded_receipt = st.file_uploader(
                "Upload Expense Receipt / Cash Photo",
                type=["jpg", "png", "pdf"],
                key="expense_proof",
            )

        submitted = st.form_submit_button("Submit Cash-Up")

        if submitted:
            receipt_path = None
            if uploaded_receipt:
                try:
                    receipt_path = _save_receipt_file(uploaded_receipt)
                except RuntimeError as exc:
                    st.error(str(exc))
                    return

            cashup_data = {
                "cash_on_hand_open": cash_on_hand_open,
                "withdraw": withdraw,
                "rente": rente,
                "single": single,
                "double": double,
                "returns": returns_value,
                "zero": zero,
                "new": new_value,
                "top_up": top_up,
                "deposit_general": deposit_general,
                "deposit_fnb": deposit_fnb,
                "deposit_capitec": deposit_capitec,
                "petrol": petrol,
                "transport": transport,
                "melon_mobile": melon_mobile,
                "active_accounts": latest_summary.get("active_accounts", 0),
                "outstanding": latest_summary.get("outstanding", 0),
                "single_outstanding": latest_summary.get("single_outstanding", 0),
                "cash_on_hand_end": 0.0,
                "new_loans_text": "",
            }
            if receipt_path:
                cashup_data["receipt_path"] = receipt_path

            cashup_id = _submit_cashup_record(db_path, tenant_id, agent_id, cashup_data)
            st.success(f"Daily cash-up saved successfully (ID: {cashup_id}).")

    if cashup_history:
        st.markdown("### Recent Cash-Up Records")
        st.table([
            {
                "Date": row["created_at"],
                "Active": row["active_accounts"],
                "Outstanding": row["outstanding"],
                "Single Outstanding": row["single_outstanding"],
                "Receipt": row.get("receipt_path", "-"),
            }
            for row in cashup_history[:5]
        ])
