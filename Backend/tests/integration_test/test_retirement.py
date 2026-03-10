
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.databse import SessionLocal, Base, engine
from app.models.db import User
from app.services.utils import hash_password
import uuid

client = TestClient(app)


# ─────────────────────────────────────────────────────────────────────
# ── FIXTURES
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def test_db():
    """Create test database session."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    yield db
    db.close()
    # Clean up after tests
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def standard_test_user(test_db):
    """Create a standard test user."""
    user = User(
        id=str(uuid.uuid4()),
        email=f"test_{uuid.uuid4().hex[:8]}@example.com",
        phone_number=f"9190000001",  # 10 digit phone
        hashed_password=hash_password("testpassword123"),
        full_name="Test User",
        age=25,
        marital_status="Single",
        current_income=2_400_000,
        income_raise_pct=7.0,
        current_monthly_expenses=50_000,
        inflation_rate=6.0,
        pre_retirement_return=10.0,
        post_retirement_return=7.0,
        is_verified=True,
        is_active=True,
        onboarding_complete=True
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def auth_token(standard_test_user):
    """Get authentication token for standard test user."""
    response = client.post(
        "/auth/login",
        data={
            "username": standard_test_user.email,
            "password": "testpassword123"
        }
    )
    assert response.status_code == 200
    return response.json()["access_token"]


# ─────────────────────────────────────────────────────────────────────
# ── SCENARIO 1: SINGLE - FEASIBLE
# ─────────────────────────────────────────────────────────────────────

class TestSingleFeasible:
    """Single person with high income and feasible retirement plan."""

    def test_single_feasible_full_response_structure(self, auth_token):
        """Verify complete response structure for feasible single retirement."""
        # Using wealthy_retirement fixture data (30 y/o, 1Cr income, very feasible)
        data = {
            "marital_status": "Single",
            "age": "30",
            "current_income": "10000000",
            "income_raise_pct": "7",
            "retirement_age": "55",
            "current_monthly_expenses": "200000",
            "post_retirement_expense_pct": "75",
            "inflation_rate": "5.5",
            "pre_retirement_return": "11.0",
            "post_retirement_return": "8.0",
            "life_expectancy": "95",
            "annual_post_retirement_income": "500000",
            "existing_corpus": "5000000",
            "existing_monthly_sip": "50000",
            "sip_raise_pct": "0",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        assert response.status_code == 200
        result = response.json()
        
        # Verify complete response structure
        assert "status" in result
        assert result["status"] == "feasible"
        assert "corpus" in result
        assert "feasibility" in result
        assert "glide_path" in result
        assert "buckets" in result

    def test_single_feasible_corpus_details(self, auth_token):
        """Verify corpus calculation for feasible single scenario."""
        # Using wealthy_retirement fixture data
        data = {
            "marital_status": "Single",
            "age": "30",
            "current_income": "10000000",
            "income_raise_pct": "7",
            "retirement_age": "55",
            "current_monthly_expenses": "200000",
            "post_retirement_expense_pct": "75",
            "inflation_rate": "5.5",
            "pre_retirement_return": "11.0",
            "post_retirement_return": "8.0",
            "life_expectancy": "95",
            "annual_post_retirement_income": "500000",
            "existing_corpus": "5000000",
            "existing_monthly_sip": "50000",
            "sip_raise_pct": "0",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        assert response.status_code == 200
        result = response.json()
        corpus = result["corpus"]
        
        # Verify corpus fields exist
        assert corpus["corpus_required"] > 0
        assert corpus["fv_existing_corpus"] > 0
        assert corpus["fv_existing_sip"] > 0
        # corpus_gap can be negative (no gap needed) or positive (gap exists)
        assert "corpus_gap" in corpus
        assert "additional_monthly_sip_required" in corpus

    def test_single_feasible_feasibility_boolean(self, auth_token):
        """Verify strict boolean feasibility for feasible single."""
        # Using wealthy_retirement fixture data
        data = {
            "marital_status": "Single",
            "age": "30",
            "current_income": "10000000",
            "income_raise_pct": "7",
            "retirement_age": "55",
            "current_monthly_expenses": "200000",
            "post_retirement_expense_pct": "75",
            "inflation_rate": "5.5",
            "pre_retirement_return": "11.0",
            "post_retirement_return": "8.0",
            "life_expectancy": "95",
            "annual_post_retirement_income": "500000",
            "existing_corpus": "5000000",
            "existing_monthly_sip": "50000",
            "sip_raise_pct": "0",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        assert response.status_code == 200
        result = response.json()
        
        # Feasibility must be strict boolean
        assert result["feasibility"]["feasible"] is True
        # No failure field when feasible
        assert "failure" not in result["feasibility"]

    def test_single_feasible_glide_path_structure(self, auth_token):
        """Verify glide path structure and allocation progression."""
        # Using wealthy_retirement fixture data
        data = {
            "marital_status": "Single",
            "age": "30",
            "current_income": "10000000",
            "income_raise_pct": "7",
            "retirement_age": "55",
            "current_monthly_expenses": "200000",
            "post_retirement_expense_pct": "75",
            "inflation_rate": "5.5",
            "pre_retirement_return": "11.0",
            "post_retirement_return": "8.0",
            "life_expectancy": "95",
            "annual_post_retirement_income": "500000",
            "existing_corpus": "5000000",
            "existing_monthly_sip": "50000",
            "sip_raise_pct": "0",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        assert response.status_code == 200
        result = response.json()
        glide = result["glide_path"]
        
        # Verify glide path has yearly schedule and bands
        assert "yearly_schedule" in glide
        assert "allocation_bands" in glide
        assert len(glide["yearly_schedule"]) > 0
        assert len(glide["allocation_bands"]) > 0
        
        # Equity should decrease over time
        first_equity = glide["yearly_schedule"][0]["equity_pct"]
        last_equity = glide["yearly_schedule"][-1]["equity_pct"]
        assert first_equity > last_equity

    def test_single_feasible_buckets_allocation(self, auth_token):
        """Verify bucket allocation for feasible single."""
        # Using wealthy_retirement fixture data
        data = {
            "marital_status": "Single",
            "age": "30",
            "current_income": "10000000",
            "income_raise_pct": "7",
            "retirement_age": "55",
            "current_monthly_expenses": "200000",
            "post_retirement_expense_pct": "75",
            "inflation_rate": "5.5",
            "pre_retirement_return": "11.0",
            "post_retirement_return": "8.0",
            "life_expectancy": "95",
            "annual_post_retirement_income": "500000",
            "existing_corpus": "5000000",
            "existing_monthly_sip": "50000",
            "sip_raise_pct": "0",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        assert response.status_code == 200
        result = response.json()
        buckets = result["buckets"]
        
        # Verify bucket structure
        assert "buckets" in buckets
        assert "bucket_1" in buckets["buckets"]
        assert "bucket_2" in buckets["buckets"]
        assert "bucket_3" in buckets["buckets"]
        
        # Verify bucket 1 has 0% equity
        b1 = buckets["buckets"]["bucket_1"]
        assert b1["equity_pct"] == 0.0
        assert b1["debt_pct"] == 100.0
        
        # Buckets should have positive sizes
        assert b1["size"] > 0
        assert buckets["buckets"]["bucket_2"]["size"] > 0
        assert buckets["buckets"]["bucket_3"]["size"] > 0


# ─────────────────────────────────────────────────────────────────────
# ── SCENARIO 2: SINGLE - INFEASIBLE
# ─────────────────────────────────────────────────────────────────────

class TestSingleInfeasible:
    """Single person with limited income and infeasible retirement plan."""

    def test_single_infeasible_stops_at_feasibility(self, auth_token):
        """Verify infeasible plan stops after feasibility check."""
        data = {
            "marital_status": "Single",
            "age": "45",
            "current_income": "600000",
            "income_raise_pct": "5",
            "retirement_age": "50",
            "current_monthly_expenses": "60000",
            "post_retirement_expense_pct": "90",
            "inflation_rate": "6.0",
            "pre_retirement_return": "10.0",
            "post_retirement_return": "7.0",
            "life_expectancy": "85",
            "annual_post_retirement_income": "0",
            "existing_corpus": "0",
            "existing_monthly_sip": "0",
            "sip_raise_pct": "0",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        assert response.status_code == 200
        result = response.json()
        
        # Infeasible status
        assert result["status"] == "infeasible"
        assert result["feasibility"]["feasible"] is False
        
        # No glide path or buckets for infeasible
        assert result["glide_path"] is None
        assert result["buckets"] is None
        
        # But corpus should still be computed
        assert result["corpus"] is not None

    def test_single_infeasible_failure_details(self, auth_token):
        """Verify failure details for infeasible scenario."""
        data = {
            "marital_status": "Single",
            "age": "45",
            "current_income": "600000",
            "income_raise_pct": "5",
            "retirement_age": "50",
            "current_monthly_expenses": "60000",
            "post_retirement_expense_pct": "90",
            "inflation_rate": "6.0",
            "pre_retirement_return": "10.0",
            "post_retirement_return": "7.0",
            "life_expectancy": "85",
            "annual_post_retirement_income": "0",
            "existing_corpus": "0",
            "existing_monthly_sip": "0",
            "sip_raise_pct": "0",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        assert response.status_code == 200
        result = response.json()
        
        # Infeasible with failure details
        assert result["feasibility"]["feasible"] is False
        assert "failure" in result["feasibility"]
        
        failure = result["feasibility"]["failure"]
        assert "year" in failure
        assert "age" in failure
        assert "savings_ratio_pct" in failure
        assert "message" in failure
        
        # First failure should have savings ratio > 50%
        assert failure["savings_ratio_pct"] > 50

    def test_single_infeasible_only_first_failure(self, auth_token):
        """Verify only first failure is reported (not all breaches)."""
        data = {
            "marital_status": "Single",
            "age": "45",
            "current_income": "600000",
            "income_raise_pct": "5",
            "retirement_age": "50",
            "current_monthly_expenses": "60000",
            "post_retirement_expense_pct": "90",
            "inflation_rate": "6.0",
            "pre_retirement_return": "10.0",
            "post_retirement_return": "7.0",
            "life_expectancy": "85",
            "annual_post_retirement_income": "0",
            "existing_corpus": "0",
            "existing_monthly_sip": "0",
            "sip_raise_pct": "0",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        assert response.status_code == 200
        result = response.json()
        
        # Should have exactly one failure (the first)
        assert result["feasibility"]["feasible"] is False
        failure = result["feasibility"]["failure"]
        assert isinstance(failure, dict)
        # Should not have arrays of multiple failures
        assert not isinstance(failure.get("year"), list)


# ─────────────────────────────────────────────────────────────────────
# ── SCENARIO 3: MARRIED WITH SPOUSE EARNING - FEASIBLE
# ─────────────────────────────────────────────────────────────────────

class TestMarriedBothEarningFeasible:
    """Married couple, both earning, feasible retirement."""

    def test_married_both_earning_feasible_complete_plan(self, auth_token):
        """Verify complete feasible plan for dual-income couple."""
        # Using married_retirement fixture data
        data = {
            "marital_status": "Married",
            "age": "28",
            "current_income": "3000000",
            "income_raise_pct": "8",
            "retirement_age": "50",
            "current_monthly_expenses": "50000",
            "post_retirement_expense_pct": "70",
            "inflation_rate": "6.0",
            "pre_retirement_return": "10.0",
            "post_retirement_return": "7.0",
            "life_expectancy": "90",
            "annual_post_retirement_income": "100000",
            "existing_corpus": "1000000",
            "existing_monthly_sip": "20000",
            "sip_raise_pct": "0",
            "spouse_age": "26",
            "spouse_income": "2000000",
            "spouse_income_raise_pct": "7",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        assert response.status_code == 200
        result = response.json()
        
        # Complete feasible response
        assert result["status"] == "feasible"
        assert result["feasibility"]["feasible"] is True
        assert result["corpus"] is not None
        assert result["glide_path"] is not None
        assert result["buckets"] is not None

    def test_married_both_earning_feasible_spouse_details(self, auth_token):
        """Verify spouse details are processed correctly."""
        # Using married_retirement fixture data
        data = {
            "marital_status": "Married",
            "age": "28",
            "current_income": "3000000",
            "income_raise_pct": "8",
            "retirement_age": "50",
            "current_monthly_expenses": "50000",
            "post_retirement_expense_pct": "70",
            "inflation_rate": "6.0",
            "pre_retirement_return": "10.0",
            "post_retirement_return": "7.0",
            "life_expectancy": "90",
            "annual_post_retirement_income": "100000",
            "existing_corpus": "1000000",
            "existing_monthly_sip": "20000",
            "sip_raise_pct": "0",
            "spouse_age": "26",
            "spouse_income": "2000000",
            "spouse_income_raise_pct": "7",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        assert response.status_code == 200
        result = response.json()
        
        # Should compute with dual income
        assert result["corpus"]["corpus_required"] > 0
        assert result["feasibility"]["feasible"] is True

    def test_married_both_earning_feasible_glide_path_length(self, auth_token):
        """Verify glide path length matches years to retirement."""
        # Using married_retirement fixture data
        data = {
            "marital_status": "Married",
            "age": "28",
            "current_income": "3000000",
            "income_raise_pct": "8",
            "retirement_age": "50",
            "current_monthly_expenses": "50000",
            "post_retirement_expense_pct": "70",
            "inflation_rate": "6.0",
            "pre_retirement_return": "10.0",
            "post_retirement_return": "7.0",
            "life_expectancy": "90",
            "annual_post_retirement_income": "100000",
            "existing_corpus": "1000000",
            "existing_monthly_sip": "20000",
            "sip_raise_pct": "0",
            "spouse_age": "26",
            "spouse_income": "2000000",
            "spouse_income_raise_pct": "7",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        assert response.status_code == 200
        result = response.json()
        
        years_to_retirement = 50 - 28  # 22 years
        glide_path = result["glide_path"]["yearly_schedule"]
        assert len(glide_path) == years_to_retirement


# ─────────────────────────────────────────────────────────────────────
# ── SCENARIO 4: MARRIED WITH SPOUSE EARNING - INFEASIBLE
# ─────────────────────────────────────────────────────────────────────

class TestMarriedBothEarningInfeasible:
    """Married couple, both earning, but infeasible plan."""

    def test_married_both_earning_infeasible_status(self, auth_token):
        """Verify infeasible status for dual-income couple with constraints."""
        data = {
            "marital_status": "Married",
            "age": "48",
            "current_income": "1000000",
            "income_raise_pct": "4",
            "retirement_age": "53",
            "current_monthly_expenses": "100000",
            "post_retirement_expense_pct": "95",
            "inflation_rate": "6.0",
            "pre_retirement_return": "10.0",
            "post_retirement_return": "7.0",
            "life_expectancy": "85",
            "annual_post_retirement_income": "0",
            "existing_corpus": "0",
            "existing_monthly_sip": "0",
            "sip_raise_pct": "0",
            "spouse_age": "46",
            "spouse_income": "800000",
            "spouse_income_raise_pct": "3",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        assert response.status_code == 200
        result = response.json()
        
        # Infeasible despite dual income
        assert result["status"] == "infeasible"
        assert result["feasibility"]["feasible"] is False
        assert result["glide_path"] is None
        assert result["buckets"] is None

    def test_married_both_earning_infeasible_failure_year_age(self, auth_token):
        """Verify failure capture includes year and age info."""
        data = {
            "marital_status": "Married",
            "age": "50",
            "current_income": "900000",
            "income_raise_pct": "4",
            "retirement_age": "54",
            "current_monthly_expenses": "120000",
            "post_retirement_expense_pct": "100",
            "inflation_rate": "6.0",
            "pre_retirement_return": "10.0",
            "post_retirement_return": "7.0",
            "life_expectancy": "84",
            "annual_post_retirement_income": "0",
            "existing_corpus": "0",
            "existing_monthly_sip": "0",
            "sip_raise_pct": "0",
            "spouse_age": "48",
            "spouse_income": "700000",
            "spouse_income_raise_pct": "3",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        assert response.status_code == 200
        result = response.json()
        
        failure = result["feasibility"]["failure"]
        assert failure["year"] >= 1
        assert failure["age"] >= 50  # Age at failure


# ─────────────────────────────────────────────────────────────────────
# ── SCENARIO 5: MARRIED WITH SPOUSE NOT EARNING - FEASIBLE
# ─────────────────────────────────────────────────────────────────────

class TestMarriedNonEarningSpouseFeasible:
    """Married couple, spouse not earning, feasible retirement."""

    def test_married_non_earning_feasible_zero_spouse_income(self, auth_token):
        """Verify plan handles spouse with zero income."""
        # Use 10 crore income to ensure feasibility with non-earning spouse
        data = {
            "marital_status": "Married",
            "age": "30",
            "current_income": "10000000",
            "income_raise_pct": "7",
            "retirement_age": "55",
            "current_monthly_expenses": "200000",
            "post_retirement_expense_pct": "75",
            "inflation_rate": "5.5",
            "pre_retirement_return": "11.0",
            "post_retirement_return": "8.0",
            "life_expectancy": "95",
            "annual_post_retirement_income": "500000",
            "existing_corpus": "5000000",
            "existing_monthly_sip": "50000",
            "sip_raise_pct": "0",
            "spouse_age": "28",
            "spouse_income": "0",  # Non-earning spouse
            "spouse_income_raise_pct": "0",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        assert response.status_code == 200
        result = response.json()
        
        # Should be feasible with high single income
        assert result["status"] == "feasible"
        assert result["feasibility"]["feasible"] is True
        assert result["corpus"] is not None
        assert result["glide_path"] is not None
        assert result["buckets"] is not None

    def test_married_non_earning_feasible_single_income_corpus(self, auth_token):
        """Verify corpus calculation with single household income."""
        # Use 10 crore income to ensure feasibility with non-earning spouse
        data = {
            "marital_status": "Married",
            "age": "30",
            "current_income": "10000000",
            "income_raise_pct": "7",
            "retirement_age": "55",
            "current_monthly_expenses": "200000",
            "post_retirement_expense_pct": "75",
            "inflation_rate": "5.5",
            "pre_retirement_return": "11.0",
            "post_retirement_return": "8.0",
            "life_expectancy": "95",
            "annual_post_retirement_income": "500000",
            "existing_corpus": "5000000",
            "existing_monthly_sip": "50000",
            "sip_raise_pct": "0",
            "spouse_age": "28",
            "spouse_income": "0",  # Non-earning
            "spouse_income_raise_pct": "0",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        assert response.status_code == 200
        result = response.json()
        
        # Should compute with income from primary earner only
        assert result["feasibility"]["feasible"] is True
        assert result["corpus"]["corpus_required"] > 0

    def test_married_non_earning_feasible_buckets_review_age(self, auth_token):
        """Verify buckets use retirement age, not current age."""
        # Use 10 crore income to ensure feasibility with non-earning spouse
        data = {
            "marital_status": "Married",
            "age": "30",
            "current_income": "10000000",
            "income_raise_pct": "7",
            "retirement_age": "55",
            "current_monthly_expenses": "200000",
            "post_retirement_expense_pct": "75",
            "inflation_rate": "5.5",
            "pre_retirement_return": "11.0",
            "post_retirement_return": "8.0",
            "life_expectancy": "95",
            "annual_post_retirement_income": "500000",
            "existing_corpus": "5000000",
            "existing_monthly_sip": "50000",
            "sip_raise_pct": "0",
            "spouse_age": "28",
            "spouse_income": "0",  # Non-earning
            "spouse_income_raise_pct": "0",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        assert response.status_code == 200
        result = response.json()
        
        # Buckets review age should be retirement age (55), not current (30)
        assert result["buckets"]["review_age"] == 55


# ─────────────────────────────────────────────────────────────────────
# ── SCENARIO 6: MARRIED WITH SPOUSE NOT EARNING - INFEASIBLE
# ─────────────────────────────────────────────────────────────────────

class TestMarriedNonEarningSpouseInfeasible:
    """Married couple, spouse not earning, infeasible retirement."""

    def test_married_non_earning_infeasible_single_income_constraint(self, auth_token):
        """Verify infeasibility with only primary earner and tight constraints."""
        data = {
            "marital_status": "Married",
            "age": "45",
            "current_income": "1200000",
            "income_raise_pct": "5",
            "retirement_age": "50",
            "current_monthly_expenses": "120000",
            "post_retirement_expense_pct": "95",
            "inflation_rate": "6.0",
            "pre_retirement_return": "10.0",
            "post_retirement_return": "7.0",
            "life_expectancy": "85",
            "annual_post_retirement_income": "0",
            "existing_corpus": "0",
            "existing_monthly_sip": "0",
            "sip_raise_pct": "0",
            "spouse_age": "43",
            "spouse_income": "0",
            "spouse_income_raise_pct": "0",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        assert response.status_code == 200
        result = response.json()
        
        # Infeasible with only single primary income
        assert result["status"] == "infeasible"
        assert result["feasibility"]["feasible"] is False
        assert result["glide_path"] is None

    def test_married_non_earning_infeasible_high_sip_requirement(self, auth_token):
        """Verify infeasibility when SIP exceeds 50% income cap."""
        data = {
            "marital_status": "Married",
            "age": "48",
            "current_income": "500000",
            "income_raise_pct": "3",
            "retirement_age": "52",
            "current_monthly_expenses": "80000",
            "post_retirement_expense_pct": "100",
            "inflation_rate": "6.0",
            "pre_retirement_return": "10.0",
            "post_retirement_return": "7.0",
            "life_expectancy": "82",
            "annual_post_retirement_income": "0",
            "existing_corpus": "0",
            "existing_monthly_sip": "0",
            "sip_raise_pct": "0",
            "spouse_age": "46",
            "spouse_income": "0",
            "spouse_income_raise_pct": "0",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        assert response.status_code == 200
        result = response.json()
        
        # Should be infeasible
        assert result["feasibility"]["feasible"] is False
        failure = result["feasibility"]["failure"]
        # SIP requirement should exceed 50% of annual income
        assert failure["savings_ratio_pct"] > 50


# ─────────────────────────────────────────────────────────────────────
# ── VALIDATION & ERROR CASES
# ─────────────────────────────────────────────────────────────────────

class TestRetirementValidation:
    """Test input validation and error handling."""

    def test_single_does_not_require_spouse_details(self, auth_token):
        """Single status should not require spouse info."""
        # Using wealthy_retirement data (feasible single)
        data = {
            "marital_status": "Single",
            "age": "30",
            "current_income": "10000000",
            "income_raise_pct": "7",
            "retirement_age": "55",
            "current_monthly_expenses": "200000",
            "post_retirement_expense_pct": "75",
            "inflation_rate": "5.5",
            "pre_retirement_return": "11.0",
            "post_retirement_return": "8.0",
            "life_expectancy": "95",
            "annual_post_retirement_income": "500000",
            "existing_corpus": "5000000",
            "existing_monthly_sip": "50000",
            "sip_raise_pct": "0",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        # Should succeed without spouse details
        assert response.status_code == 200
        assert response.json()["status"] == "feasible"

# ─────────────────────────────────────────────────────────────────────
# ── EDGE CASES & BOUNDARY CONDITIONS
# ─────────────────────────────────────────────────────────────────────

class TestRetirementEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_short_accumulation_window(self, auth_token):
        """Test retirement plan with only 2 years to retirement."""
        data = {
            "marital_status": "Single",
            "age": "43",
            "current_income": "3000000",
            "income_raise_pct": "8",
            "retirement_age": "45",
            "current_monthly_expenses": "80000",
            "post_retirement_expense_pct": "80",
            "inflation_rate": "6.0",
            "pre_retirement_return": "10.0",
            "post_retirement_return": "7.0",
            "life_expectancy": "85",
            "annual_post_retirement_income": "0",
            "existing_corpus": "5000000",
            "existing_monthly_sip": "50000",
            "sip_raise_pct": "0",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        assert response.status_code == 200
        result = response.json()
        # Should compute even with short window
        assert result["corpus"]["corpus_required"] > 0

    def test_very_long_retirement_window(self, auth_token):
        """Test retirement plan with 55+ years of retirement (long life)."""
        data = {
            "marital_status": "Single",
            "age": "20",
            "current_income": "2000000",
            "income_raise_pct": "8",
            "retirement_age": "45",
            "current_monthly_expenses": "40000",
            "post_retirement_expense_pct": "75",
            "inflation_rate": "6.0",
            "pre_retirement_return": "10.0",
            "post_retirement_return": "7.0",
            "life_expectancy": "100",  # 55 years of retirement
            "annual_post_retirement_income": "0",
            "existing_corpus": "0",
            "existing_monthly_sip": "5000",
            "sip_raise_pct": "0",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        assert response.status_code == 200
        result = response.json()
        # Corpus should be very large due to long retirement
        assert result["corpus"]["corpus_required"] > 5_000_000

    def test_zero_income_single(self, auth_token):
        """Test invalid case with zero income."""
        data = {
            "marital_status": "Single",
            "age": "30",
            "current_income": "0",  # Zero income
            "income_raise_pct": "8",
            "retirement_age": "55",
            "current_monthly_expenses": "50000",
            "post_retirement_expense_pct": "75",
            "inflation_rate": "6.0",
            "pre_retirement_return": "10.0",
            "post_retirement_return": "7.0",
            "life_expectancy": "90",
            "annual_post_retirement_income": "0",
            "existing_corpus": "0",
            "existing_monthly_sip": "0",
            "sip_raise_pct": "0",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        # Depends on validation rules - should handle gracefully
        assert response.status_code in [200, 422]

    def test_existing_corpus_covers_all(self, auth_token):
        """Test when existing corpus fully covers retirement needs."""
        data = {
            "marital_status": "Single",
            "age": "30",
            "current_income": "2000000",
            "income_raise_pct": "8",
            "retirement_age": "55",
            "current_monthly_expenses": "40000",
            "post_retirement_expense_pct": "75",
            "inflation_rate": "6.0",
            "pre_retirement_return": "10.0",
            "post_retirement_return": "7.0",
            "life_expectancy": "85",
            "annual_post_retirement_income": "0",
            "existing_corpus": "100000000",  # Massive corpus
            "existing_monthly_sip": "0",
            "sip_raise_pct": "0",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        assert response.status_code == 200
        result = response.json()
        # Should be feasible with large existing corpus
        assert result["status"] == "feasible"
        # Additional SIP required should be zero or minimal
        assert result["corpus"]["additional_monthly_sip_required"] == 0

    def test_high_passive_income(self, auth_token):
        """Test retirement with substantial post-retirement income."""
        data = {
            "marital_status": "Single",
            "age": "30",
            "current_income": "2500000",
            "income_raise_pct": "8",
            "retirement_age": "55",
            "current_monthly_expenses": "60000",
            "post_retirement_expense_pct": "80",
            "inflation_rate": "6.0",
            "pre_retirement_return": "10.0",
            "post_retirement_return": "7.0",
            "life_expectancy": "90",
            "annual_post_retirement_income": "1000000",  # High passive income
            "existing_corpus": "500000",
            "existing_monthly_sip": "10000",
            "sip_raise_pct": "0",
        }
        response = client.post("/goals/retirement", data=data, headers={"Authorization": f"Bearer {auth_token}"})
        
        assert response.status_code == 200
        result = response.json()
        # Should significantly reduce corpus requirement
        assert result["status"] == "feasible"


