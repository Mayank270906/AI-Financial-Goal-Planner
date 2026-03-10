
from app.schemas.calculation import (
    FutureValue, 
    BlendedReturn, 
    RequiredAnnualSavings, 
    SuggestedAllocation,
    CheckFeasibilityRequest,
    CheckRebalancing,
    SIPRequest,
    GlidePathRequest,
    RebalanceRequest
)
from app.utils.log_format import JSONFormatter
import logging
from datetime import datetime

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger = logging.getLogger("maths_services")
logger.addHandler(handler)
logger.setLevel(logging.INFO)



def future_value_goal(data: FutureValue):
    P = data.principal
    inflation = data.infation_rate/100
    years = data.years
    
    time_start = datetime.now()
    future_value = P * ((1 + inflation) ** years)
    time_end = datetime.now()
    logger.info({
        "event": "Future value calculated",
        "time_taken_seconds": (time_end - time_start).total_seconds()
    })
    return {"future_value": future_value}


def blended_return(data: BlendedReturn):
    equity_pct = data.equity_pct/100
    debt_pct = data.debt_pct/100
    re = data.return_equity
    rd = data.return_debt
    
    blended = (equity_pct * re) + (debt_pct * rd)
    return {"blended_return": blended}


def required_annual_saving(data: RequiredAnnualSavings):
    FV_goal = data.future_value
    r = data.return_rate/100
    years = data.years
    current_savings = 0

    time_start = datetime.now()
    
    if r == 0:
        required_saving = (FV_goal - current_savings) / years
    else:
        required_saving = (FV_goal - current_savings * ((1 + r) ** years)) / (((1 + r) ** years - 1) / r)
    
    time_end = datetime.now()
    logger.info({
        "event": "Required annual saving calculated",
        "time_taken_seconds": (time_end - time_start).total_seconds()
    })
    return {"required_annual_saving": required_saving}


def suggest_allocation(data: SuggestedAllocation):
    years = data.years
    risk = data.risk
    
    time_start = datetime.now()
    if years < 3:
        equity_pct = 20
    elif years < 7:
        equity_pct = 50
    else:
        equity_pct = 70
    
    if risk.lower() == "low":
        equity_pct = max(0, equity_pct - 20)
    elif risk.lower() == "moderate":
        # Keep the base allocation as-is
        pass
    elif risk.lower() == "high":
        equity_pct = min(100, equity_pct + 20)
    
    debt_pct = 100 - equity_pct
    time_end = datetime.now()
    logger.info({
        "event": "Suggested allocation calculated",
        "time_taken_seconds": (time_end - time_start).total_seconds()
    })
    
    return {"equity_allocation": equity_pct, "debt_allocation": debt_pct}


def check_feasibility(data: CheckFeasibilityRequest) -> dict:
    g_income   = data.income_raise_pct / 100
    g_sip      = data.annual_step_up_pct / 100
    g_expenses = 0.05                          # conservative fixed expense growth
    cap        = data.savings_cap_pct / 100

    breach_years    = []
    yearly_summary  = []
    peak_ratio      = 0.0
    
    time_start = datetime.now()

    for year in range(1, data.years_to_goal + 1):
        t = year - 1   # index from 0

        # Income and expenses grow each year
        monthly_income   = data.monthly_income   * (1 + g_income)   ** t
        monthly_expenses = data.monthly_expenses * (1 + g_expenses) ** t

        # Disposable income = what remains after fixed expenses
        disposable       = monthly_income - monthly_expenses

        # This goal's SIP steps up at derived real rate
        this_goal_sip    = data.starting_monthly_sip * (1 + g_sip) ** t

        # Existing committed SIPs also step up at same real rate
        existing_sip     = data.existing_monthly_sip * (1 + g_sip) ** t

        # Total SIP burden this year
        total_sip        = this_goal_sip + existing_sip

        # Savings ratio against disposable income
        ratio            = (total_sip / disposable) if disposable > 0 else float("inf")
        within_cap       = ratio <= cap
        peak_ratio       = max(peak_ratio, ratio)

        record = {
            "year":                   year,
            "monthly_income":         round(monthly_income,   2),
            "monthly_expenses":       round(monthly_expenses, 2),
            "disposable_income":      round(disposable,       2),
            "this_goal_sip":          round(this_goal_sip,    2),
            "existing_sip":           round(existing_sip,     2),
            "total_sip":              round(total_sip,        2),
            "savings_ratio_pct":      round(ratio * 100,      1),
            "cap_pct":                data.savings_cap_pct,
            "within_cap":             within_cap,
        }

        yearly_summary.append(record)

        if not within_cap:
            breach_years.append(record)

    feasible         = len(breach_years) == 0
    shortfall_year1  = max(
        0,
        data.starting_monthly_sip + data.existing_monthly_sip
        - (data.monthly_income - data.monthly_expenses) * cap
    )
    
    timeend=datetime.now()
    logger.info({
        "event": "Feasibility check completed",
        "time_taken_seconds": (timeend - time_start).total_seconds(),
        "feasible": feasible,
        "peak_savings_ratio_pct": round(peak_ratio * 100, 1),
        "breach_count": len(breach_years)
    })

    return {
        # Top-level verdict
        "feasible":             feasible,
        "status":               "feasible" if feasible else "infeasible",

        # Shortfall context (only meaningful if infeasible)
        "monthly_shortfall":    round(shortfall_year1, 2) if not feasible else 0.0,

        # Breach summary
        "breach_count":         len(breach_years),
        "first_breach_year":    breach_years[0]["year"] if breach_years else None,
        "first_breach_ratio":   round(breach_years[0]["savings_ratio_pct"], 1) if breach_years else None,
        "peak_savings_ratio":   round(peak_ratio * 100, 1),

        # Year-by-year detail
        "yearly_summary":       yearly_summary,
        "breach_years":         breach_years,

        # Input echo for transparency
        "inputs": {
            "starting_monthly_sip":  data.starting_monthly_sip,
            "existing_monthly_sip":  data.existing_monthly_sip,
            "annual_step_up_pct":    data.annual_step_up_pct,
            "monthly_income":        data.monthly_income,
            "monthly_expenses":      data.monthly_expenses,
            "income_raise_pct":      data.income_raise_pct,
            "savings_cap_pct":       data.savings_cap_pct,
            "years_to_goal":         data.years_to_goal,
        }
    }

def check_rebalancing(data: CheckRebalancing):
    planned_alloc = data.planned_alloc
    current_alloc = data.current_alloc
    threshold = data.threshold
    
    needs_rebalancing = False
    deviations = {}
    
    for key in planned_alloc:
        if key in current_alloc:
            deviation = abs(planned_alloc[key] - current_alloc[key])
            deviations[key] = deviation
            if deviation > threshold:
                needs_rebalancing = True
    
    return {"needs_rebalancing": needs_rebalancing, "deviations": deviations}

# Phase 1 Implementation

def calculate_sip(data: SIPRequest) -> dict:
    r = data.pre_ret_return/100
    n = data.years_to_goal
    i = data.inflation_rate/100
    income_raise = data.income_raise_pct/100
    
    time_start = datetime.now()
    #Caluclating the future value of the goal
    future_goal = future_value_goal(FutureValue(
        principal=data.goal_amount,
        infation_rate=data.inflation_rate,  # Note: schema has typo 'infation_rate'
        years=data.years_to_goal
    ))["future_value"]
    
    #Step-up fisher equation
    g = ((1 + income_raise) / (1 + i)) - 1
    
    if abs(r - g) < 1e-9:
        # Edge case: return ≈ step-up rate, use linear approximation
        annual_sip = future_goal / (n * (1 + r) ** (n - 1))
    else:
        annual_sip = (
            future_goal * (r - g)
            / (((1 + r) ** n - (1 + g) ** n) * (1 + r / 12))
        )
    
    starting_monthly_sip = annual_sip / 12
    
    time_end = datetime.now()
    logger.info({
        "event": "SIP calculated",
        "time_taken_seconds": (time_end - time_start).total_seconds(),
        "future_goal": round(future_goal, 2),
        "annual_sip": round(annual_sip, 2),
        "starting_monthly_sip": round(starting_monthly_sip, 2)
    })

    return {
        "goal_today":              round(data.goal_amount, 2),
        "goal_at_target_date":     round(future_goal, 2),
        "starting_monthly_sip":    round(starting_monthly_sip, 2),
        "annual_step_up_pct":      round(g * 100, 4),
        "years_to_goal":           n,
        "inflation_rate_pct":      data.inflation_rate,
        "income_raise_pct":        data.income_raise_pct,
        "expected_return_pct":     data.pre_ret_return,
    }
    
    
def calculate_glide_path(data: GlidePathRequest) -> dict:
    current_age  = data.current_age
    goal_age     = data.goal_age
    e_start      = data.start_equity_percent
    e_end        = data.end_equity_percent
    total_years  = goal_age - current_age

    schedule = []
    
    time_start = datetime.now()

    for t in range(total_years + 1):
        equity = e_start - ((e_start - e_end) / total_years) * t
        debt   = 100 - equity

        schedule.append({
            "year":           current_age + t+1,    # actual age: 31, 32...
            "age":            current_age + t,    # actual age: 31, 32...
            "equity_percent": round(equity, 2),
            "debt_percent":   round(debt, 2)
        })
    time_end=datetime.now()
    logger.info({
        "event": "Glide path calculated",
        "time_taken_seconds": (time_end - time_start).total_seconds(),
        "start_equity_percent": e_start,   
        "end_equity_percent": e_end,
        "total_years": total_years
    })

    return {
        "current_age":          current_age,
        "goal_age":             goal_age,
        "total_years":          total_years,
        "start_equity_percent": e_start,
        "end_equity_percent":   e_end,
        "yearly_allocation_table": schedule
    }
    
    
def check_portfolio_rebalance(data: RebalanceRequest):
    current_equity = data.current_equity_value
    current_debt = data.current_debt_value
    target_equity_ratio = data.current_year_target_ratio # decimal, e.g. 0.60
    
    total_portfolio = current_equity + current_debt
    if total_portfolio == 0:
        return {"rebalance_required": False, "suggested_move_amount": 0, "message": "Empty portfolio"}
        
    actual_equity_ratio = current_equity / total_portfolio
    drift = abs(actual_equity_ratio - target_equity_ratio)
    
    rebalance_required = False
    
    # 5/25 Rule
    if target_equity_ratio > 0.20:
        # Large domain: Absolute drift > 5%
        if drift > 0.05:
            rebalance_required = True
    else:
        # Small domain: Relative drift > 25%
        if drift > (0.25 * target_equity_ratio):
            rebalance_required = True
            
    suggested_move = 0
    if rebalance_required:
        target_equity_val = total_portfolio * target_equity_ratio
        suggested_move = target_equity_val - current_equity
        # Positive means Buy Equity (Move from Debt to Equity)
        # Negative means Sell Equity (Move from Equity to Debt)
        
    return {
        "rebalance_required": rebalance_required,
        "suggested_move_amount": round(suggested_move, 2),
        "current_equity_ratio": round(actual_equity_ratio, 4),
        "target_equity_ratio": target_equity_ratio,
        "drift": round(drift, 4)
    }
