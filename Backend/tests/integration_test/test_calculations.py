import math
from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)
client_no_raise = TestClient(app, raise_server_exceptions=False)


class TestCalculationRoot:
	def test_root_endpoint(self):
		response = client.get("/calculation/")
		assert response.status_code == 200
		assert response.json() == {"Message": "Financial Calculation API root"}


class TestFutureValueGoalIntegration:
	def test_future_value_goal_happy_path(self):
		payload = {"principal": 1_000_000, "infation_rate": 6.0, "years": 10}
		response = client.post("/calculation/future_value_goal", json=payload)
		assert response.status_code == 200
		result = response.json()
		assert "future_value" in result
		assert result["future_value"] > payload["principal"]

	def test_future_value_goal_zero_years(self):
		payload = {"principal": 250_000, "infation_rate": 12.0, "years": 0}
		response = client.post("/calculation/future_value_goal", json=payload)
		assert response.status_code == 200
		assert response.json()["future_value"] == 250_000

	def test_future_value_goal_deflation(self):
		payload = {"principal": 500_000, "infation_rate": -3.0, "years": 5}
		response = client.post("/calculation/future_value_goal", json=payload)
		assert response.status_code == 200
		assert response.json()["future_value"] < 500_000

	def test_future_value_goal_fractional_years(self):
		payload = {"principal": 100_000, "infation_rate": 6.0, "years": 2.5}
		response = client.post("/calculation/future_value_goal", json=payload)
		assert response.status_code == 200
		fv = response.json()["future_value"]
		assert 100_000 < fv < 120_000


class TestBlendedReturnIntegration:
	def test_blended_return_happy_path(self):
		payload = {
			"equity_pct": 70,
			"debt_pct": 30,
			"return_equity": 12,
			"return_debt": 7,
		}
		response = client.post("/calculation/blended_return", json=payload)
		assert response.status_code == 200
		assert math.isclose(response.json()["blended_return"], 10.5, rel_tol=1e-12, abs_tol=1e-12)

	def test_blended_return_zero_weights(self):
		payload = {
			"equity_pct": 0,
			"debt_pct": 0,
			"return_equity": 15,
			"return_debt": 8,
		}
		response = client.post("/calculation/blended_return", json=payload)
		assert response.status_code == 200
		assert response.json()["blended_return"] == 0

	def test_blended_return_weights_not_100_still_computes(self):
		payload = {
			"equity_pct": 90,
			"debt_pct": 40,
			"return_equity": 10,
			"return_debt": 5,
		}
		response = client.post("/calculation/blended_return", json=payload)
		assert response.status_code == 200
		assert response.json()["blended_return"] == 11.0


class TestRequiredAnnualSavingIntegration:
	def test_required_annual_saving_form_happy_path(self):
		form_data = {
			"future_value": 10_000_000,
			"return_rate": 10,
			"years": 15,
			"current_savings": 0,
		}
		response = client.post("/calculation/required_annual_saving", data=form_data)
		assert response.status_code == 200
		result = response.json()
		assert "required_annual_saving" in result
		assert result["required_annual_saving"] > 0

	def test_required_annual_saving_zero_return_branch(self):
		form_data = {
			"future_value": 1_200_000,
			"return_rate": 0,
			"years": 12,
			"current_savings": 100_000,
		}
		response = client.post("/calculation/required_annual_saving", data=form_data)
		assert response.status_code == 200
		assert response.json()["required_annual_saving"] == 100_000

	def test_required_annual_saving_current_savings_is_ignored_by_service(self):
		base_data = {"future_value": 2_000_000, "return_rate": 8, "years": 10}
		response_a = client.post(
			"/calculation/required_annual_saving",
			data={**base_data, "current_savings": 0},
		)
		response_b = client.post(
			"/calculation/required_annual_saving",
			data={**base_data, "current_savings": 900_000},
		)
		assert response_a.status_code == 200
		assert response_b.status_code == 200
		assert response_a.json()["required_annual_saving"] == response_b.json()["required_annual_saving"]

	def test_required_annual_saving_json_payload_fails_validation(self):
		payload = {
			"future_value": 1_000_000,
			"return_rate": 10,
			"years": 10,
			"current_savings": 0,
		}
		response = client.post("/calculation/required_annual_saving", json=payload)
		assert response.status_code == 422


class TestSuggestAllocationIntegration:
	def test_suggest_allocation_short_term_low_risk(self):
		payload = {"years": 2, "risk": "low"}
		response = client.post("/calculation/suggest_allocation", json=payload)
		assert response.status_code == 200
		assert response.json() == {"equity_allocation": 0, "debt_allocation": 100}

	def test_suggest_allocation_boundary_year_3(self):
		payload = {"years": 3, "risk": "medium"}
		response = client.post("/calculation/suggest_allocation", json=payload)
		assert response.status_code == 200
		assert response.json() == {"equity_allocation": 50, "debt_allocation": 50}

	def test_suggest_allocation_boundary_year_7(self):
		payload = {"years": 7, "risk": "high"}
		response = client.post("/calculation/suggest_allocation", json=payload)
		assert response.status_code == 200
		assert response.json() == {"equity_allocation": 90, "debt_allocation": 10}

	def test_suggest_allocation_unknown_risk_behaves_like_medium(self):
		payload = {"years": 10, "risk": "moderate"}
		response = client.post("/calculation/suggest_allocation", json=payload)
		assert response.status_code == 200
		assert response.json() == {"equity_allocation": 70, "debt_allocation": 30}

	def test_suggest_allocation_case_insensitive_risk(self):
		payload = {"years": 10, "risk": "LOW"}
		response = client.post("/calculation/suggest_allocation", json=payload)
		assert response.status_code == 200
		assert response.json() == {"equity_allocation": 50, "debt_allocation": 50}


class TestCheckFeasibilityIntegration:
	def test_check_feasibility_feasible(self):
		payload = {
			"starting_monthly_sip": 30_000,
			"annual_step_up_pct": 0.94,
			"monthly_income": 200_000,
			"income_raise_pct": 7.0,
			"monthly_expenses": 50_000,
			"years_to_goal": 5,
			"existing_monthly_sip": 0.0,
			"savings_cap_pct": 50.0
		}
		response = client.post("/calculation/check_feasibility", json=payload)
		assert response.status_code == 200
		result = response.json()
		assert result["feasible"] is True
		assert result["breach_count"] == 0

	def test_check_feasibility_infeasible(self):
		payload = {
			"starting_monthly_sip": 150_000,  # Far too high
			"annual_step_up_pct": 0.94,
			"monthly_income": 200_000,
			"income_raise_pct": 7.0,
			"monthly_expenses": 50_000,
			"years_to_goal": 5,
			"existing_monthly_sip": 0.0,
			"savings_cap_pct": 50.0
		}
		response = client.post("/calculation/check_feasibility", json=payload)
		assert response.status_code == 200
		result = response.json()
		assert result["feasible"] is False
		assert result["breach_count"] > 0

	def test_check_feasibility_boundary_equal(self):
		# Disposable income = 150k (200k - 50k), 50% cap = 75k
		payload = {
			"starting_monthly_sip": 75_000,
			"annual_step_up_pct": 0.0,  # No step-up for simplicity
			"monthly_income": 200_000,
			"income_raise_pct": 7.0,
			"monthly_expenses": 50_000,
			"years_to_goal": 3,
			"existing_monthly_sip": 0.0,
			"savings_cap_pct": 50.0
		}
		response = client.post("/calculation/check_feasibility", json=payload)
		assert response.status_code == 200
		result = response.json()
		assert result["feasible"] is True


class TestCheckRebalancingIntegration:
	def test_check_rebalancing_triggers_when_deviation_above_threshold(self):
		payload = {
			"planned_alloc": {"equity": 60, "debt": 40},
			"current_alloc": {"equity": 54, "debt": 46},
			"threshold": 5,
		}
		response = client.post("/calculation/check_rebalancing", json=payload)
		assert response.status_code == 200
		result = response.json()
		assert result["needs_rebalancing"] is True
		assert result["deviations"]["equity"] == 6

	def test_check_rebalancing_not_triggered_at_exact_threshold(self):
		payload = {
			"planned_alloc": {"equity": 60, "debt": 40},
			"current_alloc": {"equity": 55, "debt": 45},
			"threshold": 5,
		}
		response = client.post("/calculation/check_rebalancing", json=payload)
		assert response.status_code == 200
		result = response.json()
		assert result["needs_rebalancing"] is False
		assert result["deviations"]["equity"] == 5

	def test_check_rebalancing_missing_asset_in_current_allocation(self):
		payload = {
			"planned_alloc": {"equity": 60, "debt": 30, "gold": 10},
			"current_alloc": {"equity": 60, "debt": 40},
			"threshold": 5,
		}
		response = client.post("/calculation/check_rebalancing", json=payload)
		assert response.status_code == 200
		result = response.json()
		assert "gold" not in result["deviations"]


class TestStartingSipIntegration:
	def test_starting_sip_happy_path(self):
		payload = {
			"goal_amount": 30_000_000,
			"pre_ret_return": 10,
			"inflation_rate": 6,
			"income_raise_pct": 8,
			"years_to_goal": 20,
		}
		response = client.post("/calculation/starting-sip", json=payload)
		assert response.status_code == 200
		sip = response.json()["starting_monthly_sip"]
		assert sip > 0

	def test_starting_sip_handles_r_equals_g_case(self):
		payload = {
			"goal_amount": 25_000_000,
			"pre_ret_return": 10,
			"inflation_rate": 5,
			"income_raise_pct": 15.5,
			"years_to_goal": 15,
		}
		response = client.post("/calculation/starting-sip", json=payload)
		assert response.status_code == 200
		sip = response.json()["starting_monthly_sip"]
		assert math.isfinite(sip)
		assert sip > 0

	def test_starting_sip_zero_years_to_goal_returns_server_error(self):
		payload = {
			"goal_amount": 10_000_000,
			"pre_ret_return": 10,
			"inflation_rate": 6,
			"income_raise_pct": 8,
			"years_to_goal": 0,
		}
		response = client_no_raise.post("/calculation/starting-sip", json=payload)
		assert response.status_code == 500


class TestGlidePathIntegration:
	def test_glide_path_happy_path_includes_goal_year(self):
		payload = {
			"current_age": 30,
			"goal_age": 40,
			"start_equity_percent": 80,
			"end_equity_percent": 50,
		}
		response = client.post("/calculation/glide-path", json=payload)
		assert response.status_code == 200
		schedule = response.json()["yearly_allocation_table"]
		assert len(schedule) == 11
		assert schedule[0]["age"] == 30
		assert schedule[-1]["age"] == 40
		assert schedule[0]["equity_percent"] == 80
		assert schedule[-1]["equity_percent"] == 50

	def test_glide_path_same_current_and_goal_age(self):
		"""Same age for current and goal should fail validation (422)."""
		payload = {
			"current_age": 40,
			"goal_age": 40,
			"start_equity_percent": 70,
			"end_equity_percent": 40,
		}
		response = client.post("/calculation/glide-path", json=payload)
		# Validation should fail because goal_age must be > current_age
		assert response.status_code == 422

	def test_glide_path_goal_age_before_current_age(self):
		"""Goal age before current age should fail validation (422)."""
		payload = {
			"current_age": 50,
			"goal_age": 40,
			"start_equity_percent": 70,
			"end_equity_percent": 30,
		}
		response = client.post("/calculation/glide-path", json=payload)
		# Validation should fail because goal_age must be > current_age
		assert response.status_code == 422


class TestDriftIntegration:
	def test_drift_large_domain_rebalance_required(self):
		payload = {
			"current_equity_value": 650_000,
			"current_debt_value": 350_000,
			"current_year_target_ratio": 0.50,
		}
		response = client.post("/calculation/drift", json=payload)
		assert response.status_code == 200
		result = response.json()
		assert result["rebalance_required"] is True
		assert result["drift"] == 0.15

	def test_drift_large_domain_below_5_percent_not_required(self):
		payload = {
			"current_equity_value": 540_000,
			"current_debt_value": 460_000,
			"current_year_target_ratio": 0.50,
		}
		response = client.post("/calculation/drift", json=payload)
		assert response.status_code == 200
		result = response.json()
		assert result["rebalance_required"] is False
		assert result["drift"] == 0.04

	def test_drift_small_domain_relative_rule_triggers(self):
		payload = {
			"current_equity_value": 260_000,
			"current_debt_value": 740_000,
			"current_year_target_ratio": 0.20,
		}
		response = client.post("/calculation/drift", json=payload)
		assert response.status_code == 200
		result = response.json()
		assert result["rebalance_required"] is True
		assert result["drift"] == 0.06

	def test_drift_empty_portfolio(self):
		payload = {
			"current_equity_value": 0,
			"current_debt_value": 0,
			"current_year_target_ratio": 0.60,
		}
		response = client.post("/calculation/drift", json=payload)
		assert response.status_code == 200
		result = response.json()
		assert result["rebalance_required"] is False
		assert result["suggested_move_amount"] == 0
		assert result["message"] == "Empty portfolio"

