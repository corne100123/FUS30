import datetime
import streamlit as st

from DFUS_30_Suite.config import get_default_db_path
from DFUS_30_Suite.db_helpers import get_db_connection
from mobile_tab_loans import render_mobile_loans
from mobile_tab_payments import render_mobile_payments


def hide_sidebar():
    st.markdown(
        """
        <style>
            [data-testid="stSidebar"] {display: none !important;}
            .css-1bd0b4e {display: none !important;}
            .css-1v3fvcr {display: none !important;}
            .main .block-container {padding-left: 1rem; padding-right: 1rem;}
            .reportview-container .main .block-container {max-width: 100% !important;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def get_db_path() -> str:
    if st.session_state.get("config") and st.session_state.config.get("db_path"):
        return st.session_state.config.get("db_path")
    return get_default_db_path()


def resolve_agent_identity(db_path: str) -> int:
    if st.session_state.get("agent_id"):
        return st.session_state.agent_id

    if not st.session_state.get("user_id"):
        st.error("The mobile app requires an authenticated agent user.")
        st.stop()

    with get_db_connection(db_path) as conn:
        row = conn.execute(
            "SELECT agent_id FROM agents WHERE tenant_id = ? AND user_id = ?",
            (st.session_state.tenant_id, st.session_state.user_id),
        ).fetchone()
        if row:
            st.session_state.agent_id = row["agent_id"]
            return row["agent_id"]

    st.error(
        "Agent profile not found. Please ensure the current user is mapped to an active agent record."
    )
    st.stop()


def get_assigned_clients(db_path: str, tenant_id: int, agent_id: int):
    with get_db_connection(db_path) as conn:
        return conn.execute(
            "SELECT client_id, first_name, last_name, phone, status"
            " FROM clients"
            " WHERE tenant_id = ? AND assigned_agent_id = ?",
            (tenant_id, agent_id),
        ).fetchall()


def get_assigned_loans(db_path: str, tenant_id: int, agent_id: int):
    with get_db_connection(db_path) as conn:
        return conn.execute(
            "SELECT l.loan_id, l.client_id, l.principal, l.balance, l.due_date, l.status, c.first_name, c.last_name"
            " FROM loans l"
            " JOIN clients c ON c.client_id = l.client_id"
            " WHERE l.tenant_id = ? AND l.agent_id = ?",
            (tenant_id, agent_id),
        ).fetchall()


def count_defaulted_clients(db_path: str, tenant_id: int, agent_id: int) -> int:
    with get_db_connection(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(DISTINCT c.client_id) AS total"
            " FROM clients c"
            " JOIN loans l ON l.client_id = c.client_id"
            " WHERE c.tenant_id = ?"
            " AND c.assigned_agent_id = ?"
            " AND l.agent_id = ?"
            " AND l.status = 'Default'"
            " AND DATE(l.created_at) >= DATE('now', '-60 days')",
            (tenant_id, agent_id, agent_id),
        ).fetchone()
        return int(row["total"] if row and row["total"] is not None else 0)


def get_alert_rows(db_path: str, tenant_id: int, agent_id: int):
    with get_db_connection(db_path) as conn:
        return conn.execute(
            "SELECT c.client_id, c.first_name, c.last_name, l.status, l.due_date"
            " FROM clients c"
            " JOIN loans l ON l.client_id = c.client_id"
            " WHERE c.tenant_id = ?"
            " AND c.assigned_agent_id = ?"
            " AND l.agent_id = ?"
            " AND (l.status = 'Default' OR l.status = 'Arrears')",
            (tenant_id, agent_id, agent_id),
        ).fetchall()


def create_new_client(db_path: str, tenant_id: int, agent_id: int, first_name: str, last_name: str, phone: str) -> int:
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO clients (tenant_id, assigned_agent_id, first_name, last_name, phone, status)"
            " VALUES (?, ?, ?, ?, ?, 'Active')",
            (tenant_id, agent_id, first_name, last_name, phone),
        )
        conn.commit()
        return cursor.lastrowid


def create_new_loan(db_path: str, tenant_id: int, agent_id: int, client_id: int, principal: float) -> int:
    due_date = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO loans (tenant_id, client_id, agent_id, due_date, principal, balance, status)"
            " VALUES (?, ?, ?, ?, ?, ?, 'Active')",
            (tenant_id, client_id, agent_id, due_date, principal, principal),
        )
        conn.commit()
        return cursor.lastrowid


def record_payment(db_path: str, tenant_id: int, agent_id: int, loan_id: int, amount: float, payment_type: str):
    payment_date = datetime.date.today().isoformat()
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO payment_history (tenant_id, loan_id, agent_id, amount, date, type)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (tenant_id, loan_id, agent_id, amount, payment_date, payment_type),
        )
        cursor.execute(
            "UPDATE loans SET balance = balance - ?, amount_paid = amount_paid + ? WHERE tenant_id = ? AND loan_id = ? AND agent_id = ?",
            (amount, amount, tenant_id, loan_id, agent_id),
        )
        conn.commit()


def main():
    st.set_page_config(page_title="FUS30 Agent Mobile", layout="wide")
    hide_sidebar()

    if "tenant_id" not in st.session_state or not st.session_state.get("tenant_id"):
        st.error("Agent mobile mode requires `st.session_state['tenant_id']` to be set.")
        st.stop()

    if "role" not in st.session_state or st.session_state.role != "Agent":
        st.error("Agent mobile mode requires an authenticated Agent role.")
        st.stop()

    db_path = get_db_path()
    agent_id = resolve_agent_identity(db_path)
    tenant_id = st.session_state.tenant_id

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Dash",
        "🗺️ Route",
        "📝 Loans",
        "💳 Pay",
        "⚠️ Alerts",
    ])

    with tab1:
        defaulted_count = count_defaulted_clients(db_path, tenant_id, agent_id)
        st.markdown(
            f"<div style='border: 3px solid red; padding: 18px; background:#ffe6e6; color:#900; font-size:1.35rem; font-weight:bold;'>"
            f"Defaulted Clients (First 60 Days): {defaulted_count}"
            "</div>",
            unsafe_allow_html=True,
        )
        st.write("Focus on your assigned clients only. All queries are scoped by your agent_id and tenant_id.")

        assigned_clients = get_assigned_clients(db_path, tenant_id, agent_id)
        if assigned_clients:
            st.subheader("Your Assigned Clients")
            st.table(
                [
                    {
                        "Client ID": row["client_id"],
                        "Name": f"{row['first_name']} {row['last_name']}",
                        "Phone": row["phone"],
                        "Status": row["status"],
                    }
                    for row in assigned_clients
                ]
            )
        else:
            st.info("No assigned clients found. Please connect with your supervisor to receive assignments.")

    with tab2:
        st.subheader("Route Plan")
        if assigned_clients:
            for row in assigned_clients:
                st.markdown(
                    f"**{row['first_name']} {row['last_name']}**  |  Phone: {row['phone']}  |  Status: {row['status']}"
                )
        else:
            st.info("No route items available.")

    with tab3:
        render_mobile_loans(agent_id)

    with tab4:
        render_mobile_payments(agent_id)

    with tab5:
        st.subheader("Priority Alerts")
        alerts = get_alert_rows(db_path, tenant_id, agent_id)
        if alerts:
            for alert in alerts:
                st.warning(
                    f"{alert['first_name']} {alert['last_name']} — Loan Status: {alert['status']} | Due: {alert['due_date']}"
                )
        else:
            st.success("No immediate alerts. Keep engaging your assigned clients.")


if __name__ == "__main__":
    main()
