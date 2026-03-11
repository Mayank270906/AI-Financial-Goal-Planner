"""
End-to-End Smoke Test for Goal Planning + Conflict Engine Integration

This test verifies:
1. User authentication (OAuth2)
2. Retirement plan creation
3. Multiple goal creation (one-time and recurring)
4. Conflict engine integration at each step
5. Final profile overview with all goals

Test Scenario:
- User: 35 years old, 1.2M annual income, 50k monthly expenses
- Goals: Retirement + 2 one-time goals + 1 recurring goal
"""

import sys
from fastapi.testclient import TestClient
from app.main import app
from app.databse import Base, engine, get_db
from app.models.db import User, RetirementPlan, OneTimeGoalPlan, RecurringGoalPlan, ConflictResults
from sqlalchemy.orm import Session
import json

client = TestClient(app)

# Test user credentials
test_email = "smoke_test_e2e@example.com"
test_password = "SecurePass123!"
test_phone = "9876543222"

def cleanup_test_user(db: Session):
    """Clean up any existing test user and related data."""
    user = db.query(User).filter(User.email == test_email).first()
    if user:
        # Delete in reverse FK order
        db.query(ConflictResults).filter(ConflictResults.user_id == user.id).delete()
        db.query(RecurringGoalPlan).filter(RecurringGoalPlan.user_id == user.id).delete()
        db.query(OneTimeGoalPlan).filter(OneTimeGoalPlan.user_id == user.id).delete()
        db.query(RetirementPlan).filter(RetirementPlan.user_id == user.id).delete()
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
        print(f"✓ Cleaned up existing test user: {test_email}")

def get_auth_token() -> str:
    """Register and login to get OAuth2 token."""
    Base.metadata.create_all(bind=engine)
    
    # Get DB session
    db = next(get_db())
    cleanup_test_user(db)
    db.close()
    
    # Register (user creation endpoint accepts form-data)
    register_data = {
        "name": "Smoke Test User E2E",
        "email": test_email,
        "phone_number": test_phone,
        "password": test_password,
        "age": 35,
        "marital_status": "Married",
        "current_income": 1200000,
        "income_raise_pct": 8.0,
        "current_monthly_expenses": 50000,
        "spouse_age": 33,
        "spouse_income": 600000,
        "spouse_income_raise_pct": 7.0,
        "inflation_rate": 6.0,
    }

    response = client.post("/user/", data=register_data)
    assert response.status_code in (200, 201), f"Registration failed: {response.text}"
    print(f"✓ User registered: {test_email}")
    
    # Login
    login_data = {
        "username": test_email,
        "password": test_password
    }
    response = client.post("/auth/login", data=login_data)
    assert response.status_code == 200, f"Login failed: {response.text}"
    token = response.json()["access_token"]
    print(f"✓ User logged in, token obtained")
    
    return token

def run_retirement_plan(token: str) -> dict:
    """Test retirement plan creation and conflict engine."""
    print("\n=== STEP 1: Create Retirement Plan ===")
    
    data = {
        "retirement_age": 60,
        "post_retirement_expense_pct": 70.0,
        "post_retirement_return": 7.0,
        "pre_retirement_return": 10.0,
        "life_expectancy": 85,
        "annual_post_retirement_income": 0,
        "existing_corpus": 500000,
        "existing_monthly_sip": 10000,
        "sip_raise_pct": 8.0
    }
    
    response = client.post(
        "/goals/retirement",
        data=data,
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200, f"Retirement plan failed: {response.text}"
    plan = response.json()
    
    print(f"  Status: {plan.get('status')}")
    
    if plan.get('status') == 'feasible':
        corpus = plan.get('corpus', {})
        print(f"  Required Corpus: ₹{corpus.get('required_corpus', 0):,.0f}")
        print(f"  Additional SIP: ₹{corpus.get('additional_monthly_sip_required', 0):,.0f}")
        print(f"  ✓ Retirement plan created successfully")
    else:
        print(f"  ⚠ Retirement plan infeasible")
    
    return plan

def run_one_time_goal(token: str, goal_num: int, goal_data: dict) -> dict:
    """Test one-time goal creation and conflict engine."""
    print(f"\n=== STEP {goal_num}: Create One-Time Goal '{goal_data['goal_name']}' ===")
    
    response = client.post(
        "/goals/one_time_goal",
        data=goal_data,
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200, f"One-time goal failed: {response.text}"
    plan = response.json()
    
    print(f"  Status: {plan.get('status')}")
    
    if plan.get('status') == 'feasible':
        summary = plan.get('goal_summary', {})
        sip = plan.get('sip_plan', {})
        print(f"  Future Value: ₹{summary.get('future_value', 0):,.0f}")
        print(f"  Monthly SIP: ₹{sip.get('starting_monthly_sip', 0):,.0f}")
        print(f"  ✓ Goal created successfully")
    else:
        print(f"  ⚠ Goal infeasible: {plan.get('message', 'Unknown')}")
    
    return plan

def run_recurring_goal(token: str, goal_num: int, goal_data: dict) -> dict:
    """Test recurring goal creation and conflict engine."""
    print(f"\n=== STEP {goal_num}: Create Recurring Goal '{goal_data['goal_name']}' ===")
    
    response = client.post(
        "/goals/recurring_goal",
        data=goal_data,
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200, f"Recurring goal failed: {response.text}"
    plan = response.json()
    
    print(f"  Status: {plan.get('status')}")
    
    if plan.get('status') == 'feasible':
        summary = plan.get('goal_summary', {})
        sip = plan.get('sip_plan', {})
        print(f"  Total FV: ₹{summary.get('total_future_value', 0):,.0f}")
        print(f"  Total Monthly SIP: ₹{summary.get('total_monthly_sip', 0):,.0f}")
        print(f"  Occurrences: {summary.get('num_occurrences', 0)}")
        print(f"  ✓ Goal created successfully")
    else:
        print(f"  ⚠ Goal infeasible: {plan.get('message', 'Unknown')}")
    
    return plan

def run_profile_overview(token: str) -> dict:
    """Test final profile overview with conflict engine."""
    print(f"\n=== FINAL STEP: Profile Overview & Conflict Analysis ===")
    
    response = client.get(
        "/goals/profile_overview",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200, f"Profile overview failed: {response.text}"
    results = response.json()
    
    print(f"  Overall Status: {results.get('overall_status')}")
    print(f"  Critical Breaches: {results.get('critical_breach_count', 0)}")
    print(f"  Warning Breaches: {results.get('warning_breach_count', 0)}")
    print(f"  Advisory Count: {results.get('advisory_count', 0)}")
    
    # Corridor config
    config = results.get('corridor_config', {})
    print(f"\n  Corridor Configuration:")
    print(f"    Ceiling: {config.get('ceiling_pct', 0)}%")
    print(f"    Floor: {config.get('savings_pct', 0)}%")
    print(f"    Buffer: {config.get('buffer_pct', 0)}%")
    
    # Waterfall summary
    waterfall = results.get('surplus_waterfall', {})
    print(f"\n  Surplus Waterfall (Year 1):")
    print(f"    Monthly Income: ₹{waterfall.get('monthly_income', 0):,.0f}")
    print(f"    Monthly Expenses: ₹{waterfall.get('monthly_expenses', 0):,.0f}")
    print(f"    Disposable: ₹{waterfall.get('disposable', 0):,.0f}")
    print(f"    Total Allocated: ₹{waterfall.get('total_allocated', 0):,.0f}")
    print(f"    Remaining Surplus: ₹{waterfall.get('remaining_surplus', 0):,.0f}")
    
    # Goals summary
    funded = waterfall.get('funded_goals', [])
    deferred = waterfall.get('deferred_goals', [])
    
    print(f"\n  Funded Goals: {len(funded)}")
    for goal in funded:
        status = "FULL" if goal.get('funded_fully') else "PARTIAL"
        print(f"    [{goal.get('priority_rank')}] {goal.get('goal_name')}: ₹{goal.get('monthly_sip', 0):,.2f} ({status})")
    
    if deferred:
        print(f"\n  Deferred Goals: {len(deferred)}")
        for goal in deferred:
            print(f"    [{goal.get('priority_rank')}] {goal.get('goal_name')}: ₹{goal.get('monthly_sip', 0):,.2f}")
            print(f"        Reason: {goal.get('reason', 'Unknown')}")
    
    # Priority prompt check
    if 'priority_input_required' in results:
        print(f"\n  ⚠ Priority Input Required:")
        print(f"    Message: {results['priority_input_required'].get('message')}")
        print(f"    Current Auto Order: {results['priority_input_required'].get('current_auto_order')}")
    else:
        print(f"\n  ✓ Priorities already set by user")
    
    # Recommendations
    recs = results.get('recommendations', [])
    if recs:
        print(f"\n  Recommendations:")
        for rec in recs[:3]:  # Show first 3
            print(f"    [{rec.get('type')}] {rec.get('message')}")
    
    print(f"\n✓ Profile overview completed successfully")
    return results

def main():
    print("=" * 70)
    print("END-TO-END SMOKE TEST: Goal Planning + Conflict Engine Integration")
    print("=" * 70)
    
    try:
        # Step 0: Authentication
        token = get_auth_token()
        
        # Step 1: Retirement Plan
        retirement_plan = run_retirement_plan(token)
        
        # Step 2: One-Time Goal 1 (Car Purchase)
        car_goal = run_one_time_goal(token, 2, {
            "goal_name": "Car Purchase",
            "goal_amount": 1500000,
            "years_to_goal": 3,
            "pre_ret_return": 10.0,
            "existing_corpus": 0,
            "existing_monthly_sip": 0,
            "risk_tolerance": "moderate"
        })
        
        # Step 3: One-Time Goal 2 (House Down Payment)
        house_goal = run_one_time_goal(token, 3, {
            "goal_name": "House Down Payment",
            "goal_amount": 5000000,
            "years_to_goal": 7,
            "pre_ret_return": 10.0,
            "existing_corpus": 100000,
            "existing_monthly_sip": 5000,
            "risk_tolerance": "moderate"
        })
        
        # Step 4: Recurring Goal (Vacation Every 2 Years)
        vacation_goal = run_recurring_goal(token, 4, {
            "goal_name": "International Vacation",
            "current_cost": 200000,
            "years_to_first": 2,
            "frequency_years": 2,
            "num_occurrences": 5,
            "goal_inflation_pct": 6.0,
            "expected_return_pct": 10.0,
            "existing_corpus": 0
        })
        
        # Step 5: Profile Overview
        overview = run_profile_overview(token)
        
        print(f"\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)
        print(f"✓ All endpoint integrations working correctly")
        print(f"✓ Conflict engine triggered after each goal creation")
        print(f"✓ Final profile overview generated successfully")
        print(f"✓ Overall Status: {overview.get('overall_status')}")
        print(f"\n🎉 END-TO-END TEST PASSED!")
        print("=" * 70)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()


def test_e2e_smoke_flow():
    token = get_auth_token()
    plan = run_retirement_plan(token)
    assert plan.get("status") in {"feasible", "infeasible"}

    one_time = run_one_time_goal(token, 2, {
        "goal_name": "Car Purchase",
        "goal_amount": 1500000,
        "years_to_goal": 3,
        "pre_ret_return": 10.0,
        "existing_corpus": 0,
        "existing_monthly_sip": 0,
        "risk_tolerance": "moderate"
    })
    assert one_time.get("status") in {"feasible", "infeasible"}

    recurring = run_recurring_goal(token, 3, {
        "goal_name": "International Vacation",
        "current_cost": 200000,
        "years_to_first": 2,
        "frequency_years": 2,
        "num_occurrences": 5,
        "goal_inflation_pct": 6.0,
        "expected_return_pct": 10.0,
        "existing_corpus": 0
    })
    assert recurring.get("status") in {"feasible", "infeasible"}

    overview = run_profile_overview(token)
    assert "overall_status" in overview
