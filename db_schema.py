from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    create_engine,
    event,
    func,
)
from sqlalchemy.orm import declarative_base
import os

Base = declarative_base()


class Tenant(Base):
    __tablename__ = "tenants"
    tenant_id = Column(String(36), primary_key=True)


class Client(Base):
    __tablename__ = "clients"
    client_id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=False)


class LoanApplication(Base):
    __tablename__ = "loan_applications"
    application_id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    client_id = Column(String(36), ForeignKey("clients.client_id"), nullable=False, index=True)
    principal_requested = Column(Float, nullable=False)
    declared_net_income = Column(Float, nullable=False)
    total_living_expenses = Column(Float, nullable=False)
    existing_debt_obligations = Column(Float, nullable=False)
    affordability_buffer = Column(Float, nullable=False)
    application_status = Column(String(32), nullable=False)
    timestamp_created = Column(DateTime(timezone=True), server_default=func.datetime("now"), nullable=False)


class LoanProduct(Base):
    __tablename__ = "loan_products"
    product_id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    product_name = Column(String(128), nullable=False)
    min_principal = Column(Float, nullable=False)
    max_principal = Column(Float, nullable=False)
    term_duration_days = Column(Integer, nullable=False)
    annual_interest_rate = Column(Float, nullable=False)
    default_initiation_fee_strategy = Column(String(32), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)


class ActiveLoan(Base):
    __tablename__ = "active_loans"
    loan_id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    application_id = Column(String(36), ForeignKey("loan_applications.application_id"), nullable=False, index=True)
    product_id = Column(String(36), ForeignKey("loan_products.product_id"), nullable=False, index=True)
    current_principal_balance = Column(Float, nullable=False)
    current_arrears_balance = Column(Float, nullable=False, default=0.0)
    loan_status = Column(String(32), nullable=False)


class FinancialTransaction(Base):
    __tablename__ = "financial_transactions"
    transaction_id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    loan_id = Column(String(36), ForeignKey("active_loans.loan_id"), nullable=False, index=True)
    transaction_type = Column(String(32), nullable=False)
    amount = Column(Float, nullable=False)
    allocation_to_principal = Column(Float, nullable=False, default=0.0)
    allocation_to_interest = Column(Float, nullable=False, default=0.0)
    allocation_to_fees = Column(Float, nullable=False, default=0.0)
    timestamp = Column(DateTime(timezone=True), server_default=func.datetime("now"), nullable=False)


def get_engine(db_path: str = None):
    db_path = db_path or os.environ.get("FUS30_DB", "sqlite:///fus30.db")
    engine = create_engine(db_path, connect_args={"check_same_thread": False})

    # Ensure SQLite enforces foreign keys
    if "sqlite" in engine.url.drivername:
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def init_db(engine=None):
    engine = engine or get_engine()
    Base.metadata.create_all(engine)
    return engine


if __name__ == "__main__":
    engine = init_db()
    print("Database initialized (tables created) using:", engine.url)
