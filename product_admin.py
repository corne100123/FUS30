import uuid
from typing import List

import pandas as pd
import streamlit as st
from sqlalchemy.orm import sessionmaker

from db_schema import get_engine, LoanProduct
from nca_engine import NCA_Engine


def _row_to_dict(lp: LoanProduct) -> dict:
    return {
        "product_id": lp.product_id,
        "product_name": lp.product_name,
        "min_principal": lp.min_principal,
        "max_principal": lp.max_principal,
        "term_duration_days": lp.term_duration_days,
        "annual_interest_rate": lp.annual_interest_rate,
        "default_initiation_fee_strategy": lp.default_initiation_fee_strategy,
        "is_active": bool(lp.is_active),
    }


def main():
    st.title("Product Administration")

    if "tenant_id" not in st.session_state or not st.session_state.get("tenant_id"):
        st.error("No tenant selected. `st.session_state['tenant_id']` must be set.")
        st.stop()

    tenant_id = st.session_state["tenant_id"]

    engine = get_engine()
    Session = sessionmaker(bind=engine)
    session = Session()

    with st.form("create_product_form", clear_on_submit=True):
        st.header("Create New Loan Product Template")
        product_name = st.text_input("Product Name", max_chars=128)
        min_principal = st.number_input("Min Principal", min_value=0.0, value=100.0, step=50.0, format="%.2f")
        max_principal = st.number_input("Max Principal", min_value=0.0, value=5000.0, step=50.0, format="%.2f")
        term_duration_days = st.number_input("Term Duration (Days)", min_value=1, value=90, step=1)
        annual_interest_percent = st.number_input("Annual Interest Rate (%)", min_value=0.0, value=28.0, step=0.01, format="%.2f")
        default_initiation_fee_strategy = st.selectbox(
            "Default Initiation Fee Strategy", ("MAX_LEGAL", "FIXED_DISCOUNTED")
        )

        submitted = st.form_submit_button("Create Product")

    if submitted:
        # Basic validations
        if not product_name:
            st.error("Product name is required.")
        elif max_principal < min_principal:
            st.error("Max Principal must be >= Min Principal.")
        else:
            # Convert interest percent to decimal
            proposed_interest = float(annual_interest_percent) / 100.0

            # Use conservative principal check (use max_principal)
            is_valid, message = NCA_Engine.validate_loan_product(
                principal=float(max_principal),
                term_days=int(term_duration_days),
                proposed_interest=proposed_interest,
                repo_rate=0.0825,  # dummy repo rate for Phase 1
            )

            if not is_valid:
                st.error(f"Product rejected: {message}")
            else:
                product = LoanProduct(
                    product_id=str(uuid.uuid4()),
                    tenant_id=tenant_id,
                    product_name=product_name,
                    min_principal=float(min_principal),
                    max_principal=float(max_principal),
                    term_duration_days=int(term_duration_days),
                    annual_interest_rate=float(proposed_interest),
                    default_initiation_fee_strategy=default_initiation_fee_strategy,
                    is_active=True,
                )
                try:
                    session.add(product)
                    session.commit()
                    st.success(f"Product '{product_name}' created.")
                except Exception as exc:
                    session.rollback()
                    st.error(f"Failed to create product: {exc}")

    # Display active products for tenant
    try:
        products: List[LoanProduct] = (
            session.query(LoanProduct)
            .filter(LoanProduct.tenant_id == tenant_id)
            .filter(LoanProduct.is_active == True)
            .all()
        )
        rows = [ _row_to_dict(p) for p in products ]
        if rows:
            df = pd.DataFrame(rows)
            # Show interest as percent for readability
            df["annual_interest_rate_pct"] = (df["annual_interest_rate"] * 100).round(2)
            st.subheader("Active Products")
            st.dataframe(df.drop(columns=["annual_interest_rate"]))
        else:
            st.info("No active products found for this tenant.")
    except Exception as exc:
        st.error(f"Failed to load products: {exc}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
