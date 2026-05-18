import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta

def run(get_db):
    tenant_id = st.session_state.get('tenant_id')
    if not tenant_id:
        st.error("No tenant selected. Please log in again.")
        return

    st.title("📊- Admin Dashboard")

    try:
        with get_db() as conn:
            # Fetching all data with agent information
            loans_query = """
                SELECT l.*, u.full_name as agent_name, u.username as agent_username
                FROM loans l
                LEFT JOIN users u ON l.agent_id = u.user_id
                WHERE l.tenant_id = ?
            """
            loans = pd.read_sql_query(loans_query, conn, params=(tenant_id,))

            payments_query = """
                SELECT p.*, u.full_name as agent_name, u.username as agent_username
                FROM payment_history p
                LEFT JOIN users u ON p.agent_id = u.user_id
                WHERE p.tenant_id = ?
            """
            payments = pd.read_sql_query(payments_query, conn, params=(tenant_id,))

            # Get active agents
            agents_query = """
                SELECT user_id, username, full_name, role
                FROM users
                WHERE tenant_id = ? AND role = 'Agent' AND is_active = 1
            """
            agents = pd.read_sql_query(agents_query, conn, params=(tenant_id,))

    except Exception as e:
        st.error(f"Database Error: {e}")
        st.error(f"Error type: {type(e).__name__}")
        return

    # --- OVERALL METRICS ---
    st.header("📈 Overall Business Metrics")
    col1, col2, col3, col4 = st.columns(4)

    # Total Book Value
    total_owed = loans['balance'].sum() if not loans.empty else 0.0
    # Total Principal Out
    total_principal = loans['principal'].sum() if not loans.empty else 0.0
    # Total Collected
    total_collected = payments['amount'].sum() if not payments.empty else 0.0
    # Active Loans
    active_loans = len(loans[loans['status'] == 'Active']) if not loans.empty else 0

    col1.metric("Total Book Value (Owed)", f"R {total_owed:,.2f}")
    col2.metric("Principal Out", f"R {total_principal:,.2f}")
    col3.metric("Total Collected", f"R {total_collected:,.2f}")
    col4.metric("Active Loans", f"{active_loans}")

    st.markdown("---")

    # --- AGENT-SPECIFIC DASHBOARDS ---
    st.header("👥 Agent Performance Dashboard")

    if agents.empty:
        st.warning("No active agents found in the system.")
        return

    # Agent selector
    selected_agent = st.selectbox(
        "Select Agent to View Details:",
        agents['user_id'].tolist(),
        format_func=lambda x: f"{agents[agents['user_id']==x]['full_name'].iloc[0]} ({agents[agents['user_id']==x]['username'].iloc[0]})"
    )

    agent_info = agents[agents['user_id'] == selected_agent].iloc[0]
    agent_loans = loans[loans['agent_id'] == selected_agent]
    agent_payments = payments[payments['agent_id'] == selected_agent]

    st.subheader(f"📊 {agent_info['full_name']} ({agent_info['username']}) - Performance Metrics")

    # Agent metrics
    agent_col1, agent_col2, agent_col3, agent_col4 = st.columns(4)

    agent_total_owed = agent_loans['balance'].sum() if not agent_loans.empty else 0.0
    agent_total_principal = agent_loans['principal'].sum() if not agent_loans.empty else 0.0
    agent_total_collected = agent_payments['amount'].sum() if not agent_payments.empty else 0.0
    agent_active_loans = len(agent_loans[agent_loans['status'] == 'Active']) if not agent_loans.empty else 0

    agent_col1.metric("Agent's Book Value", f"R {agent_total_owed:,.2f}")
    agent_col2.metric("Agent's Principal Out", f"R {agent_total_principal:,.2f}")
    agent_col3.metric("Agent's Collections", f"R {agent_total_collected:,.2f}")
    agent_col4.metric("Agent's Active Loans", f"{agent_active_loans}")

    # Daily Cashup for selected agent
    st.subheader("💰 Daily Cashup")
    today = datetime.now().strftime('%Y-%m-%d')

    # Filter today's data
    agent_today_payments = agent_payments[agent_payments['date'] == today] if not agent_payments.empty else agent_payments
    if not agent_loans.empty:
        agent_today_loans = agent_loans[agent_loans['created_at'].str.startswith(today)]
    else:
        agent_today_loans = agent_loans

    today_payments_total = agent_today_payments['amount'].sum() if not agent_today_payments.empty else 0.0
    today_loans_total = agent_today_loans['principal'].sum() if not agent_today_loans.empty else 0.0

    cashup_col1, cashup_col2, cashup_col3 = st.columns(3)
    cashup_col1.metric("Today's Payments", f"R {today_payments_total:,.2f}")
    cashup_col2.metric("Today's New Loans", f"R {today_loans_total:,.2f}")
    cashup_col3.metric("Net Cashup", f"R {today_payments_total - today_loans_total:,.2f}")

    # Agent's Active vs Non-Payers
    st.subheader("📋 Client Status Overview")

    if not agent_loans.empty:
        # Get clients with loans from this agent
        agent_client_ids = agent_loans['client_id'].unique()

        # Get payment activity in last 30 days
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        recent_payments = agent_payments[agent_payments['date'] >= thirty_days_ago]

        active_payers = len(recent_payments['loan_id'].unique())
        total_clients = len(agent_client_ids)
        non_payers = total_clients - active_payers

        status_col1, status_col2, status_col3 = st.columns(3)
        status_col1.metric("Active Clients", f"{active_payers}")
        status_col2.metric("Non-Payers (30+ days)", f"{non_payers}")
        status_col3.metric("Total Clients", f"{total_clients}")

        # Performance indicator
        if total_clients > 0:
            performance_rate = (active_payers / total_clients) * 100
            if performance_rate >= 80:
                st.success(f"✅ Excellent Performance: {performance_rate:.1f}% of clients are active payers")
            elif performance_rate >= 60:
                st.warning(f"⚠️ Good Performance: {performance_rate:.1f}% of clients are active payers")
            else:
                st.error(f"❌ Needs Attention: Only {performance_rate:.1f}% of clients are active payers")
    else:
        st.info("No loans assigned to this agent yet.")

    # Agent's Loan Portfolio
    st.subheader("🏦 Loan Portfolio Details")

    if not agent_loans.empty:
        # Loan status breakdown
        status_counts = agent_loans['status'].value_counts()

        portfolio_col1, portfolio_col2 = st.columns(2)

        with portfolio_col1:
            st.write("**Loan Status Distribution:**")
            for status, count in status_counts.items():
                st.write(f"- {status}: {count} loans")

        with portfolio_col2:
            # Average loan size
            avg_loan_size = agent_loans['principal'].mean()
            total_loans_value = agent_loans['principal'].sum()
            st.metric("Average Loan Size", f"R {avg_loan_size:,.2f}")
            st.metric("Total Portfolio Value", f"R {total_loans_value:,.2f}")

        # Recent loans table
        st.write("**Recent Loans:**")
        recent_loans = agent_loans.sort_values('created_at', ascending=False).head(5)
        if not recent_loans.empty:
            display_loans = recent_loans[['loan_id', 'principal', 'balance', 'status', 'created_at']]
            display_loans['created_at'] = pd.to_datetime(display_loans['created_at']).dt.strftime('%Y-%m-%d')
            st.dataframe(display_loans)
    else:
        st.info("No loans in this agent's portfolio.")

    # Overall Analysis
    st.header("📊 Overall Analysis")

    # System-wide performance
    total_agents = len(agents)
    total_system_loans = len(loans[loans['status'] == 'Active'])
    total_system_collected = payments['amount'].sum() if not payments.empty else 0.0

    analysis_col1, analysis_col2, analysis_col3 = st.columns(3)
    analysis_col1.metric("Total Active Agents", f"{total_agents}")
    analysis_col2.metric("System-wide Active Loans", f"{total_system_loans}")
    analysis_col3.metric("System-wide Collections", f"R {total_system_collected:,.2f}")

    # Agent ranking
    if not agents.empty:
        st.subheader("🏆 Agent Performance Ranking")

        agent_performance = []
        for _, agent in agents.iterrows():
            agent_id = agent['user_id']
            agent_loans_perf = loans[loans['agent_id'] == agent_id]
            agent_payments_perf = payments[payments['agent_id'] == agent_id]

            portfolio_value = agent_loans_perf['balance'].sum() if not agent_loans_perf.empty else 0.0
            collections = agent_payments_perf['amount'].sum() if not agent_payments_perf.empty else 0.0
            active_loans_count = len(agent_loans_perf[agent_loans_perf['status'] == 'Active'])

            agent_performance.append({
                'Agent': agent['full_name'],
                'Portfolio Value': portfolio_value,
                'Collections': collections,
                'Active Loans': active_loans_count
            })

        perf_df = pd.DataFrame(agent_performance)
        perf_df = perf_df.sort_values('Collections', ascending=False)
        st.dataframe(perf_df)

    # --- OVERDUE ALERT LEDGER ---
    st.markdown("---")
    st.subheader("🚩 Overdue / Due Now Accounts")
    if not loans.empty:
        loans['due_date'] = pd.to_datetime(loans['due_date'])
        overdue = loans[loans['due_date'].dt.date <= pd.Timestamp.now().date()]
        if not overdue.empty:
            st.warning(f"Attention: {len(overdue)} accounts require collection.")
            st.table(overdue[['loan_id', 'balance', 'due_date']])
        else:
            st.success("All accounts are currently within their 30-day window.")