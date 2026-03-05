"""
Integration tests for one-time goal planner API endpoint.
Tests the /goals/one_time_goal endpoint with various scenarios.
"""

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
    """Create a standard test user with healthy financial profile."""
    user = User(
        id=str(uuid.uuid4()),
        email=f"test_{uuid.uuid4().hex[:8]}@example.com",
        phone_number=f"919{uuid.uuid4().hex[:9]}",
        hashed_password=hash_password("testpassword123"),
        full_name="Test User",
        age=25,
        marital_status="Single",
        current_income=2_400_000,  # 2L monthly
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
def high_income_test_user(test_db):
    """Create a high income test user."""
    user = User(
        id=str(uuid.uuid4()),
        email=f"highincome_{uuid.uuid4().hex[:8]}@example.com",
        phone_number=f"918{uuid.uuid4().hex[:9]}",
        hashed_password=hash_password("testpassword123"),
        full_name="High Income User",
        age=30,
        marital_status="Single",
        current_income=12_000_000,  # 10L monthly
        income_raise_pct=10.0,
        current_monthly_expenses=200_000,
        inflation_rate=6.0,
        pre_retirement_return=11.0,
        post_retirement_return=8.0,
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
# ── TESTS: SUCCESSFUL SCENARIOS
# ─────────────────────────────────────────────────────────────────────

class TestOneTimeGoalEndpointSuccess:
    """Test successful one-time goal creation scenarios."""

    def test_create_car_goal_feasible(self, auth_token):
        """Test creating a feasible car purchase goal."""
        payload = {
            "goal_name": "Buy a Car",
            "goal_amount": 1_500_000,
            "years_to_goal": 3.0,
            "pre_ret_return": 10.0,
            "existing_corpus": 0.0,
            "existing_monthly_sip": 0.0,
            "risk_tolerance": "moderate"
        }
        
        response = client.post(
            "/goals/one_time_goal",
            data=payload,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        result = response.json()
        
        assert result["status"] == "feasible"
        assert result["goal_name"] == "Buy a Car"
        assert result["goal_summary"]["goal_amount_today"] == 1_500_000
        assert "sip_plan" in result
        assert "feasibility" in result
        assert "allocation" in result
        assert "glide_path" in result

    def test_create_house_goal_with_existing_savings(self, auth_token):
        """Test creating house down payment goal with existing savings."""
        payload = {
            "goal_name": "House Down Payment",
            "goal_amount": 3_000_000,
            "years_to_goal": 5.0,
            "pre_ret_return": 11.0,
            "existing_corpus": 500_000,
            "existing_monthly_sip": 10_000,
            "risk_tolerance": "high"
        }
        
        response = client.post(
            "/goals/one_time_goal",
            data=payload,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        result = response.json()
        
        assert result["sip_plan"]["existing_corpus"] == 500_000
        assert result["sip_plan"]["existing_monthly_sip"] == 10_000
        assert result["allocation"]["risk_profile"] == "high"

    def test_create_education_goal_long_term(self, auth_token):
        """Test creating long-term education goal."""
        payload = {
            "goal_name": "Child's Education",
            "goal_amount": 2_500_000,
            "years_to_goal": 10.0,
            "pre_ret_return": 12.0,
            "existing_corpus": 0.0,
            "existing_monthly_sip": 0.0,
            "risk_tolerance": "moderate"
        }
        
        response = client.post(
            "/goals/one_time_goal",
            data=payload,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        result = response.json()
        
        assert result["goal_summary"]["years_to_goal"] == 10.0
        # Long horizon should have equity-heavy allocation
        assert result["allocation"]["initial_equity_pct"] >= 60


# ─────────────────────────────────────────────────────────────────────
# ── TESTS: RISK TOLERANCE
# ─────────────────────────────────────────────────────────────────────

class TestOneTimeGoalRiskTolerance:
    """Test different risk tolerance levels."""

    def test_low_risk_conservative_allocation(self, auth_token):
        """Test low risk tolerance gets conservative allocation."""
        payload = {
            "goal_name": "Conservative Goal",
            "goal_amount": 1_000_000,
            "years_to_goal": 5.0,
            "pre_ret_return": 9.0,
            "existing_corpus": 0.0,
            "existing_monthly_sip": 0.0,
            "risk_tolerance": "low"
        }
        
        response = client.post(
            "/goals/one_time_goal",
            data=payload,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        result = response.json()
        
        assert result["allocation"]["risk_profile"] == "low"
        # Low risk should have reduced equity
        assert result["allocation"]["initial_equity_pct"] <= 40

    def test_high_risk_aggressive_allocation(self, auth_token):
        """Test high risk tolerance gets aggressive allocation."""
        payload = {
            "goal_name": "Aggressive Goal",
            "goal_amount": 1_000_000,
            "years_to_goal": 5.0,
            "pre_ret_return": 12.0,
            "existing_corpus": 0.0,
            "existing_monthly_sip": 0.0,
            "risk_tolerance": "high"
        }
        
        response = client.post(
            "/goals/one_time_goal",
            data=payload,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        result = response.json()
        
        assert result["allocation"]["risk_profile"] == "high"
        # High risk should have increased equity
        assert result["allocation"]["initial_equity_pct"] >= 60


# ─────────────────────────────────────────────────────────────────────
# ── TESTS: VALIDATION AND ERROR HANDLING
# ─────────────────────────────────────────────────────────────────────

class TestOneTimeGoalValidation:
    """Test input validation and error scenarios."""

    def test_without_authentication_fails(self):
        """Test endpoint requires authentication."""
        payload = {
            "goal_name": "Test Goal",
            "goal_amount": 1_000_000,
            "years_to_goal": 5.0,
            "pre_ret_return": 10.0,
            "existing_corpus": 0.0,
            "existing_monthly_sip": 0.0,
            "risk_tolerance": "moderate"
        }
        
        response = client.post("/goals/one_time_goal", data=payload)
        
        assert response.status_code == 401

    def test_negative_goal_amount_fails(self, auth_token):
        """Test negative goal amount is rejected."""
        payload = {
            "goal_name": "Invalid Goal",
            "goal_amount": -1_000_000,
            "years_to_goal": 5.0,
            "pre_ret_return": 10.0,
            "existing_corpus": 0.0,
            "existing_monthly_sip": 0.0,
            "risk_tolerance": "moderate"
        }
        
        response = client.post(
            "/goals/one_time_goal",
            data=payload,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 422  # Validation error

    def test_zero_years_to_goal_fails(self, auth_token):
        """Test zero years to goal is rejected."""
        payload = {
            "goal_name": "Invalid Goal",
            "goal_amount": 1_000_000,
            "years_to_goal": 0.0,
            "pre_ret_return": 10.0,
            "existing_corpus": 0.0,
            "existing_monthly_sip": 0.0,
            "risk_tolerance": "moderate"
        }
        
        response = client.post(
            "/goals/one_time_goal",
            data=payload,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 422

    def test_excessive_years_to_goal_fails(self, auth_token):
        """Test excessively long timeline is rejected."""
        payload = {
            "goal_name": "Invalid Goal",
            "goal_amount": 1_000_000,
            "years_to_goal": 100.0,
            "pre_ret_return": 10.0,
            "existing_corpus": 0.0,
            "existing_monthly_sip": 0.0,
            "risk_tolerance": "moderate"
        }
        
        response = client.post(
            "/goals/one_time_goal",
            data=payload,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 422


# ─────────────────────────────────────────────────────────────────────
# ── TESTS: INFEASIBLE SCENARIOS
# ─────────────────────────────────────────────────────────────────────

class TestOneTimeGoalInfeasible:
    """Test infeasible goal scenarios."""

    def test_unrealistic_goal_returns_infeasible(self, auth_token):
        """Test unrealistic goal returns infeasible status."""
        payload = {
            "goal_name": "Unrealistic Goal",
            "goal_amount": 50_000_000,  # 5 crores
            "years_to_goal": 1.0,
            "pre_ret_return": 10.0,
            "existing_corpus": 0.0,
            "existing_monthly_sip": 0.0,
            "risk_tolerance": "moderate"
        }
        
        response = client.post(
            "/goals/one_time_goal",
            data=payload,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        result = response.json()
        
        # Should return infeasible with helpful message
        assert result["status"] == "infeasible"
        assert "message" in result
        assert "suggestion" in result


# ─────────────────────────────────────────────────────────────────────
# ── TESTS: RESPONSE STRUCTURE
# ─────────────────────────────────────────────────────────────────────

class TestOneTimeGoalResponseStructure:
    """Test API response structure."""

    def test_feasible_response_structure_complete(self, auth_token):
        """Test feasible response has complete structure."""
        payload = {
            "goal_name": "Test Goal",
            "goal_amount": 1_500_000,
            "years_to_goal": 5.0,
            "pre_ret_return": 10.0,
            "existing_corpus": 0.0,
            "existing_monthly_sip": 0.0,
            "risk_tolerance": "moderate"
        }
        
        response = client.post(
            "/goals/one_time_goal",
            data=payload,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        result = response.json()
        
        # Verify all major sections exist
        required_keys = [
            "status", "goal_name", "goal_summary", 
            "sip_plan", "feasibility", "allocation", "glide_path"
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

    def test_goal_summary_has_required_fields(self, auth_token):
        """Test goal_summary contains all required fields."""
        payload = {
            "goal_name": "Test Goal",
            "goal_amount": 1_000_000,
            "years_to_goal": 5.0,
            "pre_ret_return": 10.0,
            "existing_corpus": 0.0,
            "existing_monthly_sip": 0.0,
            "risk_tolerance": "moderate"
        }
        
        response = client.post(
            "/goals/one_time_goal",
            data=payload,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        result = response.json()
        
        goal_summary = result["goal_summary"]
        required_fields = [
            "goal_amount_today", "goal_amount_at_target",
            "years_to_goal", "target_age", "expected_return_pct"
        ]
        for field in required_fields:
            assert field in goal_summary

    def test_glide_path_structure_correct(self, auth_token):
        """Test glide path has correct structure."""
        payload = {
            "goal_name": "Test Goal",
            "goal_amount": 1_000_000,
            "years_to_goal": 5.0,
            "pre_ret_return": 10.0,
            "existing_corpus": 0.0,
            "existing_monthly_sip": 0.0,
            "risk_tolerance": "moderate"
        }
        
        response = client.post(
            "/goals/one_time_goal",
            data=payload,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        result = response.json()
        
        glide_path = result["glide_path"]
        assert "current_age" in glide_path
        assert "goal_age" in glide_path
        assert "total_years" in glide_path
        assert "yearly_allocation_table" in glide_path
        assert isinstance(glide_path["yearly_allocation_table"], list)
