import json
from sqlalchemy.orm import Session
from app.models.db import (
    ConflictResults,
    OneTimeGoalPlan,
    RecurringGoalPlan,
    RetirementPlan,
    User,
)
from app.schemas.calculation import ConflictEngineRequest, FutureValue
from app.services.math.calculation import future_value_goal
from app.utils.log_format import JSONFormatter
from datetime import datetime
import logging

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger = logging.getLogger("conflict_engine")
logger.addHandler(handler)
logger.setLevel(logging.INFO)


def _coerce_positive_int(value) -> int | None:
    try:
        coerced = int(float(value))
    except (TypeError, ValueError):
        return None
    return coerced if coerced > 0 else None


def _extract_retirement_horizon(retirement_plan: dict | None) -> int | None:
    if not retirement_plan or retirement_plan.get("status") != "feasible":
        return None

    retirement_glide = retirement_plan.get("glide_path") or {}
    return _coerce_positive_int(retirement_glide.get("accumulation_years"))


def _extract_onetime_horizon(goal: dict) -> int | None:
    goal_summary = goal.get("goal_summary") or {}
    glide_path = goal.get("glide_path") or {}

    return (
        _coerce_positive_int(goal_summary.get("years_to_goal"))
        or _coerce_positive_int(glide_path.get("total_years"))
        or _coerce_positive_int(goal.get("time_horizon_years"))
    )


def _extract_recurring_horizon(goal: dict) -> int | None:
    goal_summary = goal.get("goal_summary") or {}
    years_to_first = _coerce_positive_int(
        goal_summary.get("years_to_first_occurrence", goal_summary.get("years_to_first"))
    )
    frequency_years = _coerce_positive_int(goal_summary.get("frequency_years"))
    num_occurrences = _coerce_positive_int(goal_summary.get("num_occurrences"))

    if years_to_first is not None and frequency_years is not None and num_occurrences is not None:
        return years_to_first + frequency_years * (num_occurrences - 1)

    return (
        _coerce_positive_int(goal_summary.get("total_planning_years"))
        or _coerce_positive_int(goal.get("time_horizon_years"))
    )


def compute_corridor_status(
    total_sip:    float,
    disposable:   float,
    floor_pct:    float = 20.0,   # default, user-adjustable, minimum 7%
    ceiling_pct:  float = 70.0,   # fixed at 100 - (floor + buffer)
    buffer_pct:   float = 10.0    # default, user-adjustable, minimum 5%
) -> dict:

    # Guardrail: negative disposable is treated as zero available capacity.
    effective_disposable = max(disposable, 0.0)
    
    time_start = datetime.now()
    # Absolute amounts from disposable
    ceiling_amount = effective_disposable * ceiling_pct  / 100
    floor_amount   = effective_disposable * floor_pct    / 100
    buffer_amount  = effective_disposable * buffer_pct   / 100

    if effective_disposable > 0:
        sip_ratio = total_sip / effective_disposable * 100
    elif total_sip > 0:
        sip_ratio = 999.9
    else:
        sip_ratio = 0.0

    # Three alert levels
    if effective_disposable <= 0 and total_sip > 0:
        status = "over_invested"
        alert_level = "critical"
        message = (
            "You currently have no disposable income, but SIP commitments still exist. "
            "Pause or defer lower-priority goals immediately."
        )

    elif total_sip > ceiling_amount:
        status = "over_invested"
        alert_level = "critical"
        message = (
            "Your total SIP commitments exceed 70% of your disposable income. "
            "Your emergency buffer is being compromised. "
            "Reduce or defer a lower-priority goal."
        )

    elif total_sip > ceiling_amount * 0.90:   # between 63% and 70%
        status = "approaching_ceiling"
        alert_level = "warning"
        message = (
            "Your total SIP is approaching the 70% ceiling. "
            "You have limited room to add new goals."
        )

    elif total_sip < floor_amount:
        status = "under_saving"
        alert_level = "advisory"
        message = (
            "Your total SIP is below the recommended 20% savings floor. "
            "Consider increasing contributions to build long-term wealth."
        )

    else:
        status = "in_corridor"
        alert_level = "none"
        message = "All goals are within the safe savings corridor."
        
    time_end = datetime.now()
    logger.info({
        "event": "Corridor status computed",
        "time_taken_seconds": (time_end - time_start).total_seconds(),
        "status": status,
        "alert_level": alert_level,
        "message": message,
    })
    return {
        "status":          status,
        "alert_level":     alert_level,
        "sip_ratio_pct":   round(sip_ratio, 1),
        "ceiling_pct":     ceiling_pct,
        "floor_pct":       floor_pct,
        "buffer_pct":      buffer_pct,
        "ceiling_amount":  round(ceiling_amount, 2),
        "floor_amount":    round(floor_amount,   2),
        "buffer_amount":   round(buffer_amount,  2),
        "message":         message,
        "alert_level":     alert_level
    }
    
    

def compute_max_horizon(data: ConflictEngineRequest) -> int:
    horizons = []
    
    time_start = datetime.now()
    retirement_years = _extract_retirement_horizon(data.retirement_plan)
    if retirement_years is not None:
        horizons.append(retirement_years)

    for goal in data.onetime_goals:
        if goal.get("status") != "feasible":
            continue
        years_to_goal = _extract_onetime_horizon(goal)
        if years_to_goal is not None:
            horizons.append(years_to_goal)

    for goal in data.recurring_goals:
        if goal.get("status") != "feasible":
            continue
        recurring_horizon = _extract_recurring_horizon(goal)
        if recurring_horizon is not None:
            horizons.append(recurring_horizon)
    
    max_horizon = max(horizons) if horizons else 0
            
    time_end= datetime.now()
    logger.info({
        "event":"max horizon computed",         
        "time_taken_seconds": (time_end - time_start).total_seconds(),
        "horizons_computed": max_horizon
    })
    return max_horizon

def compute_all_goal_sips_for_year(data: ConflictEngineRequest, year: int) -> dict:
    goal_sips: dict[str, float] = {}
    year_index = max(year - 1, 0)
    
    time_start = datetime.now()
    # Retirement SIP for this year
    if data.retirement_plan and data.retirement_plan.get("status") == "feasible":
        corpus = data.retirement_plan.get("corpus") or {}
        glide_path = data.retirement_plan.get("glide_path") or {}

        retirement_additional_monthly_sip = float(corpus.get("additional_monthly_sip_required", 0.0))
        retirement_existing_monthly_sip = float(data.retirement_plan.get("existing_monthly_sip", 0.0))
        retirement_years = _extract_retirement_horizon(data.retirement_plan) or 0

        # Prefer explicit total from glide path year 1 when available.
        yearly_schedule = glide_path.get("yearly_schedule") or []
        retirement_total_monthly_sip = (
            float(yearly_schedule[0].get("monthly_sip", 0.0))
            if yearly_schedule else
            retirement_existing_monthly_sip + retirement_additional_monthly_sip
        )

        if retirement_total_monthly_sip > 0 and year <= retirement_years:
            retirement_monthly_sip = future_value_goal(FutureValue(
                principal=retirement_total_monthly_sip,
                infation_rate=float(glide_path.get("sip_stepup_rate_pct", 0.0)),
                years=year_index,
            ))["future_value"]
            goal_sips["retirement_monthly_sip"] = retirement_monthly_sip

    # One-time goals SIP for this year
    for idx, goal in enumerate(data.onetime_goals, start=1):
        if goal.get("status") != "feasible":
            continue

        goal_name = goal.get("goal_name", f"onetime_goal_{idx}")
        sip_plan = goal.get("sip_plan", {})

        years_to_goal = _extract_onetime_horizon(goal) or 0
        base_monthly_sip = float(
            sip_plan.get(
                "total_first_year_sip",
                float(sip_plan.get("starting_monthly_sip", 0.0)) + float(sip_plan.get("existing_monthly_sip", 0.0))
            )
        )

        if base_monthly_sip > 0 and 1 <= year <= years_to_goal:
            monthly_sip_this_year = future_value_goal(FutureValue(
                principal=base_monthly_sip,
                infation_rate=float(sip_plan.get("annual_step_up_pct", 0.0)),
                years=year_index,
            ))["future_value"]
            goal_sips[f"onetime_{idx}_{goal_name}"] = monthly_sip_this_year

    # Recurring goals SIP for this year
    for idx, goal in enumerate(data.recurring_goals, start=1):
        if goal.get("status") != "feasible":
            continue

        goal_name = goal.get("goal_name", f"recurring_goal_{idx}")
        sip_plan = goal.get("sip_plan", {})
        occurrence_plans = sip_plan.get("occurrence_plans", [])

        goal_monthly_sip_this_year = 0.0
        for occ in occurrence_plans:
            occ_year = int(occ.get("years_from_now", 0))
            occ_base_monthly_sip = float(occ.get("monthly_sip", 0.0))

            # SIP for each occurrence is contributed from year 1 until its due year.
            if occ_base_monthly_sip > 0 and 1 <= year <= occ_year:
                goal_monthly_sip_this_year += future_value_goal(FutureValue(
                    principal=occ_base_monthly_sip,
                    infation_rate=float(sip_plan.get("sip_stepup_rate_pct", 0.0)),
                    years=year_index,
                ))["future_value"]

        if goal_monthly_sip_this_year > 0:
            goal_sips[f"recurring_{idx}_{goal_name}"] = goal_monthly_sip_this_year
    time_end = datetime.now()
    logger.info({
        "event": "Goal SIPs computed for year",
        "year": year,
        "time_taken_seconds": (time_end - time_start).total_seconds(),
        "goal_sips_computed": len(goal_sips)
    })
    return goal_sips

def prioritised_goal(
    data: ConflictEngineRequest,
    year: int
) -> list[dict]:
    
    goal_sips  = compute_all_goal_sips_for_year(data, year)
    all_goals  = []

    # Retirement
    if data.retirement_plan:
        all_goals.append({
            "goal_id":      "retirement",
            "goal_name":    "Retirement",
            "goal_type":    "retirement",
            "monthly_sip":  goal_sips.get("retirement_monthly_sip", 0.0),
            "priority_rank": 1   # always 1
        })

    # One-time goals
    for idx, goal in enumerate(data.onetime_goals, start=1):
        gid = goal.get("goal_id", f"onetime_{idx}")
        goal_name = goal.get("goal_name", f"onetime_goal_{idx}")
        all_goals.append({
            "goal_id":       gid,
            "goal_name":     goal_name,
            "goal_type":     "one_time",
            "monthly_sip":   goal_sips.get(f"onetime_{idx}_{goal_name}", 0.0),
            "priority_rank": data.priority_order.index(gid) + 1
                             if gid in data.priority_order
                             else 99
        })

    # Recurring goals
    for idx, goal in enumerate(data.recurring_goals, start=1):
        gid = goal.get("goal_id", f"recurring_{idx}")
        goal_name = goal.get("goal_name", f"recurring_goal_{idx}")
        all_goals.append({
            "goal_id":       gid,
            "goal_name":     goal_name,
            "goal_type":     "recurring",
            "monthly_sip":   goal_sips.get(f"recurring_{idx}_{goal_name}", 0.0),
            "priority_rank": data.priority_order.index(gid) + 1
                             if gid in data.priority_order
                             else 99
        })

    # Sort by priority rank — lowest number = highest priority
    return sorted(all_goals, key=lambda g: g["priority_rank"])


def compute_surplus_waterfall(data: ConflictEngineRequest, first_year_summary: dict) -> dict:
    
    year= first_year_summary["year"]
    disposable_amount = first_year_summary["disposable"]
    savings_amount = data.savings_pct / 100 * disposable_amount
    buffer_amount = data.buffer_pct / 100 * disposable_amount
    remaining_amount = disposable_amount -(savings_amount + buffer_amount)
    total_available_for_goals = max(remaining_amount, 0.0)
    
    all_goals= prioritised_goal(data,year)
    funded_goals = []
    deferred_goals = []
    
    time_start = datetime.now()
    
    for goal in all_goals:
        sip = goal["monthly_sip"]

        if sip <= 0:
            # Goal already complete or has zero SIP — skip
            continue

        if sip <= remaining_amount:
            remaining_amount -= sip
            funded_goals.append({
                "goal_id":          goal["goal_id"],
                "goal_name":        goal["goal_name"],
                "goal_type":        goal["goal_type"],
                "priority_rank":    goal["priority_rank"],
                "monthly_sip":      round(sip,       2),
                "remaining_after":  round(remaining_amount, 2),
                "status":           "funded",
                "funded_fully":     True
            })

        elif remaining_amount > 0:
            # Partial funding — some money left but not enough for full SIP
            partially_funded = remaining_amount
            shortfall        = sip - remaining_amount
            remaining_amount        = 0.0

            funded_goals.append({
                "goal_id":          goal["goal_id"],
                "goal_name":        goal["goal_name"],
                "goal_type":        goal["goal_type"],
                "priority_rank":    goal["priority_rank"],
                "monthly_sip":      round(sip,               2),
                "funded_amount":    round(partially_funded,   2),
                "shortfall":        round(shortfall,          2),
                "remaining_after":  0.0,
                "status":           "partially_funded",
                "funded_fully":     False
            })

        else:
            # Pool exhausted — goal cannot be funded at all
            deferred_goals.append({
                "goal_id":       goal["goal_id"],
                "goal_name":     goal["goal_name"],
                "goal_type":     goal["goal_type"],
                "priority_rank": goal["priority_rank"],
                "monthly_sip":   round(sip, 2),
                "shortfall":     round(sip, 2),
                "status":        "deferred",
                "reason":        (
                    "Insufficient surplus after funding "
                    "{} higher priority goal(s).".format(
                        len(funded_goals)
                    )
                )
            })

    total_allocated = total_available_for_goals - remaining_amount
    below_floor = total_allocated < savings_amount
    
    time_end = datetime.now()
    logger.info({
        "event": "Surplus waterfall computed for year",
        "year": year,
        "time_taken_seconds": (time_end - time_start).total_seconds(),
        "total_goals_considered": len(all_goals),
        "funded_goals_count": len(funded_goals),
        "deferred_goals_count": len(deferred_goals),
        "total_allocated": round(total_allocated, 2),
        "below_floor": below_floor
    })

    return {
        "year":               year,
        "monthly_income":     round(data.monthly_income,   2),
        "monthly_expenses":   round(data.monthly_expenses, 2),
        "disposable":         round(disposable_amount,       2),

        # The three buckets
        "ceiling_amount":     round(total_available_for_goals,   2),   # 70% — max for SIPs
        "floor_amount":       round(remaining_amount,     2),   # 20% — minimum savings
        "buffer_amount":      round(buffer_amount,    2),   # 10% — untouchable

        # Allocation result
        "total_allocated":    round(total_allocated,  2),
        "remaining_surplus":  round(remaining_amount,        2),

        # Floor status
        "below_floor":        below_floor,
        "floor_gap":          round(
            max(0, savings_amount - total_allocated), 2
        ),

        # Goal breakdown
        "funded_goals":       funded_goals,
        "deferred_goals":     deferred_goals,
        "funded_count":       len(funded_goals),
        "deferred_count":     len(deferred_goals),
    }

            
def generate_recommendations(critical, warning, advisory, data):
    recs = []

    if critical:
        recs.append({
            "type":     "critical",
            "year":     critical[0]["year"],
            "message":  f"Goals exceed allocated {data.ceiling_pct}% of disposable income",
            "impact":   "emergency buffer compromised",
            "levers": [
                "defer lowest priority goal",
                "extend timeline of lowest priority goal",
                "reduce amount of lowest priority goal"
            ],
            "suggested_goal": data.priority_order[-1]
        })

    if warning:
        recs.append({
            "type":    "warning",
            "year":    warning[0]["year"],
            "message": f"Approaching {data.ceiling_pct}% ceiling — limited room for new goals",
            "levers":  ["review before adding any new goal"]
        })

    if advisory:
        recs.append({
            "type":    "advisory",
            "message": f"Total SIP below {data.savings_pct}% floor",
            "levers":  [
                "increase retirement SIP",
                "add a new savings goal",
                "increase step-up rate"
            ]
        })

    if not critical and not warning and not advisory:
        recs.append({
            "type":    "all_clear",
            "message": "All goals within corridor",
            "surplus": "Room exists to add new goals or increase contributions"
        })

    return recs


def compute_conflict_engine(data: ConflictEngineRequest) -> dict:

    g_income   = data.income_raise_pct
    g_expenses = 5.0
    max_years  = compute_max_horizon(data)

    yearly_summary = []
    
    time_start = datetime.now()

    for year in range(1, max_years + 1):
        t = year - 1

        # Project income and expenses
        monthly_income   = future_value_goal(FutureValue(
            principal=data.monthly_income,
            infation_rate=g_income,
            years=t,
        ))["future_value"]
        monthly_expenses = future_value_goal(FutureValue(
            principal=data.monthly_expenses,
            infation_rate=g_expenses,
            years=t,
        ))["future_value"]
        disposable       = monthly_income - monthly_expenses

        # Get each goal's SIP in this year (stepped up at its own rate)
        goal_sips  = compute_all_goal_sips_for_year(data, year)
        total_sip  = sum(goal_sips.values())

        # Corridor check against DISPOSABLE income
        corridor   = compute_corridor_status(
            total_sip   = total_sip,
            disposable  = disposable,
            floor_pct   = data.savings_pct,
            ceiling_pct = data.ceiling_pct,
            buffer_pct  = data.buffer_pct
        )

        yearly_summary.append({
            "year":           year,
            "monthly_income": round(monthly_income,  2),
            "monthly_expenses":round(monthly_expenses,2),
            "disposable":     round(disposable,      2),
            "goal_sips":      {k: round(v, 2) for k, v in goal_sips.items()},
            "total_sip":      round(total_sip,       2),

            # The three buckets of disposable
            "ceiling_amount": corridor["ceiling_amount"],
            "savings_amount":   corridor["floor_amount"],
            "buffer_amount":  corridor["buffer_amount"],

            # Status
            "corridor":       corridor
        })

    if not yearly_summary:
        return {
            "overall_status": "all_clear",
            "critical_breach_count": 0,
            "warning_breach_count": 0,
            "advisory_count": 0,
            "first_critical_year": None,
            "first_warning_year": None,
            "corridor_config": {
                "ceiling_pct": data.ceiling_pct,
                "savings_pct": data.savings_pct,
                "buffer_pct": data.buffer_pct,
            },
            "surplus_waterfall": {
                "funded_goals": [],
                "deferred_goals": [],
                "funded_count": 0,
                "deferred_count": 0,
            },
            "deferred_goals": [],
            "yearly_summary": [],
            "recommendations": [{
                "type": "all_clear",
                "message": "No active goals found. Add one-time or recurring goals to run conflict analysis.",
            }],
        }

    # Surplus waterfall at year 1
    waterfall = compute_surplus_waterfall(data, yearly_summary[0])

    # Aggregate breach summary
    critical_years  = [y for y in yearly_summary
                       if y["corridor"]["alert_level"] == "critical"]
    warning_years   = [y for y in yearly_summary
                       if y["corridor"]["alert_level"] == "warning"]
    advisory_years  = [y for y in yearly_summary
                       if y["corridor"]["alert_level"] == "advisory"]

    overall_status = (
        "conflict_detected" if critical_years  else
        "warning"           if warning_years   else
        "under_saving"      if advisory_years  else
        "all_clear"
    )
    time_end = datetime.now()
    logger.info({
        "event": "Conflict engine computation completed",
        "time_taken_seconds": (time_end - time_start).total_seconds(),
        "overall_status": overall_status,
        "critical_breach_count": len(critical_years),
        "warning_breach_count": len(warning_years),
        "advisory_count": len(advisory_years),
    })

    return {
        "overall_status":         overall_status,
        "critical_breach_count":  len(critical_years),
        "warning_breach_count":   len(warning_years),
        "advisory_count":         len(advisory_years),
        "first_critical_year":    critical_years[0]["year"]  if critical_years else None,
        "first_warning_year":     warning_years[0]["year"]   if warning_years  else None,

        # Corridor config used
        "corridor_config": {
            "ceiling_pct": data.ceiling_pct,
            "savings_pct": data.savings_pct,
            "buffer_pct":  data.buffer_pct,
        },

        # Surplus waterfall
        "surplus_waterfall": waterfall,

        # Deferred goals
        "deferred_goals": waterfall["deferred_goals"],

        # Full year by year
        "yearly_summary": yearly_summary,

        # Recommendations for AI layer
        "recommendations": generate_recommendations(
            critical_years, warning_years, advisory_years, data
        )
    }
    
def _parse_plan_json(raw: str | dict | None) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {}


def fetch_retirement_plan(db: Session, user_id: str) -> dict | None:
    row = db.query(RetirementPlan).filter(
        RetirementPlan.user_id == user_id,
        RetirementPlan.is_active == True,
    ).order_by(RetirementPlan.created_at.desc()).first()

    if not row:
        return None

    plan = _parse_plan_json(row.plan_data)
    plan["goal_id"] = "retirement"
    return plan


def fetch_onetime_goals(db: Session, user_id: str) -> list[dict]:
    """Fetch only FEASIBLE one-time goals for conflict engine.
    
    Infeasible goals should not be passed to conflict engine - they are 
    already flagged at creation time and don't need conflict resolution.
    """
    rows = db.query(OneTimeGoalPlan).filter(
        OneTimeGoalPlan.user_id == user_id,
        OneTimeGoalPlan.is_active == True,
    ).order_by(
        OneTimeGoalPlan.priority.is_(None),
        OneTimeGoalPlan.priority.asc(),
        OneTimeGoalPlan.created_at.asc(),
    ).all()

    goals = []
    for row in rows:
        plan = _parse_plan_json(row.goal_data)
        
        # Only include feasible goals in conflict engine
        if plan.get("status") != "feasible":
            continue
            
        plan["goal_id"] = row.id
        plan["goal_name"] = plan.get("goal_name", row.goal_name)
        plan["priority"] = row.priority
        plan["time_horizon_years"] = row.time_horizon_years
        goals.append(plan)
    return goals


def fetch_recurring_goals(db: Session, user_id: str) -> list[dict]:
    """Fetch only FEASIBLE recurring goals for conflict engine.
    
    Infeasible goals should not be passed to conflict engine - they are 
    already flagged at creation time and don't need conflict resolution.
    """
    rows = db.query(RecurringGoalPlan).filter(
        RecurringGoalPlan.user_id == user_id,
        RecurringGoalPlan.is_active == True,
    ).order_by(
        RecurringGoalPlan.priority.is_(None),
        RecurringGoalPlan.priority.asc(),
        RecurringGoalPlan.created_at.asc(),
    ).all()

    goals = []
    for row in rows:
        plan = _parse_plan_json(row.goal_data)
        
        # Only include feasible goals in conflict engine
        if plan.get("status") != "feasible":
            continue
            
        plan["goal_id"] = row.id
        plan["goal_name"] = plan.get("goal_name", row.goal_name)
        plan["priority"] = row.priority
        plan["time_horizon_years"] = row.time_horizon_years
        goals.append(plan)
    return goals


def fetch_user_profile(db: Session, user_id: str) -> User:
    row = db.query(User).filter(User.id == user_id).first()
    if not row:
        raise ValueError("User not found")
    return row


def normalize_goal_priorities(db: Session, user_id: str) -> tuple[list[str], bool]:
    """Assign continuous priorities across one-time and recurring goals.

    Retirement is always priority 1 and is not stored in goal tables.
    Goal tables start from priority 2 and continue without gaps.
    
    Returns:
        tuple: (ordered_ids, has_unprioritized_goals)
            - ordered_ids: List of goal IDs in priority order
            - has_unprioritized_goals: True if any goals had None priority
    """

    rows: list[tuple[str, str, int | None, object, object]] = []

    one_time_rows = db.query(OneTimeGoalPlan).filter(
        OneTimeGoalPlan.user_id == user_id,
        OneTimeGoalPlan.is_active == True,
    ).all()
    rows.extend([("one_time", row.id, row.priority, row.created_at, row) for row in one_time_rows])

    recurring_rows = db.query(RecurringGoalPlan).filter(
        RecurringGoalPlan.user_id == user_id,
        RecurringGoalPlan.is_active == True,
    ).all()
    rows.extend([("recurring", row.id, row.priority, row.created_at, row) for row in recurring_rows])

    # Track if any goals lack user-assigned priorities
    has_unprioritized = any(row[2] is None for row in rows)

    rows.sort(key=lambda x: (x[2] is None, x[2] if x[2] is not None else 9999, x[3]))

    next_priority = 2
    ordered_ids = ["retirement"]
    changed = False

    for goal_type, goal_id, old_priority, _, row in rows:
        ordered_ids.append(goal_id)
        if old_priority != next_priority:
            row.priority = next_priority
            changed = True
        next_priority += 1

    if changed:
        db.commit()

    return ordered_ids, has_unprioritized


def fetch_priority_order(db: Session, user_id: str) -> tuple[list[str], bool]:
    return normalize_goal_priorities(db, user_id)


def save_conflict_result(db: Session, user_id: str, result: dict) -> ConflictResults:
    db.query(ConflictResults).filter(
        ConflictResults.user_id == user_id,
        ConflictResults.is_latest == True,
    ).update({"is_latest": False})

    record = ConflictResults(
        user_id=user_id,
        overall_status=result.get("overall_status"),
        ceiling_breach_count=result.get("critical_breach_count", 0),
        floor_breach_count=result.get("advisory_count", 0),
        deferred_goal_count=len(result.get("deferred_goals", [])),
        funded_goal_count=result.get("surplus_waterfall", {}).get("funded_count", 0),
        result_data=json.dumps(result, default=str),
        is_latest=True,
    )

    db.add(record)
    db.commit()
    db.refresh(record)
    return record


async def run_and_save_conflict_engine(user_id: str, db: Session) -> dict:
    retirement = fetch_retirement_plan(db, user_id)
    onetime = fetch_onetime_goals(db, user_id)
    recurring = fetch_recurring_goals(db, user_id)
    profile = fetch_user_profile(db, user_id)
    priorities, needs_priority_input = fetch_priority_order(db, user_id)

    # Run engine
    result = compute_conflict_engine(ConflictEngineRequest(
        retirement_plan=retirement,
        onetime_goals=onetime,
        recurring_goals=recurring,
        monthly_income=(profile.current_income or 0.0) / 12,
        monthly_expenses=profile.current_monthly_expenses or 0.0,
        income_raise_pct=profile.income_raise_pct or 0.0,
        priority_order=priorities,
        savings_pct=profile.savings_pct or 20.0,
        buffer_pct=profile.buffer_pct or 10.0,
    ))

    # Only prompt for priorities if user hasn't set them yet
    if needs_priority_input:
        result["priority_input_required"] = {
            "message": "Please provide a continuous priority order for all goals (one-time and recurring). Retirement is always priority 1.",
            "expected_format": ["retirement", "<goal_id_1>", "<goal_id_2>"],
            "current_auto_order": priorities,
        }

    # Save to DB
    save_conflict_result(db, user_id, result)

    return result