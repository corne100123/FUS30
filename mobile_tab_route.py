import datetime
import re
from typing import Dict, List, Optional

import folium
import requests
import streamlit as st
from streamlit_folium import st_folium

from DFUS_30_Suite.config import get_default_db_path
from DFUS_30_Suite.db_helpers import get_db_connection


def _get_db_path() -> str:
    if st.session_state.get("config") and st.session_state.config.get("db_path"):
        return st.session_state.config.get("db_path")
    return get_default_db_path()


def _ensure_follow_ups_table(db_path: str):
    with get_db_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS follow_ups (
                follow_up_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                agent_id INTEGER NOT NULL,
                client_id INTEGER NOT NULL,
                reminder_date TEXT NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def _sanitize_phone(phone: str) -> str:
    sanitized = re.sub(r"\D", "", str(phone or ""))
    if sanitized.startswith("0"):
        sanitized = "27" + sanitized[1:]
    elif not sanitized.startswith("27") and sanitized:
        sanitized = "27" + sanitized
    return sanitized


def _build_whatsapp_link(phone: str) -> str:
    phone_number = _sanitize_phone(phone)
    if not phone_number:
        return "#"
    return f"https://wa.me/{phone_number}"


def _extract_lat_lon(address: str) -> Optional[Dict[str, float]]:
    if not address:
        return None
    match = re.search(r"(-?\d+\.\d+)[,\s]+(-?\d+\.\d+)", address)
    if match:
        return {"lat": float(match.group(1)), "lon": float(match.group(2))}
    return None


_geo_cache: Dict[str, Optional[Dict[str, float]]] = {}


def _geocode_address(address: str) -> Optional[Dict[str, float]]:
    if not address:
        return None
    address = address.strip()
    if address in _geo_cache:
        return _geo_cache[address]

    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1},
            headers={"User-Agent": "FUS30-Agent-Mobile/1.0"},
            timeout=8,
        )
        response.raise_for_status()
        data = response.json()
        if data:
            lat = float(data[0]["lat"])
            lon = float(data[0]["lon"])
            coords = {"lat": lat, "lon": lon}
            _geo_cache[address] = coords
            return coords
    except Exception:
        pass
    _geo_cache[address] = None
    return None


def _get_due_today_clients(db_path: str, tenant_id: int, agent_id: int) -> List[dict]:
    today = datetime.date.today().isoformat()
    with get_db_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT c.client_id, c.first_name, c.last_name, c.address, c.phone, l.loan_id, l.balance, l.principal, l.due_date, l.status"
            " FROM clients c"
            " JOIN loans l ON l.client_id = c.client_id"
            " WHERE c.tenant_id = ?"
            " AND c.assigned_agent_id = ?"
            " AND l.tenant_id = ?"
            " AND l.agent_id = ?"
            " AND DATE(l.due_date) = DATE(?)"
            " AND l.status IN ('Active', 'Arrears')"
            " ORDER BY l.due_date ASC",
            (tenant_id, agent_id, tenant_id, agent_id, today),
        ).fetchall()
        return [dict(row) for row in rows]


def _create_follow_up(db_path: str, tenant_id: int, agent_id: int, client_id: int, reminder_date: datetime.date, notes: str = "") -> int:
    _ensure_follow_ups_table(db_path)
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO follow_ups (tenant_id, agent_id, client_id, reminder_date, notes) VALUES (?, ?, ?, ?, ?)",
            (tenant_id, agent_id, client_id, reminder_date.isoformat(), notes),
        )
        conn.commit()
        return cursor.lastrowid


def render_mobile_route(agent_id: int):
    if not agent_id:
        st.error("Agent route requires a valid agent_id.")
        return
    if "tenant_id" not in st.session_state or not st.session_state.get("tenant_id"):
        st.error("Tenant context is required for route rendering.")
        return

    tenant_id = st.session_state.tenant_id
    db_path = _get_db_path()
    due_today_clients = _get_due_today_clients(db_path, tenant_id, agent_id)

    st.title("Route & Customers")

    points = []
    for client in due_today_clients:
        coords = _extract_lat_lon(client.get("address", ""))
        if not coords:
            coords = _geocode_address(client.get("address", ""))
        if coords:
            points.append({"coords": coords, "client": client})

    if points:
        start = points[0]["coords"]
        route_map = folium.Map(location=[start["lat"], start["lon"]], zoom_start=12)
        for point in points:
            client = point["client"]
            folium.Marker(
                [point["coords"]["lat"], point["coords"]["lon"]],
                popup=f"<b>{client['first_name']} {client['last_name']}</b><br>Due: R{client['balance']:.2f}",
                tooltip=client['first_name'] + " " + client['last_name'],
            ).add_to(route_map)
        st_folium(route_map, width="100%", height=450)
    else:
        st.info("No geocoded route points available for today. Please ensure client addresses include lat/long or are valid for geocoding.")

    st.markdown("---")
    st.subheader("Expected Today")

    if not due_today_clients:
        st.info("No clients expected to pay today.")
        return

    for client in due_today_clients:
        client_id = client["client_id"]
        full_name = f"{client['first_name']} {client['last_name']}"
        address = client.get("address") or "Address not available"
        amount_due = client.get("balance", 0.0)
        phone = client.get("phone", "")
        whatsapp_url = _build_whatsapp_link(phone)

        with st.container():
            st.markdown(
                f"<div style='border: 1px solid #ddd; border-radius:14px; padding:18px; margin-bottom:16px; background:#fff;'>"
                f"<div style='font-size:1.15rem; font-weight:700;'>{full_name}</div>"
                f"<div style='color:#555; margin-bottom:12px;'>{address}</div>"
                f"<div style='font-size:2rem; font-weight:800; color:#b21f1f;'>R{amount_due:,.2f}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            cols = st.columns([1, 1, 1])
            with cols[0]:
                if st.button("Log Payment", key=f"log_payment_{client_id}"):
                    st.session_state[f"open_payment_dialog_{client_id}"] = True

                if st.session_state.get(f"open_payment_dialog_{client_id}"):
                    with st.dialog(f"Log Payment for {full_name}"):
                        pay_amount = st.number_input("Amount Paid", min_value=0.0, value=0.0, format="%.2f")
                        pay_type = st.selectbox("Payment Method", ["Cash", "Card", "Transfer"])
                        note = st.text_area("Payment notes (optional)")
                        if st.button("Confirm Payment", key=f"confirm_payment_{client_id}"):
                            with get_db_connection(db_path) as conn:
                                conn.execute(
                                    "INSERT INTO payment_history (tenant_id, loan_id, agent_id, amount, date, type) VALUES (?, ?, ?, ?, ?, ?)",
                                    (
                                        tenant_id,
                                        client["loan_id"],
                                        agent_id,
                                        float(pay_amount),
                                        datetime.date.today().isoformat(),
                                        pay_type,
                                    ),
                                )
                                conn.execute(
                                    "UPDATE loans SET balance = balance - ?, amount_paid = amount_paid + ? WHERE tenant_id = ? AND loan_id = ? AND agent_id = ?",
                                    (float(pay_amount), float(pay_amount), tenant_id, client["loan_id"], agent_id),
                                )
                                conn.commit()
                            st.success("Payment recorded.")
                            st.session_state[f"open_payment_dialog_{client_id}"] = False

            with cols[1]:
                st.markdown(
                    f"<a href='{whatsapp_url}' target='_blank' style='display:inline-block; padding:10px 12px; width:100%; text-align:center; border-radius:10px; background:#25D366; color:#fff; text-decoration:none;'>WhatsApp</a>",
                    unsafe_allow_html=True,
                )

            with cols[2]:
                followup_date = st.date_input(
                    "Follow-Up Date",
                    value=datetime.date.today() + datetime.timedelta(days=3),
                    key=f"followup_date_{client_id}",
                )
                if st.button("Set Follow-Up", key=f"set_followup_{client_id}"):
                    follow_up_id = _create_follow_up(
                        db_path=db_path,
                        tenant_id=tenant_id,
                        agent_id=agent_id,
                        client_id=client_id,
                        reminder_date=followup_date,
                        notes=f"Follow-up set from route page for loan {client['loan_id']}",
                    )
                    st.success(f"Follow-up scheduled (ID: {follow_up_id}).")
