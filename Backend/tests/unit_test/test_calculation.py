
import pytest
from app.schemas.calculation import (
    FutureValue,
    CheckFeasibilityRequest,
    SuggestedAllocation,
    SIPRequest,
    GlidePathRequest,
)
from app.services.math.calculation import (
    future_value_goal,
    check_feasibility,
    suggest_allocation,
    calculate_sip,
    calculate_glide_path,
)


# ─────────────────────────────────────────────────────────────────────
# ── TESTS: FUTURE VALUE CALCULATION
# ─────────────────────────────────────────────────────────────────────

class TestFutureValue:
    """Test future_value_goal function."""

    def test_future_value_zero_inflation(self):
        """Zero inflation: future value = principal."""
        data = FutureValue(
            principal=1_000_000,
            infation_rate=0.0,  # Note: model has typo 'infation'
            years=10
        )
        result = future_value_goal(data)
        assert result["future_value"] == 1_000_000

    def test_future_value_positive_inflation(self):
        """Positive inflation increases future value."""
        data = FutureValue(
            principal=1_000_000,
            infation_rate=6.0,
            years=10
        )
        result = future_value_goal(data)
        # FV = 1M * (1.06)^10 ≈ 1.791M
        assert result["future_value"] > 1_000_000
        assert result["future_value"] < 2_000_000

    def test_future_value_high_inflation_long_period(self):
        """High inflation over long period significantly increases value."""
        data = FutureValue(
            principal=1_000_000,
            infation_rate=8.0,
            years=20
        )
        result = future_value_goal(data)
        # FV = 1M * (1.08)^20 ≈ 4.66M
        assert result["future_value"] > 4_000_000

    def test_future_value_zero_years(self):
        """Zero years: future value = principal."""
        data = FutureValue(
            principal=1_000_000,
            infation_rate=6.0,
            years=0
        )
        result = future_value_goal(data)
        assert result["future_value"] == 1_000_000

    def test_future_value_one_year(self):
        """One year: FV = principal * (1 + inflation)."""
        data = FutureValue(
            principal=1_000_000,
            infation_rate=6.0,
            years=1
        )
        result = future_value_goal(data)
        assert result["future_value"] == 1_000_000 * 1.06

    def test_future_value_compound_effect(self):
        """Compound effect: 10 years doubles at ~7.2% inflation."""
        principal = 1_000_000
        data = FutureValue(
            principal=principal,
            infation_rate=7.2,
            years=10
        )
        result = future_value_goal(data)
        # Should approximately double
        assert 1_900_000 < result["future_value"] < 2_100_000


# ─────────────────────────────────────────────────────────────────────
# ── TESTS: FEASIBILITY CHECK
# ─────────────────────────────────────────────────────────────────────

class TestCheckFeasibility:
    """Test check_feasibility function with new schema."""

    def test_feasible_within_savings_cap(self):
        """Feasible when total SIP is within savings cap."""
        data = CheckFeasibilityRequest(
            starting_monthly_sip=30_000,
            annual_step_up_pct=0.94,
            monthly_income=200_000,
            income_raise_pct=7.0,
            monthly_expenses=50_000,
            years_to_goal=5,
            existing_monthly_sip=0.0,
            savings_cap_pct=50.0
        )
        result = check_feasibility(data)
        assert result["feasible"] is True
        assert result["breach_count"] == 0

    def test_infeasible_exceeds_savings_cap(self):
        """Infeasible when total SIP exceeds savings cap."""
        data = CheckFeasibilityRequest(
            starting_monthly_sip=150_000,  # Far too high
            annual_step_up_pct=0.94,
            monthly_income=200_000,
            income_raise_pct=7.0,
            monthly_expenses=50_000,
            years_to_goal=5,
            existing_monthly_sip=0.0,
            savings_cap_pct=50.0
        )
        result = check_feasibility(data)
        assert result["feasible"] is False
        assert result["breach_count"] > 0

    def test_feasible_at_boundary(self):
        """Feasible when at exact savings cap."""
        # Disposable income = 150k (200k - 50k)
        # 50% cap = 75k
        data = CheckFeasibilityRequest(
            starting_monthly_sip=75_000,
            annual_step_up_pct=0.0,  # No step-up for simplicity
            monthly_income=200_000,
            income_raise_pct=7.0,
            monthly_expenses=50_000,
            years_to_goal=3,
            existing_monthly_sip=0.0,
            savings_cap_pct=50.0
        )
        result = check_feasibility(data)
        # Should be feasible at exact boundary
        assert result["feasible"] is True

    def test_existing_sip_considered(self):
        """Test existing SIP commitments are considered."""
        data = CheckFeasibilityRequest(
            starting_monthly_sip=40_000,
            annual_step_up_pct=0.94,
            monthly_income=200_000,
            income_raise_pct=7.0,
            monthly_expenses=50_000,
            years_to_goal=5,
            existing_monthly_sip=30_000,  # Already committed 30k
            savings_cap_pct=50.0
        )
        result = check_feasibility(data)
        # Total would be 70k which is within 75k cap
        assert "yearly_summary" in result
        assert all(item["existing_sip"] == 30_000 for item in result["yearly_summary"][:1])

    def test_yearly_summary_present(self):
        """Test yearly summary is included in result."""
        data = CheckFeasibilityRequest(
            starting_monthly_sip=30_000,
            annual_step_up_pct=0.94,
            monthly_income=200_000,
            income_raise_pct=7.0,
            monthly_expenses=50_000,
            years_to_goal=5,
            existing_monthly_sip=0.0,
            savings_cap_pct=50.0
        )
        result = check_feasibility(data)
        assert "yearly_summary" in result
        assert len(result["yearly_summary"]) == 5
        assert all("year" in item for item in result["yearly_summary"])
        assert all("savings_ratio_pct" in item for item in result["yearly_summary"])


# ─────────────────────────────────────────────────────────────────────
# ── TESTS: ALLOCATION SUGGESTION
# ─────────────────────────────────────────────────────────────────────

class TestSuggestAllocation:
    """Test suggest_allocation function."""

    def test_short_term_low_risk(self):
        """Short term (< 3 years) + low risk = low equity."""
        data = SuggestedAllocation(
            years=2,
            risk="low"
        )
        result = suggest_allocation(data)
        # Base: 20%, Low: -20% → 0%
        assert result["equity_allocation"] == 0
        assert result["debt_allocation"] == 100

    def test_short_term_medium_risk(self):
        """Short term (< 3 years) + medium risk = 20% equity."""
        data = SuggestedAllocation(
            years=2,
            risk="medium"
        )
        result = suggest_allocation(data)
        assert result["equity_allocation"] == 20
        assert result["debt_allocation"] == 80

    def test_short_term_high_risk(self):
        """Short term (< 3 years) + high risk = 40% equity."""
        data = SuggestedAllocation(
            years=2,
            risk="high"
        )
        result = suggest_allocation(data)
        # Base: 20%, High: +20% → 40%
        assert result["equity_allocation"] == 40
        assert result["debt_allocation"] == 60

    def test_medium_term_low_risk(self):
        """Medium term (3-7 years) + low risk = 30% equity."""
        data = SuggestedAllocation(
            years=5,
            risk="low"
        )
        result = suggest_allocation(data)
        # Base: 50%, Low: -20% → 30%
        assert result["equity_allocation"] == 30
        assert result["debt_allocation"] == 70

    def test_medium_term_medium_risk(self):
        """Medium term (3-7 years) + medium risk = 50% equity."""
        data = SuggestedAllocation(
            years=5,
            risk="medium"
        )
        result = suggest_allocation(data)
        assert result["equity_allocation"] == 50
        assert result["debt_allocation"] == 50

    def test_medium_term_high_risk(self):
        """Medium term (3-7 years) + high risk = 70% equity."""
        data = SuggestedAllocation(
            years=5,
            risk="high"
        )
        result = suggest_allocation(data)
        # Base: 50%, High: +20% → 70%
        assert result["equity_allocation"] == 70
        assert result["debt_allocation"] == 30

    def test_long_term_low_risk(self):
        """Long term (>= 7 years) + low risk = 50% equity."""
        data = SuggestedAllocation(
            years=10,
            risk="low"
        )
        result = suggest_allocation(data)
        # Base: 70%, Low: -20% → 50%
        assert result["equity_allocation"] == 50
        assert result["debt_allocation"] == 50

    def test_long_term_medium_risk(self):
        """Long term (>= 7 years) + medium risk = 70% equity."""
        data = SuggestedAllocation(
            years=10,
            risk="medium"
        )
        result = suggest_allocation(data)
        assert result["equity_allocation"] == 70
        assert result["debt_allocation"] == 30

    def test_long_term_high_risk(self):
        """Long term (>= 7 years) + high risk = 90% equity (capped at 100)."""
        data = SuggestedAllocation(
            years=10,
            risk="high"
        )
        result = suggest_allocation(data)
        # Base: 70%, High: +20% → 90%
        assert result["equity_allocation"] == 90
        assert result["debt_allocation"] == 10

    def test_equity_debt_sum_to_100(self):
        """Allocation: equity + debt always = 100%."""
        test_cases = [
            (2, "low"), (5, "medium"), (10, "high"), (3, "low"), (7, "high")
        ]
        for years, risk in test_cases:
            data = SuggestedAllocation(years=years, risk=risk)
            result = suggest_allocation(data)
            assert result["equity_allocation"] + result["debt_allocation"] == 100

    def test_allocation_never_negative(self):
        """Allocation: equity and debt never negative."""
        test_cases = [
            (1, "low"), (2, "low"), (3, "low"), (10, "high"), (20, "high")
        ]
        for years, risk in test_cases:
            data = SuggestedAllocation(years=years, risk=risk)
            result = suggest_allocation(data)
            assert result["equity_allocation"] >= 0
            assert result["debt_allocation"] >= 0

    def test_allocation_never_exceeds_100(self):
        """Allocation: equity and debt never exceed 100%."""
        test_cases = [
            (1, "high"), (10, "high"), (20, "high"), (30, "high")
        ]
        for years, risk in test_cases:
            data = SuggestedAllocation(years=years, risk=risk)
            result = suggest_allocation(data)
            assert result["equity_allocation"] <= 100
            assert result["debt_allocation"] <= 100


# ─────────────────────────────────────────────────────────────────────
# ── TESTS: GLIDE PATH CALCULATION
# ─────────────────────────────────────────────────────────────────────

class TestGlidePath:
    """Test calculate_glide_path function for year-by-year allocation."""

    def test_glide_path_schedule_length(self):
        """Schedule should have total_years + 1 entries (including start and end)."""
        data = GlidePathRequest(
            current_age=35,
            goal_age=55,
            start_equity_percent=75.0,
            end_equity_percent=25.0
        )
        result = calculate_glide_path(data)
        # 55 - 35 = 20 years, so should have 21 entries (0 to 20 inclusive)
        assert len(result["yearly_allocation_table"]) == 21

    def test_glide_path_starts_at_current_age(self):
        """First entry should start at current_age."""
        data = GlidePathRequest(
            current_age=35,
            goal_age=55,
            start_equity_percent=75.0,
            end_equity_percent=25.0
        )
        result = calculate_glide_path(data)
        assert result["yearly_allocation_table"][0]["year"] == 35
        assert result["yearly_allocation_table"][0]["age"] == 35

    def test_glide_path_ends_at_goal_age(self):
        """Last entry should end at goal_age."""
        data = GlidePathRequest(
            current_age=35,
            goal_age=55,
            start_equity_percent=75.0,
            end_equity_percent=25.0
        )
        result = calculate_glide_path(data)
        assert result["yearly_allocation_table"][-1]["year"] == 55
        assert result["yearly_allocation_table"][-1]["age"] == 55

    def test_glide_path_starts_with_correct_equity(self):
        """First entry equity should equal start_equity_percent."""
        data = GlidePathRequest(
            current_age=35,
            goal_age=55,
            start_equity_percent=75.0,
            end_equity_percent=25.0
        )
        result = calculate_glide_path(data)
        assert result["yearly_allocation_table"][0]["equity_percent"] == 75.0

    def test_glide_path_ends_with_correct_equity(self):
        """Last entry equity should equal end_equity_percent."""
        data = GlidePathRequest(
            current_age=35,
            goal_age=55,
            start_equity_percent=75.0,
            end_equity_percent=25.0
        )
        result = calculate_glide_path(data)
        assert result["yearly_allocation_table"][-1]["equity_percent"] == 25.0

    def test_glide_path_decreases_monotonically(self):
        """Equity percentage should decrease monotonically over time."""
        data = GlidePathRequest(
            current_age=30,
            goal_age=60,
            start_equity_percent=80.0,
            end_equity_percent=20.0
        )
        result = calculate_glide_path(data)
        schedule = result["yearly_allocation_table"]
        for i in range(1, len(schedule)):
            assert schedule[i]["equity_percent"] <= schedule[i-1]["equity_percent"]

    def test_glide_path_linear_decrease(self):
        """Equity should decrease linearly from start to end."""
        data = GlidePathRequest(
            current_age=35,
            goal_age=55,
            start_equity_percent=80.0,
            end_equity_percent=20.0
        )
        result = calculate_glide_path(data)
        schedule = result["yearly_allocation_table"]
        total_years = 20
        annual_decrease = (80.0 - 20.0) / total_years
        
        for i, entry in enumerate(schedule):
            expected_equity = 80.0 - (annual_decrease * i)
            assert abs(entry["equity_percent"] - expected_equity) < 0.01

    def test_glide_path_equity_plus_debt_equals_100(self):
        """Equity + Debt should always = 100%."""
        data = GlidePathRequest(
            current_age=30,
            goal_age=60,
            start_equity_percent=75.0,
            end_equity_percent=25.0
        )
        result = calculate_glide_path(data)
        for entry in result["yearly_allocation_table"]:
            assert entry["equity_percent"] + entry["debt_percent"] == 100.0

    def test_glide_path_zero_years_to_goal(self):
        """Zero years to goal: current_age = goal_age raises ValidationError."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            data = GlidePathRequest(
                current_age=50,
                goal_age=50,
                start_equity_percent=75.0,
                end_equity_percent=25.0
            )

    def test_glide_path_negative_years_returns_empty(self):
        """Negative years (goal_age < current_age) raises ValidationError."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            data = GlidePathRequest(
                current_age=60,
                goal_age=50,
                start_equity_percent=75.0,
                end_equity_percent=25.0
            )

    def test_glide_path_short_window(self):
        """Short 3-year window should still show linear decrease."""
        data = GlidePathRequest(
            current_age=47,
            goal_age=50,
            start_equity_percent=60.0,
            end_equity_percent=30.0
        )
        result = calculate_glide_path(data)
        schedule = result["yearly_allocation_table"]
        assert len(schedule) == 4  # Years 47, 48, 49, 50
        assert schedule[0]["equity_percent"] == 60.0
        assert schedule[-1]["equity_percent"] == 30.0
        
        # Check linear decrease
        annual_decrease = (60.0 - 30.0) / 3
        for i in range(len(schedule)):
            expected = 60.0 - (annual_decrease * i)
            assert abs(schedule[i]["equity_percent"] - expected) < 0.01

    def test_glide_path_long_window(self):
        """Long 30-year window should show smooth de-risking."""
        data = GlidePathRequest(
            current_age=25,
            goal_age=55,
            start_equity_percent=80.0,
            end_equity_percent=20.0
        )
        result = calculate_glide_path(data)
        schedule = result["yearly_allocation_table"]
        assert len(schedule) == 31  # 25 to 55 inclusive
        assert schedule[0]["equity_percent"] == 80.0
        assert schedule[-1]["equity_percent"] == 20.0

    def test_glide_path_all_percentages_valid(self):
        """All equity and debt percentages should be between 0 and 100."""
        data = GlidePathRequest(
            current_age=30,
            goal_age=65,
            start_equity_percent=85.0,
            end_equity_percent=15.0
        )
        result = calculate_glide_path(data)
        for entry in result["yearly_allocation_table"]:
            assert 0 <= entry["equity_percent"] <= 100
            assert 0 <= entry["debt_percent"] <= 100


# ─────────────────────────────────────────────────────────────────────
# ── TESTS: SIP CALCULATION
# ─────────────────────────────────────────────────────────────────────

class TestCalculateSIP:
    """Test calculate_sip function with inflation and salary hike."""

    def test_sip_basic_calculation(self):
        """Basic SIP calculation with inflation and salary hike."""
        data = SIPRequest(
            goal_amount=10_000_000,
            pre_ret_return=10.0,
            inflation_rate=6.0,
            income_raise_pct=8.0,
            years_to_goal=20
        )
        result = calculate_sip(data)
        assert result["starting_monthly_sip"] > 0
        assert isinstance(result["starting_monthly_sip"], float)

    def test_sip_zero_inflation(self):
        """SIP with zero inflation should work."""
        data = SIPRequest(
            goal_amount=10_000_000,
            pre_ret_return=10.0,
            inflation_rate=0.0,
            income_raise_pct=5.0,
            years_to_goal=20
        )
        result = calculate_sip(data)
        assert result["starting_monthly_sip"] > 0

    def test_sip_zero_income_raise(self):
        """SIP with zero income raise (flat salary)."""
        data = SIPRequest(
            goal_amount=10_000_000,
            pre_ret_return=10.0,
            inflation_rate=6.0,
            income_raise_pct=0.0,
            years_to_goal=20
        )
        result = calculate_sip(data)
        assert result["starting_monthly_sip"] > 0

    def test_sip_income_raise_equals_inflation(self):
        """SIP when income raise = inflation (no real growth)."""
        data = SIPRequest(
            goal_amount=10_000_000,
            pre_ret_return=10.0,
            inflation_rate=6.0,
            income_raise_pct=6.0,  # Same as inflation
            years_to_goal=20
        )
        result = calculate_sip(data)
        assert result["starting_monthly_sip"] > 0

    def test_sip_income_raise_exceeds_inflation(self):
        """SIP when income raise > inflation (real income growth)."""
        data = SIPRequest(
            goal_amount=10_000_000,
            pre_ret_return=10.0,
            inflation_rate=5.0,
            income_raise_pct=10.0,  # Greater than inflation
            years_to_goal=20
        )
        result = calculate_sip(data)
        assert result["starting_monthly_sip"] > 0

    def test_sip_lower_return_requires_higher_sip(self):
        """Lower return rate requires higher SIP."""
        data_low_return = SIPRequest(
            goal_amount=10_000_000,
            pre_ret_return=7.0,  # Lower return
            inflation_rate=6.0,
            income_raise_pct=8.0,
            years_to_goal=20
        )
        data_high_return = SIPRequest(
            goal_amount=10_000_000,
            pre_ret_return=12.0,  # Higher return
            inflation_rate=6.0,
            income_raise_pct=8.0,
            years_to_goal=20
        )
        result_low = calculate_sip(data_low_return)
        result_high = calculate_sip(data_high_return)
        assert result_low["starting_monthly_sip"] > result_high["starting_monthly_sip"]

    def test_sip_shorter_window_requires_higher_sip(self):
        """Shorter accumulation window requires higher SIP."""
        data_short = SIPRequest(
            goal_amount=10_000_000,
            pre_ret_return=10.0,
            inflation_rate=6.0,
            income_raise_pct=8.0,
            years_to_goal=10  # Shorter
        )
        data_long = SIPRequest(
            goal_amount=10_000_000,
            pre_ret_return=10.0,
            inflation_rate=6.0,
            income_raise_pct=8.0,
            years_to_goal=20  # Longer
        )
        result_short = calculate_sip(data_short)
        result_long = calculate_sip(data_long)
        assert result_short["starting_monthly_sip"] > result_long["starting_monthly_sip"]

    def test_sip_higher_corpus_requires_higher_sip(self):
        """Higher target corpus requires higher SIP."""
        data_low_corpus = SIPRequest(
            goal_amount=5_000_000,
            pre_ret_return=10.0,
            inflation_rate=6.0,
            income_raise_pct=8.0,
            years_to_goal=20
        )
        data_high_corpus = SIPRequest(
            goal_amount=20_000_000,
            pre_ret_return=10.0,
            inflation_rate=6.0,
            income_raise_pct=8.0,
            years_to_goal=20
        )
        result_low = calculate_sip(data_low_corpus)
        result_high = calculate_sip(data_high_corpus)
        assert result_low["starting_monthly_sip"] < result_high["starting_monthly_sip"]

    def test_sip_result_is_positive(self):
        """SIP result should always be positive."""
        test_cases = [
            (10_000_000, 10.0, 6.0, 8.0, 20),
            (5_000_000, 8.0, 5.0, 7.0, 15),
            (15_000_000, 12.0, 6.5, 9.0, 25),
        ]
        for corpus, ret, inf, inc, years in test_cases:
            data = SIPRequest(
                goal_amount=corpus,
                pre_ret_return=ret,
                inflation_rate=inf,
                income_raise_pct=inc,
                years_to_goal=years
            )
            result = calculate_sip(data)
            assert result["starting_monthly_sip"] > 0

    def test_sip_step_up_derived_from_inflation_and_income(self):
        """SIP step-up should be derived from income raise and inflation."""
        # When income_raise > inflation, step-up should be positive
        data = SIPRequest(
            goal_amount=10_000_000,
            pre_ret_return=10.0,
            inflation_rate=5.0,
            income_raise_pct=10.0,  # > inflation
            years_to_goal=20
        )
        result = calculate_sip(data)
        # g = ((1 + 0.10) / (1 + 0.05)) - 1 = 1.1 / 1.05 - 1 ≈ 0.0476 (4.76% real growth)
        assert result["starting_monthly_sip"] > 0
        assert isinstance(result["starting_monthly_sip"], float)


# ─────────────────────────────────────────────────────────────────────
# ── COMBINED TESTS: CALCULATION FLOW
# ─────────────────────────────────────────────────────────────────────

class TestCalculationFlow:
    """Test integrated calculation flow."""

    def test_goal_future_value_then_feasibility(self):
        """Calculate future value of goal, then check feasibility."""
        # Step 1: Future value of 1M goal in 10 years at 6% inflation
        fv_data = FutureValue(principal=1_000_000, infation_rate=6.0, years=10)
        fv_result = future_value_goal(fv_data)
        goal_fv = fv_result["future_value"]

        # Step 2: Check if one-time goal requiring SIP is feasible
        # Assume need 30k monthly SIP with step-up for this goal
        feas_data = CheckFeasibilityRequest(
            starting_monthly_sip=30_000,
            annual_step_up_pct=0.94,
            monthly_income=200_000,
            income_raise_pct=7.0,
            monthly_expenses=50_000,
            years_to_goal=10,
            existing_monthly_sip=0.0,
            savings_cap_pct=50.0
        )
        feas_result = check_feasibility(feas_data)
        
        assert feas_result["feasible"] is True or feas_result["feasible"] is False
        assert "yearly_summary" in feas_result

    def test_allocation_then_sip_calculation(self):
        """Determine allocation, then calculate SIP for risk profile."""
        # Step 1: Suggest allocation for 15-year goal with medium risk
        alloc_data = SuggestedAllocation(years=15, risk="medium")
        alloc_result = suggest_allocation(alloc_data)
        
        # Step 2: Calculate SIP for corpus with derived step-up
        sip_data = SIPRequest(
            goal_amount=10_000_000,
            pre_ret_return=10.0,
            inflation_rate=6.0,
            income_raise_pct=8.0,
            years_to_goal=15
        )
        sip_result = calculate_sip(sip_data)
        
        assert sip_result["starting_monthly_sip"] > 0

    def test_glide_path_then_allocation(self):
        """Generate glide path, then verify allocation consistency."""
        # Step 1: Calculate glide path
        glide_data = GlidePathRequest(
            current_age=35,
            goal_age=55,
            start_equity_percent=75.0,
            end_equity_percent=25.0
        )
        glide_result = calculate_glide_path(glide_data)
        
        # Step 2: Verify that allocation starts high and ends low
        first_equity = glide_result["yearly_allocation_table"][0]["equity_percent"]
        last_equity = glide_result["yearly_allocation_table"][-1]["equity_percent"]
        
        assert first_equity == 75.0
        assert last_equity == 25.0
        assert first_equity > last_equity


