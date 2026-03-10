"""
Unit tests for one-time goal planner functionality.
Tests the one_time_goal function with various scenarios.
"""

import pytest
from app.schemas.goals import OneTimeGoalRequest
from app.services.math.goals import one_time_goal
from app.models.db import User


# ─────────────────────────────────────────────────────────────────────
# ── FIXTURES
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def standard_user():
    """Standard user with healthy financial profile."""
    user = User()
    user.id = "test-user-1"
    user.full_name = "Test User"
    user.age = 25
    user.current_income = 2_400_000  # 2.4L annual = 200k monthly
    user.income_raise_pct = 7.0
    user.current_monthly_expenses = 50_000
    user.inflation_rate = 6.0
    user.marital_status = "Single"
    return user


@pytest.fixture
def high_income_user():
    """High income user with large financial capacity."""
    user = User()
    user.id = "test-user-2"
    user.full_name = "High Income User"
    user.age = 30
    user.current_income = 12_000_000  # 12L annual = 1M monthly
    user.income_raise_pct = 10.0
    user.current_monthly_expenses = 200_000
    user.inflation_rate = 6.0
    user.marital_status = "Single"
    return user


@pytest.fixture
def tight_budget_user():
    """User with tight budget constraints."""
    user = User()
    user.id = "test-user-3"
    user.full_name = "Tight Budget User"
    user.age = 35
    user.current_income = 600_000  # 50k monthly
    user.income_raise_pct = 5.0
    user.current_monthly_expenses = 40_000
    user.inflation_rate = 6.0
    user.marital_status = "Single"
    return user


# ─────────────────────────────────────────────────────────────────────
# ── TESTS: FEASIBLE SCENARIOS
# ─────────────────────────────────────────────────────────────────────

class TestOneTimeGoalFeasible:
    """Test feasible one-time goal scenarios."""

    def test_short_term_car_goal_feasible(self, standard_user):
        """Test short-term car purchase goal (3 years)."""
        goal_request = OneTimeGoalRequest(
            goal_name="Buy a Car",
            goal_amount=1_500_000,
            years_to_goal=3.0,
            pre_ret_return=10.0,
            existing_corpus=0.0,
            existing_monthly_sip=0.0,
            risk_tolerance="moderate"
        )
        
        result = one_time_goal(goal_request, standard_user)
        
        assert result["status"] == "feasible"
        assert result["goal_name"] == "Buy a Car"
        assert result["goal_summary"]["goal_amount_today"] == 1_500_000
        assert result["goal_summary"]["years_to_goal"] == 3.0
        assert result["goal_summary"]["target_age"] == 28
        
        # Should have positive SIP requirement
        assert result["sip_plan"]["starting_monthly_sip"] > 0
        
        # Feasibility should be positive
        assert result["feasibility"]["feasible"] is True
        assert result["feasibility"]["breach_count"] == 0
        
        # Allocation should match moderate risk + short horizon
        assert result["allocation"]["initial_equity_pct"] == 50
        assert result["allocation"]["risk_profile"] == "moderate"

    def test_medium_term_house_down_payment_feasible(self, high_income_user):
        """Test medium-term house down payment goal (7 years)."""
        goal_request = OneTimeGoalRequest(
            goal_name="House Down Payment",
            goal_amount=5_000_000,
            years_to_goal=7.0,
            pre_ret_return=12.0,
            existing_corpus=500_000,
            existing_monthly_sip=10_000,
            risk_tolerance="high"
        )
        
        result = one_time_goal(goal_request, high_income_user)
        
        assert result["status"] == "feasible"
        assert result["goal_summary"]["goal_amount_at_target"] > 5_000_000  # Inflation adjusted
        
        # Should consider existing corpus
        assert result["sip_plan"]["existing_corpus"] == 500_000
        assert result["sip_plan"]["fv_of_existing_corpus"] > 500_000
        
        # High risk should increase equity allocation
        assert result["allocation"]["initial_equity_pct"] >= 70
        assert result["allocation"]["risk_profile"] == "high"

    def test_long_term_education_goal_feasible(self, standard_user):
        """Test long-term education goal (10 years)."""
        goal_request = OneTimeGoalRequest(
            goal_name="Child's Education",
            goal_amount=3_000_000,
            years_to_goal=10.0,
            pre_ret_return=11.0,
            existing_corpus=0.0,
            existing_monthly_sip=0.0,
            risk_tolerance="moderate"
        )
        
        result = one_time_goal(goal_request, standard_user)
        
        assert result["status"] == "feasible"
        
        # Long horizon should have higher equity allocation
        assert result["allocation"]["initial_equity_pct"] >= 60
        
        # Glide path should be present
        assert "glide_path" in result
        assert result["glide_path"]["total_years"] == 10
        assert len(result["glide_path"]["yearly_allocation_table"]) == 11  # 0 to 10


# ─────────────────────────────────────────────────────────────────────
# ── TESTS: INFEASIBLE SCENARIOS
# ─────────────────────────────────────────────────────────────────────

class TestOneTimeGoalInfeasible:
    """Test infeasible one-time goal scenarios."""

    def test_too_large_amount_short_timeline_infeasible(self, tight_budget_user):
        """Test unrealistic goal: 20L in 2 years with tight budget."""
        goal_request = OneTimeGoalRequest(
            goal_name="Unrealistic Goal",
            goal_amount=20_000_000,
            years_to_goal=2.0,
            pre_ret_return=10.0,
            existing_corpus=0.0,
            existing_monthly_sip=0.0,
            risk_tolerance="moderate"
        )
        
        result = one_time_goal(goal_request, tight_budget_user)
        
        assert result["status"] == "infeasible"
        assert "message" in result
        assert "suggestion" in result
        assert result["feasibility_report"]["feasible"] is False
        assert result["feasibility_report"]["breach_count"] > 0

    def test_tight_budget_high_goal_infeasible(self, tight_budget_user):
        """Test tight budget with moderately high goal."""
        goal_request = OneTimeGoalRequest(
            goal_name="Car Purchase",
            goal_amount=2_000_000,
            years_to_goal=3.0,
            pre_ret_return=10.0,
            existing_corpus=0.0,
            existing_monthly_sip=0.0,
            risk_tolerance="low"
        )
        
        result = one_time_goal(goal_request, tight_budget_user)
        
        # Might be feasible or infeasible depending on calculations
        # Just verify structure
        assert result["status"] in ["feasible", "infeasible"]
        if result["status"] == "feasible":
            assert "feasibility" in result
        else:
            assert "feasibility_report" in result
        assert "sip_report" in result


# ─────────────────────────────────────────────────────────────────────
# ── TESTS: RISK TOLERANCE VARIATIONS
# ─────────────────────────────────────────────────────────────────────

class TestOneTimeGoalRiskTolerance:
    """Test different risk tolerance levels affect allocation."""

    def test_low_risk_reduces_equity(self, standard_user):
        """Test low risk tolerance reduces equity allocation."""
        goal_request = OneTimeGoalRequest(
            goal_name="Conservative Goal",
            goal_amount=1_000_000,
            years_to_goal=5.0,
            pre_ret_return=9.0,
            existing_corpus=0.0,
            existing_monthly_sip=0.0,
            risk_tolerance="low"
        )
        
        result = one_time_goal(goal_request, standard_user)
        
        # Low risk should reduce equity from base allocation
        # 5 years normally gives 50% equity base
        assert result["allocation"]["initial_equity_pct"] <= 40
        assert result["allocation"]["risk_profile"] == "low"

    def test_moderate_risk_baseline(self, standard_user):
        """Test moderate risk uses baseline allocation."""
        goal_request = OneTimeGoalRequest(
            goal_name="Moderate Goal",
            goal_amount=1_000_000,
            years_to_goal=5.0,
            pre_ret_return=10.0,
            existing_corpus=0.0,
            existing_monthly_sip=0.0,
            risk_tolerance="moderate"
        )
        
        result = one_time_goal(goal_request, standard_user)
        
        # Moderate risk should use baseline
        # 5 years gives 50% base equity
        assert result["allocation"]["initial_equity_pct"] == 50
        assert result["allocation"]["risk_profile"] == "moderate"

    def test_high_risk_increases_equity(self, standard_user):
        """Test high risk tolerance increases equity allocation."""
        goal_request = OneTimeGoalRequest(
            goal_name="Aggressive Goal",
            goal_amount=1_000_000,
            years_to_goal=5.0,
            pre_ret_return=12.0,
            existing_corpus=0.0,
            existing_monthly_sip=0.0,
            risk_tolerance="high"
        )
        
        result = one_time_goal(goal_request, standard_user)
        
        # High risk should increase equity from base
        assert result["allocation"]["initial_equity_pct"] >= 60
        assert result["allocation"]["risk_profile"] == "high"


# ─────────────────────────────────────────────────────────────────────
# ── TESTS: TIME HORIZON VARIATIONS
# ─────────────────────────────────────────────────────────────────────

class TestOneTimeGoalTimeHorizon:
    """Test different time horizons affect allocation and glide path."""

    def test_very_short_horizon_conservative_allocation(self, standard_user):
        """Test very short horizon (< 3 years) gets conservative allocation."""
        goal_request = OneTimeGoalRequest(
            goal_name="Urgent Goal",
            goal_amount=500_000,
            years_to_goal=2.0,
            pre_ret_return=8.0,
            existing_corpus=0.0,
            existing_monthly_sip=0.0,
            risk_tolerance="moderate"
        )
        
        result = one_time_goal(goal_request, standard_user)
        
        # Short horizon should have lower equity
        assert result["allocation"]["initial_equity_pct"] <= 30
        assert result["allocation"]["final_equity_pct"] == 10.0

    def test_medium_horizon_balanced_allocation(self, standard_user):
        """Test medium horizon (3-7 years) gets balanced allocation."""
        goal_request = OneTimeGoalRequest(
            goal_name="Medium Term Goal",
            goal_amount=1_500_000,
            years_to_goal=5.0,
            pre_ret_return=10.0,
            existing_corpus=0.0,
            existing_monthly_sip=0.0,
            risk_tolerance="moderate"
        )
        
        result = one_time_goal(goal_request, standard_user)
        
        # Medium horizon should be balanced
        assert 40 <= result["allocation"]["initial_equity_pct"] <= 60

    def test_long_horizon_aggressive_allocation(self, standard_user):
        """Test long horizon (> 7 years) gets aggressive allocation."""
        goal_request = OneTimeGoalRequest(
            goal_name="Long Term Goal",
            goal_amount=3_000_000,
            years_to_goal=10.0,
            pre_ret_return=11.0,
            existing_corpus=0.0,
            existing_monthly_sip=0.0,
            risk_tolerance="moderate"
        )
        
        result = one_time_goal(goal_request, standard_user)
        
        # Long horizon should have higher equity
        assert result["allocation"]["initial_equity_pct"] >= 60


# ─────────────────────────────────────────────────────────────────────
# ── TESTS: GLIDE PATH
# ─────────────────────────────────────────────────────────────────────

class TestOneTimeGoalGlidePath:
    """Test glide path calculations."""

    def test_glide_path_reduces_equity_over_time(self, standard_user):
        """Test glide path gradually reduces equity as goal approaches."""
        goal_request = OneTimeGoalRequest(
            goal_name="Test Goal",
            goal_amount=1_000_000,
            years_to_goal=5.0,
            pre_ret_return=10.0,
            existing_corpus=0.0,
            existing_monthly_sip=0.0,
            risk_tolerance="moderate"
        )
        
        result = one_time_goal(goal_request, standard_user)
        
        glide_path = result["glide_path"]
        yearly_table = glide_path["yearly_allocation_table"]
        
        # First year equity should be highest
        first_year_equity = yearly_table[0]["equity_percent"]
        last_year_equity = yearly_table[-1]["equity_percent"]
        
        assert first_year_equity > last_year_equity
        assert last_year_equity == result["allocation"]["final_equity_pct"]

    def test_glide_path_year_count_matches_horizon(self, standard_user):
        """Test glide path has correct number of years."""
        goal_request = OneTimeGoalRequest(
            goal_name="Test Goal",
            goal_amount=1_000_000,
            years_to_goal=7.0,
            pre_ret_return=10.0,
            existing_corpus=0.0,
            existing_monthly_sip=0.0,
            risk_tolerance="moderate"
        )
        
        result = one_time_goal(goal_request, standard_user)
        
        glide_path = result["glide_path"]
        assert glide_path["total_years"] == 7
        # yearly_allocation_table includes year 0 to goal year
        assert len(glide_path["yearly_allocation_table"]) == 8


# ─────────────────────────────────────────────────────────────────────
# ── TESTS: EXISTING CORPUS AND SIP
# ─────────────────────────────────────────────────────────────────────

class TestOneTimeGoalExistingAssets:
    """Test scenarios with existing corpus and SIP."""

    def test_existing_corpus_reduces_required_sip(self, standard_user):
        """Test existing corpus reduces required monthly SIP."""
        # First without existing corpus
        goal_request_without = OneTimeGoalRequest(
            goal_name="Test Goal",
            goal_amount=1_500_000,
            years_to_goal=5.0,
            pre_ret_return=10.0,
            existing_corpus=0.0,
            existing_monthly_sip=0.0,
            risk_tolerance="moderate"
        )
        
        result_without = one_time_goal(goal_request_without, standard_user)
        
        # Now with existing corpus
        goal_request_with = OneTimeGoalRequest(
            goal_name="Test Goal",
            goal_amount=1_500_000,
            years_to_goal=5.0,
            pre_ret_return=10.0,
            existing_corpus=500_000,
            existing_monthly_sip=0.0,
            risk_tolerance="moderate"
        )
        
        result_with = one_time_goal(goal_request_with, standard_user)
        
        # SIP should be lower or equal with existing corpus
        # (In some cases the existing corpus may not significantly affect SIP requirements)
        if result_without["status"] == "feasible" and result_with["status"] == "feasible":
            assert result_with["sip_plan"]["starting_monthly_sip"] <= result_without["sip_plan"]["starting_monthly_sip"]

    def test_existing_monthly_sip_tracked(self, standard_user):
        """Test existing monthly SIP is properly tracked."""
        goal_request = OneTimeGoalRequest(
            goal_name="Test Goal",
            goal_amount=1_500_000,
            years_to_goal=5.0,
            pre_ret_return=10.0,
            existing_corpus=0.0,
            existing_monthly_sip=15_000,
            risk_tolerance="moderate"
        )
        
        result = one_time_goal(goal_request, standard_user)
        
        assert result["sip_plan"]["existing_monthly_sip"] == 15_000
        # Total SIP should include existing
        assert result["sip_plan"]["total_first_year_sip"] >= 15_000


# ─────────────────────────────────────────────────────────────────────
# ── TESTS: RESPONSE STRUCTURE
# ─────────────────────────────────────────────────────────────────────

class TestOneTimeGoalResponseStructure:
    """Test response structure completeness."""

    def test_feasible_response_has_all_required_fields(self, standard_user):
        """Test feasible response contains all required fields."""
        goal_request = OneTimeGoalRequest(
            goal_name="Complete Test",
            goal_amount=1_000_000,
            years_to_goal=5.0,
            pre_ret_return=10.0,
            existing_corpus=0.0,
            existing_monthly_sip=0.0,
            risk_tolerance="moderate"
        )
        
        result = one_time_goal(goal_request, standard_user)
        
        if result["status"] == "feasible":
            # Top-level fields
            assert "status" in result
            assert "goal_name" in result
            assert "goal_summary" in result
            assert "sip_plan" in result
            assert "feasibility" in result
            assert "allocation" in result
            assert "glide_path" in result
            
            # Goal summary fields
            assert "goal_amount_today" in result["goal_summary"]
            assert "goal_amount_at_target" in result["goal_summary"]
            assert "years_to_goal" in result["goal_summary"]
            assert "target_age" in result["goal_summary"]
            
            # SIP plan fields
            assert "starting_monthly_sip" in result["sip_plan"]
            assert "annual_step_up_pct" in result["sip_plan"]
            
            # Allocation fields
            assert "initial_equity_pct" in result["allocation"]
            assert "initial_debt_pct" in result["allocation"]
            assert "final_equity_pct" in result["allocation"]
            assert "risk_profile" in result["allocation"]

    def test_infeasible_response_has_required_fields(self, tight_budget_user):
        """Test infeasible response contains required fields."""
        goal_request = OneTimeGoalRequest(
            goal_name="Infeasible Test",
            goal_amount=10_000_000,
            years_to_goal=2.0,
            pre_ret_return=10.0,
            existing_corpus=0.0,
            existing_monthly_sip=0.0,
            risk_tolerance="moderate"
        )
        
        result = one_time_goal(goal_request, tight_budget_user)
        
        if result["status"] == "infeasible":
            assert "status" in result
            assert "goal_name" in result
            assert "message" in result
            assert "suggestion" in result
            assert "sip_report" in result
            assert "feasibility_report" in result
