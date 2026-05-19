"""
Database helper functions for FUS30.
Provides tenant-aware database schema, secure file storage, and reporting helpers.
"""
import base64
import hashlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pandas as pd


@contextmanager
def get_db_connection(db_path):
    """Context manager for database connections."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def initialize_schema(db_path):
    """Create or migrate the tenant-aware schema for FUS30."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tenants (
                tenant_id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_name TEXT NOT NULL,
                ncr_registration_number TEXT NOT NULL UNIQUE,
                address TEXT,
                email TEXT,
                phone TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS business_config (
                config_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER,
                business_name TEXT NOT NULL,
                registration_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                cloud_sync_id TEXT,
                FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                password_hash TEXT,
                role TEXT,
                full_name TEXT,
                email TEXT,
                phone TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                UNIQUE(tenant_id, username),
                FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                agent_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                user_id INTEGER,
                name TEXT NOT NULL,
                id_number TEXT,
                employee_code TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                client_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                first_name TEXT,
                last_name TEXT,
                id_number TEXT,
                phone TEXT,
                email TEXT,
                address TEXT,
                total_gross REAL DEFAULT 0.0,
                salary REAL DEFAULT 0.0,
                employer TEXT,
                work_days TEXT,
                pay_day TEXT,
                bank_name TEXT,
                account_no TEXT,
                status TEXT DEFAULT 'Active',
                assigned_agent_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id),
                FOREIGN KEY(assigned_agent_id) REFERENCES agents(agent_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reassignment_history (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                client_id INTEGER NOT NULL,
                old_agent_id INTEGER,
                new_agent_id INTEGER,
                reason TEXT,
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id),
                FOREIGN KEY(client_id) REFERENCES clients(client_id),
                FOREIGN KEY(old_agent_id) REFERENCES agents(agent_id),
                FOREIGN KEY(new_agent_id) REFERENCES agents(agent_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS loans (
                loan_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                client_id INTEGER,
                agent_id INTEGER,
                due_date TEXT,
                principal REAL,
                balance REAL,
                amount_paid REAL DEFAULT 0.0,
                status TEXT DEFAULT 'Active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id),
                FOREIGN KEY(client_id) REFERENCES clients(client_id),
                FOREIGN KEY(agent_id) REFERENCES agents(agent_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payment_history (
                payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                loan_id INTEGER,
                agent_id INTEGER,
                amount REAL,
                date TEXT,
                type TEXT,
                receipt_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id),
                FOREIGN KEY(loan_id) REFERENCES loans(loan_id),
                FOREIGN KEY(agent_id) REFERENCES agents(agent_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                expense_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                description TEXT,
                amount REAL,
                date TEXT,
                category TEXT DEFAULT 'General',
                FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                invoice_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                client_id INTEGER,
                agent_id INTEGER,
                invoice_number TEXT UNIQUE,
                amount REAL,
                due_date TEXT,
                status TEXT DEFAULT 'Draft',
                data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id),
                FOREIGN KEY(client_id) REFERENCES clients(client_id),
                FOREIGN KEY(agent_id) REFERENCES agents(agent_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invoice_audit (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                invoice_id INTEGER,
                agent_id INTEGER,
                action TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id),
                FOREIGN KEY(invoice_id) REFERENCES invoices(invoice_id),
                FOREIGN KEY(agent_id) REFERENCES agents(agent_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cashups (
                cashup_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                agent_id INTEGER,
                cash_on_hand_open REAL DEFAULT 0.0,
                withdraw REAL DEFAULT 0.0,
                rente REAL DEFAULT 0.0,
                single REAL DEFAULT 0.0,
                double REAL DEFAULT 0.0,
                returns REAL DEFAULT 0.0,
                zero REAL DEFAULT 0.0,
                new REAL DEFAULT 0.0,
                top_up REAL DEFAULT 0.0,
                petrol REAL DEFAULT 0.0,
                transport REAL DEFAULT 0.0,
                melon_mobile REAL DEFAULT 0.0,
                deposit_general REAL DEFAULT 0.0,
                deposit_fnb REAL DEFAULT 0.0,
                deposit_capitec REAL DEFAULT 0.0,
                active_accounts INTEGER DEFAULT 0,
                outstanding INTEGER DEFAULT 0,
                single_outstanding INTEGER DEFAULT 0,
                cash_on_hand_end REAL DEFAULT 0.0,
                new_loans_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id),
                FOREIGN KEY(agent_id) REFERENCES agents(agent_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS compliance_documents (
                document_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                document_type TEXT,
                original_filename TEXT,
                stored_filename TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id)
            )
        """)

        cursor.execute("""
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
            """)

        cursor.execute("""
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id),
                FOREIGN KEY(assigned_agent_id) REFERENCES agents(agent_id),
                FOREIGN KEY(allocated_loan_id) REFERENCES loans(loan_id)
            )
            """)


def register_tenant(db_path, business_name, ncr_registration_number, address=None, email=None, phone=None):
    """Register a new tenant/business."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO tenants (business_name, ncr_registration_number, address, email, phone)
            VALUES (?, ?, ?, ?, ?)
            """,
            (business_name, ncr_registration_number, address, email, phone)
        )
        conn.commit()
        return cursor.lastrowid


def get_tenant_by_id(db_path, tenant_id):
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tenants WHERE tenant_id = ?", (tenant_id,))
        tenant = cursor.fetchone()
    return dict(tenant) if tenant else None


def find_tenant(db_path, identifier):
    """Find a tenant by business name or NCR registration number."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM tenants
            WHERE business_name = ? OR ncr_registration_number = ?
            LIMIT 1
        """, (identifier, identifier))
        tenant = cursor.fetchone()
    return dict(tenant) if tenant else None


def list_tenants(db_path):
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT tenant_id, business_name, ncr_registration_number, is_active FROM tenants ORDER BY business_name")
        return [dict(row) for row in cursor.fetchall()]


def create_user(db_path, tenant_id, username, password, role, full_name=None, email=None, phone=None):
    """Create a user within a tenant."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (tenant_id, username, password_hash, role, full_name, email, phone, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, (tenant_id, username, _hash_password(password), role, full_name, email, phone))
        conn.commit()
        return cursor.lastrowid


def get_user(db_path, tenant_id, username):
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM users
            WHERE tenant_id = ? AND username = ?
            LIMIT 1
        """, (tenant_id, username))
        user = cursor.fetchone()
    return dict(user) if user else None


def authenticate_user(db_path, tenant_id, username, password):
    """Authenticate a tenant user."""
    user = get_user(db_path, tenant_id, username)
    if not user:
        return None
    if _hash_password(password) != user['password_hash'] or user['is_active'] != 1:
        return None
    return user


def create_agent(db_path, tenant_id, name, id_number=None, employee_code=None, user_id=None):
    """Create an agent profile for a tenant."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO agents (tenant_id, user_id, name, id_number, employee_code)
            VALUES (?, ?, ?, ?, ?)
        """, (tenant_id, user_id, name, id_number, employee_code))
        conn.commit()
        return cursor.lastrowid


def get_agent_by_id(db_path, tenant_id, agent_id):
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM agents
            WHERE tenant_id = ? AND agent_id = ?
        """, (tenant_id, agent_id))
        agent = cursor.fetchone()
    return dict(agent) if agent else None


def get_agent_by_user_id(db_path, tenant_id, user_id):
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM agents
            WHERE tenant_id = ? AND user_id = ?
            LIMIT 1
        """, (tenant_id, user_id))
        agent = cursor.fetchone()
    return dict(agent) if agent else None


def get_active_agents(db_path, tenant_id):
    """Fetch active agents for a specific tenant."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.agent_id, a.name, a.id_number, a.employee_code, u.username, u.full_name
            FROM agents a
            LEFT JOIN users u ON a.user_id = u.user_id
            WHERE a.tenant_id = ?
            ORDER BY a.name ASC
        """, (tenant_id,))
        return [dict(row) for row in cursor.fetchall()]


def create_client(db_path, tenant_id, first_name, last_name, id_number, phone, email=None,
                  assigned_agent_id=None, address=None, salary=None, employer=None,
                  work_days=None, pay_day=None, bank_name=None, account_no=None):
    """Create a new client under the tenant."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO clients (
                tenant_id, first_name, last_name, id_number, phone, email, address,
                total_gross, salary, employer, work_days, pay_day, bank_name, account_no,
                status, assigned_agent_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?, ?, ?, ?, ?, 'Active', ?)
        """, (
            tenant_id, first_name, last_name, id_number, phone, email, address,
            salary, employer, work_days, pay_day, bank_name, account_no, assigned_agent_id
        ))
        conn.commit()
        return cursor.lastrowid


def get_clients_by_agent(db_path, tenant_id, agent_id):
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM clients
            WHERE tenant_id = ? AND assigned_agent_id = ?
            ORDER BY last_name, first_name ASC
        """, (tenant_id, agent_id))
        return [dict(row) for row in cursor.fetchall()]


def update_client_assignment(db_path, tenant_id, client_id, new_agent_id, reason=None):
    """Reassign a client and log the change."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT assigned_agent_id FROM clients WHERE tenant_id = ? AND client_id = ?", (tenant_id, client_id))
        row = cursor.fetchone()
        old_agent_id = row['assigned_agent_id'] if row else None
        cursor.execute("""
            UPDATE clients
            SET assigned_agent_id = ?
            WHERE tenant_id = ? AND client_id = ?
        """, (new_agent_id, tenant_id, client_id))
        cursor.execute("""
            INSERT INTO reassignment_history (tenant_id, client_id, old_agent_id, new_agent_id, reason)
            VALUES (?, ?, ?, ?, ?)
        """, (tenant_id, client_id, old_agent_id, new_agent_id, reason))
        conn.commit()
        return True


def get_agent_portfolio(db_path, tenant_id, agent_id, search_term=None):
    with get_db_connection(db_path) as conn:
        query = """
            SELECT c.client_id,
                   c.first_name || ' ' || c.last_name AS client_name,
                   c.phone,
                   c.id_number,
                   l.loan_id,
                   l.balance,
                   l.due_date,
                   l.status
            FROM clients c
            JOIN loans l ON c.client_id = l.client_id
            WHERE c.tenant_id = ? AND l.tenant_id = ? AND c.assigned_agent_id = ?
        """
        params = [tenant_id, tenant_id, agent_id]
        if search_term:
            query += " AND (c.first_name || ' ' || c.last_name LIKE ? OR c.id_number LIKE ? OR c.phone LIKE ?)"
            pattern = f"%{search_term}%"
            params.extend([pattern, pattern, pattern])
        query += " ORDER BY c.last_name, c.first_name"
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def get_loan_details(db_path, tenant_id, loan_id):
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM loans
            WHERE tenant_id = ? AND loan_id = ?
        """, (tenant_id, loan_id))
        row = cursor.fetchone()
    return dict(row) if row else None


def record_payment(db_path, tenant_id, loan_id, agent_id, amount, pay_date, payment_type, receipt_path=None):
    """Record a payment and update the loan balance."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT client_id, balance
            FROM loans
            WHERE tenant_id = ? AND loan_id = ?
        """, (tenant_id, loan_id))
        loan = cursor.fetchone()
        if not loan:
            raise ValueError('Loan not found for tenant')

        new_balance = float(loan['balance'] or 0.0) - float(amount)
        status = 'Settled' if new_balance <= 0 else 'Active'

        cursor.execute("""
            INSERT INTO payment_history (tenant_id, loan_id, agent_id, amount, date, type, receipt_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (tenant_id, loan_id, agent_id, amount, pay_date, payment_type, receipt_path))

        cursor.execute("""
            UPDATE loans
            SET balance = ?, amount_paid = amount_paid + ?, status = ?
            WHERE tenant_id = ? AND loan_id = ?
        """, (new_balance, amount, status, tenant_id, loan_id))

        conn.commit()
        return cursor.lastrowid


def create_receipt_text(tenant_id, agent_id, client_id, amount, timestamp=None):
    if timestamp is None:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    receipt = (
        f"RECEIPT\n"
        f"Tenant ID: {tenant_id}\n"
        f"Agent ID: {agent_id}\n"
        f"Client ID: {client_id}\n"
        f"Amount: R{float(amount):,.2f}\n"
        f"Timestamp: {timestamp}\n"
        f"Reference: {hashlib.sha256(f'{tenant_id}-{agent_id}-{client_id}-{timestamp}'.encode()).hexdigest()[:12]}\n"
    )
    return receipt


def save_receipt_file(db_path, tenant_id, receipt_text, client_id, agent_id):
    receipts_dir = Path(db_path).parent / 'receipts'
    receipts_dir.mkdir(parents=True, exist_ok=True)
    filename = f"receipt_t{tenant_id}_a{agent_id}_c{client_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.txt"
    path = receipts_dir / filename
    path.write_text(receipt_text, encoding='utf-8')
    return str(path)


def get_document_store_path(db_path):
    folder = Path(db_path).parent / 'compliance_documents'
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def save_compliance_document(db_path, tenant_id, document_type, uploaded_bytes, original_filename, encryption_key=None):
    document_folder = get_document_store_path(db_path)
    stamp = datetime.now().strftime('%Y%m%d%H%M%S')
    safe_name = hashlib.sha256(f"{tenant_id}-{original_filename}-{stamp}".encode('utf-8')).hexdigest()
    suffix = original_filename.split('.')[-1] if '.' in original_filename else 'bin'
    stored_filename = f"{safe_name}.{suffix}"
    stored_path = document_folder / stored_filename
    content = uploaded_bytes

    if encryption_key:
        try:
            from cryptography.fernet import Fernet
            key = hashlib.sha256(encryption_key.encode('utf-8')).digest()
            key_b64 = base64.urlsafe_b64encode(key)
            content = Fernet(key_b64).encrypt(uploaded_bytes)
            stored_filename = f"{safe_name}.enc"
            stored_path = document_folder / stored_filename
        except ImportError:
            pass

    stored_path.write_bytes(content)

    metadata = json.dumps({
        'original_filename': original_filename,
        'document_type': document_type,
        'stored_path': str(stored_path),
        'uploaded_at': datetime.now().isoformat()
    })

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO compliance_documents (tenant_id, document_type, original_filename, stored_filename, metadata)
            VALUES (?, ?, ?, ?, ?)
        """, (tenant_id, document_type, original_filename, stored_filename, metadata))
        conn.commit()
        return cursor.lastrowid


def list_compliance_documents(db_path, tenant_id):
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT document_id, document_type, original_filename, stored_filename, metadata, created_at
            FROM compliance_documents
            WHERE tenant_id = ?
            ORDER BY created_at DESC
        """, (tenant_id,))
        return [dict(row) for row in cursor.fetchall()]


def export_dataframe_to_csv_bytes(df):
    return df.to_csv(index=False).encode('utf-8')


def generate_form_39_dataframe(db_path, tenant_id, year=None, quarter=None):
    with get_db_connection(db_path) as conn:
        params = [tenant_id]
        query = """
            SELECT principal, balance, status, created_at
            FROM loans
            WHERE tenant_id = ?
        """
        if year:
            query += " AND strftime('%Y', created_at) = ?"
            params.append(str(year))
        if quarter:
            first_month = (quarter - 1) * 3 + 1
            last_month = first_month + 2
            query += " AND CAST(strftime('%m', created_at) AS INTEGER) BETWEEN ? AND ?"
            params.extend([first_month, last_month])

        loans = [dict(row) for row in conn.execute(query, params).fetchall()]

    total_credit_granted = sum([row.get('principal', 0.0) or 0.0 for row in loans])
    total_book_value = sum([row.get('balance', 0.0) or 0.0 for row in loans])
    approvals = len([row for row in loans if str(row.get('status', '')).lower() != 'rejected'])
    rejections = len([row for row in loans if str(row.get('status', '')).lower() == 'rejected'])
    total_applications = approvals + rejections
    approval_ratio = f"{(approvals / total_applications * 100):.1f}%" if total_applications else "0%"
    rejection_ratio = f"{(rejections / total_applications * 100):.1f}%" if total_applications else "0%"

    data = {
        'Period': [f'Q{quarter} {year}' if quarter and year else str(year or 'All Periods')],
        'Total Credit Granted': [total_credit_granted],
        'Total Book Value': [total_book_value],
        'Applications Approved': [approvals],
        'Applications Rejected': [rejections],
        'Approval Ratio': [approval_ratio],
        'Rejection Ratio': [rejection_ratio]
    }
    return pd.DataFrame(data)


def generate_form_40_dataframe(db_path, tenant_id, year=None):
    with get_db_connection(db_path) as conn:
        params = [tenant_id]
        query = """
            SELECT principal, balance, status, created_at
            FROM loans
            WHERE tenant_id = ?
        """
        if year:
            query += " AND strftime('%Y', created_at) = ?"
            params.append(str(year))

        loans = [dict(row) for row in conn.execute(query, params).fetchall()]

    total_credit_granted = sum([row.get('principal', 0.0) or 0.0 for row in loans])
    total_book_value = sum([row.get('balance', 0.0) or 0.0 for row in loans])
    settled = len([row for row in loans if str(row.get('status', '')).lower() == 'settled'])
    active = len([row for row in loans if str(row.get('status', '')).lower() == 'active'])
    rejected = len([row for row in loans if str(row.get('status', '')).lower() == 'rejected'])
    total_applications = settled + active + rejected
    approval_ratio = f"{((settled + active) / total_applications * 100):.1f}%" if total_applications else "0%"
    rejection_ratio = f"{(rejected / total_applications * 100):.1f}%" if total_applications else "0%"

    data = {
        'Period': [str(year or 'All Years')],
        'Total Credit Granted': [total_credit_granted],
        'Total Book Value': [total_book_value],
        'Approved / Active Applications': [settled + active],
        'Rejected Applications': [rejected],
        'Approval Ratio': [approval_ratio],
        'Rejection Ratio': [rejection_ratio]
    }
    return pd.DataFrame(data)


def _parse_money_strings(value):
    if not value:
        return 0.0
    cleaned = re.sub(r'[^0-9.]', '', str(value))
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def submit_cashup(db_path, tenant_id, agent_id, cashup_data):
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO cashups (
                tenant_id, agent_id, cash_on_hand_open, withdraw, rente, single,
                double, returns, zero, new, top_up, petrol, transport, melon_mobile,
                deposit_general, deposit_fnb, deposit_capitec,
                active_accounts, outstanding, single_outstanding, cash_on_hand_end, new_loans_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tenant_id, agent_id,
            cashup_data.get('cash_on_hand_open', 0.0),
            cashup_data.get('withdraw', 0.0),
            cashup_data.get('rente', 0.0),
            cashup_data.get('single', 0.0),
            cashup_data.get('double', 0.0),
            cashup_data.get('returns', 0.0),
            cashup_data.get('zero', 0.0),
            cashup_data.get('new', 0.0),
            cashup_data.get('top_up', 0.0),
            cashup_data.get('petrol', 0.0),
            cashup_data.get('transport', 0.0),
            cashup_data.get('melon_mobile', 0.0),
            cashup_data.get('deposit_general', 0.0),
            cashup_data.get('deposit_fnb', 0.0),
            cashup_data.get('deposit_capitec', 0.0),
            int(cashup_data.get('active_accounts', 0)),
            int(cashup_data.get('outstanding', 0)),
            int(cashup_data.get('single_outstanding', 0)),
            cashup_data.get('cash_on_hand_end', 0.0),
            cashup_data.get('new_loans_text', '')
        ))
        conn.commit()
        return cursor.lastrowid


def get_cashup_summary(db_path, tenant_id, agent_id=None):
    with get_db_connection(db_path) as conn:
        query = "SELECT * FROM cashups WHERE tenant_id = ?"
        params = [tenant_id]
        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id)
        query += " ORDER BY created_at DESC LIMIT 10"
        rows = [dict(row) for row in conn.execute(query, params).fetchall()]

    for row in rows:
        row['new_loans_list'] = [line.strip() for line in str(row.get('new_loans_text', '')).splitlines() if line.strip()]
        row['new_loans_total'] = sum(_parse_money_strings(line) for line in row['new_loans_list'])
        row['subtotal'] = (
            row['cash_on_hand_open'] + row['deposit_general'] + row['deposit_fnb'] + row['deposit_capitec'] + row['returns'] + row['new'] + row['top_up']
            - row['withdraw'] - row['petrol'] - row['transport'] - row['melon_mobile']
        )
        row['calculated_expenses'] = row['subtotal'] - row['cash_on_hand_end']
    return rows


def _read_json_file(path):
    if not path.exists():
        return []
    try:
        with path.open('r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []


def _write_json_file(path, data):
    with path.open('w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def get_offline_queue_path(db_path, tenant_id):
    folder = Path(db_path).parent / 'offline_queue'
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f'offline_payments_tenant_{tenant_id}.json'


def queue_offline_payment(db_path, tenant_id, payment_record):
    queue_path = get_offline_queue_path(db_path, tenant_id)
    queued = _read_json_file(queue_path)
    queued.append(payment_record)
    _write_json_file(queue_path, queued)
    return queue_path


def get_pending_offline_payments(db_path, tenant_id):
    queue_path = get_offline_queue_path(db_path, tenant_id)
    return _read_json_file(queue_path)


def clear_offline_payments(db_path, tenant_id):
    queue_path = get_offline_queue_path(db_path, tenant_id)
    if queue_path.exists():
        queue_path.unlink()


def sync_offline_payments(db_path, tenant_id):
    pending = get_pending_offline_payments(db_path, tenant_id)
    if not pending:
        return 0
    applied = 0
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        for payment in pending:
            cursor.execute("SELECT loan_id FROM loans WHERE tenant_id = ? AND loan_id = ?", (tenant_id, payment['loan_id']))
            if cursor.fetchone():
                cursor.execute("""
                    INSERT INTO payment_history (tenant_id, loan_id, agent_id, amount, date, type, receipt_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    tenant_id,
                    payment['loan_id'],
                    payment.get('agent_id'),
                    payment['amount'],
                    payment['date'],
                    payment['type'],
                    payment.get('receipt_path')
                ))
                cursor.execute("""
                    UPDATE loans SET balance = balance - ?, amount_paid = amount_paid + ?
                    WHERE tenant_id = ? AND loan_id = ?
                """, (payment['amount'], payment['amount'], tenant_id, payment['loan_id']))
                applied += 1
        conn.commit()
    clear_offline_payments(db_path, tenant_id)
    return applied


class CostOfCreditCalculator:
    MAX_INITIATION = 165.0
    INITIATION_CAP = 1050.0
    MAX_SERVICE_FEE = 60.0
    MAX_SPREAD = 0.21

    def __init__(self, repo_rate=0.085):
        self.repo_rate = float(repo_rate)

    def max_initiation_fee(self, principal):
        excess = max(0.0, float(principal) - 1000.0)
        fee = self.MAX_INITIATION + (excess * 0.10)
        return min(fee, self.INITIATION_CAP)

    def capped_service_fee(self, service_fee):
        return min(float(service_fee or 0.0), self.MAX_SERVICE_FEE)

    def max_interest_rate(self):
        return self.repo_rate + self.MAX_SPREAD

    def validate_loan_terms(self, principal, initiation_fee, service_fee, interest_rate):
        return {
            'max_initiation_fee': self.max_initiation_fee(principal),
            'allowed_service_fee': self.capped_service_fee(service_fee),
            'allowed_interest_rate': self.max_interest_rate(),
            'is_initiation_valid': float(initiation_fee) <= self.max_initiation_fee(principal),
            'is_service_valid': float(service_fee) <= self.MAX_SERVICE_FEE,
            'is_interest_valid': float(interest_rate) <= self.max_interest_rate()
        }
