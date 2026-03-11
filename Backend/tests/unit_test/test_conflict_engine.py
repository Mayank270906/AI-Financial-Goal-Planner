from app.schemas.calculation import ConflictEngineRequest
from app.services.math.conflict_engine import compute_conflict_engine, compute_max_horizon


class TestComputeMaxHorizon:
    def test_returns_zero_when_no_active_goals(self):
        data = ConflictEngineRequest(
            retirement_plan=None,
            onetime_goals=[],
            recurring_goals=[],
            monthly_income=200_000,
            monthly_expenses=50_000,
            income_raise_pct=7.0,
            priority_order=["retirement"],
            savings_pct=20.0,
            buffer_pct=10.0,
        )

        assert compute_max_horizon(data) == 0

    def test_uses_fresh_onetime_goal_duration_as_fallback(self):
        data = ConflictEngineRequest(
            retirement_plan=None,
            onetime_goals=[{
                "status": "feasible",
                "goal_name": "Fresh Goal",
                "time_horizon_years": 4,
                "sip_plan": {
                    "starting_monthly_sip": 5_000,
                    "existing_monthly_sip": 0.0,
                },
            }],
            recurring_goals=[],
            monthly_income=200_000,
            monthly_expenses=50_000,
            income_raise_pct=7.0,
            priority_order=["retirement", "fresh-goal"],
            savings_pct=20.0,
            buffer_pct=10.0,
        )

        assert compute_max_horizon(data) == 4


class TestComputeConflictEngine:
    def test_handles_empty_horizon_without_crashing(self):
        data = ConflictEngineRequest(
            retirement_plan={"status": "infeasible", "glide_path": None},
            onetime_goals=[],
            recurring_goals=[],
            monthly_income=200_000,
            monthly_expenses=50_000,
            income_raise_pct=7.0,
            priority_order=["retirement"],
            savings_pct=20.0,
            buffer_pct=10.0,
        )

        result = compute_conflict_engine(data)

        assert result["overall_status"] == "all_clear"
        assert result["yearly_summary"] == []
        assert result["recommendations"][0]["message"] == "No active goals found. Add one-time or recurring goals to run conflict analysis."