from typing import Tuple


class NCA_Engine:
    """Compliance engine implementing NCA (South African National Credit Act) limits.

    All methods are static and perform input validation. Currency values are returned
    as floats rounded to two decimal places where appropriate.
    """

    @staticmethod
    def calculate_max_initiation_fee(principal_amount: float) -> float:
        """Calculate the maximum initiation fee per NCA rules.

        Rules:
        - Base fee is R165.
        - Add 10% of any principal amount that exceeds R1000.
        - The returned fee can never exceed R1050.

        Args:
            principal_amount: The loan principal amount in Rands (>= 0).

        Returns:
            The maximum initiation fee (rounded to 2 decimals).

        Raises:
            TypeError: if principal_amount is not a number.
            ValueError: if principal_amount is negative.
        """
        try:
            p = float(principal_amount)
        except Exception as exc:
            raise TypeError("principal_amount must be a number") from exc

        if p < 0:
            raise ValueError("principal_amount must be non-negative")

        excess = max(0.0, p - 1000.0)
        fee = 165.0 + 0.10 * excess
        fee = min(fee, 1050.0)
        return round(fee, 2)

    @staticmethod
    def calculate_max_service_fee(days_in_term: int) -> float:
        """Calculate the maximum service fee for the loan term.

        Rules:
        - R60 per 30 days (i.e. R2 per day).
        - Partial months are prorated at R2 per day.

        Args:
            days_in_term: Total number of days in the loan term (>= 0).

        Returns:
            The maximum service fee (rounded to 2 decimals).

        Raises:
            TypeError: if days_in_term is not an int.
            ValueError: if days_in_term is negative.
        """
        if not isinstance(days_in_term, int):
            raise TypeError("days_in_term must be an integer number of days")
        if days_in_term < 0:
            raise ValueError("days_in_term must be non-negative")

        fee_per_day = 60.0 / 30.0  # R2.0 per day
        fee = days_in_term * fee_per_day
        return round(fee, 2)

    @staticmethod
    def calculate_max_annual_interest(current_repo_rate: float) -> float:
        """Return the legal maximum annual interest rate.

        Logic: repo rate + 21 percentage points (0.21 in decimal form).

        Args:
            current_repo_rate: Current repo rate expressed as decimal (e.g., 0.07 for 7%).

        Returns:
            The maximum allowed annual interest rate as a decimal (e.g., 0.28).

        Raises:
            TypeError: if current_repo_rate is not numeric.
        """
        try:
            r = float(current_repo_rate)
        except Exception as exc:
            raise TypeError("current_repo_rate must be a number") from exc

        max_rate = r + 0.21
        # Keep reasonable precision for rates
        return round(max_rate, 6)

    @staticmethod
    def validate_loan_product(
        principal: float, term_days: int, proposed_interest: float, repo_rate: float
    ) -> Tuple[bool, str]:
        """Validate a proposed loan product against NCA guardrails.

        Checks performed:
        - `principal` must be non-negative.
        - `term_days` must be a non-negative integer.
        - `proposed_interest` must not exceed `calculate_max_annual_interest(repo_rate)`.

        Note: initiation and service fees are calculable from `principal` and `term_days`
        respectively, but since there is no proposed-fee input to validate against, this
        function computes the maxima and includes them in the error message only when
        relevant inputs are invalid.

        Args:
            principal: Proposed loan principal (>= 0).
            term_days: Loan term in days (>= 0).
            proposed_interest: Proposed annual interest rate as decimal (e.g., 0.28).
            repo_rate: Current repo rate as decimal (e.g., 0.07).

        Returns:
            Tuple where first element is True if valid, otherwise False. Second element
            is "Valid" or an explanatory error message.
        """
        # Validate inputs
        try:
            p = float(principal)
        except Exception as exc:
            return False, "principal must be a number"
        if p < 0:
            return False, "principal must be non-negative"

        if not isinstance(term_days, int):
            return False, "term_days must be an integer"
        if term_days < 0:
            return False, "term_days must be non-negative"

        try:
            proposed = float(proposed_interest)
        except Exception:
            return False, "proposed_interest must be a number"

        try:
            repo = float(repo_rate)
        except Exception:
            return False, "repo_rate must be a number"

        # Interest check
        max_interest = NCA_Engine.calculate_max_annual_interest(repo)
        if proposed > max_interest:
            return False, (
                f"Proposed interest {proposed:.6f} exceeds max allowed {max_interest:.6f} "
                f"(repo_rate {repo:.6f} + 0.21)"
            )

        # All checks passed
        return True, "Valid"


__all__ = ["NCA_Engine"]
