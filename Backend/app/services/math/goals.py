from typing import Optional, TYPE_CHECKING
from app.schemas.user import Retirement, BucketAllocation
from app.schemas.goals import OneTimeGoalRequest, RecurringGoalRequest
from app.schemas.calculation import CheckFeasibilityRequest, SIPRequest, GlidePathRequest, SuggestedAllocation
from app.services.math.calculation import calculate_sip, calculate_glide_path, check_feasibility, suggest_allocation
import os
from openai import OpenAI
import datetime
import json
from dotenv import load_dotenv
import logging
from datetime import datetime
from app.utils.log_format import JSONFormatter

if TYPE_CHECKING:
    from app.models.db import User

# Load environment variables from .env file
load_dotenv()

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger = logging.getLogger("goal_services")
logger.addHandler(handler)
logger.setLevel(logging.INFO)


def _non_negative(value: float) -> float:
    return max(value, 0.0)


def check_feasibility_retirement(r: Retirement, additional_monthly_sip: float) -> dict:
    g = r.income_raise_pct / 100
    gs = (r.spouse_income_raise_pct or 0) / 100
    i = r.inflation_rate / 100
    s = ((1 + g) / (1 + i)) - 1  # derived real step-up rate
    n_acc = r.years_to_retirement
    savings_ratio_cap = 0.50

    breach_years = []
    yearly_summary = []

    for year in range(n_acc):
        # Household income grows each year
        user_monthly_income = (r.current_income / 12) * (1 + g) ** year

        spouse_monthly_income = 0.0
        if r.marital_status == "Married" and r.spouse_income:
            spouse_monthly_income = (r.spouse_income / 12) * (1 + gs) ** year

        total_monthly_income = user_monthly_income + spouse_monthly_income

        # Total SIP steps up at sip_raise_pct
        total_sip = (r.existing_monthly_sip + additional_monthly_sip) * (1 + s) ** year

        ratio = total_sip / total_monthly_income if total_monthly_income > 0 else float('inf')

        record = {
            "year": year + 1,
            "age": r.age + year,
            "monthly_household_income": round(total_monthly_income, 2),
            "total_monthly_sip": round(total_sip, 2),
            "savings_ratio_pct": round(ratio * 100, 1),
            "within_cap": ratio <= savings_ratio_cap
        }
        yearly_summary.append(record)

        if ratio > savings_ratio_cap:
            breach_years.append(record)

    feasible = bool(len(breach_years) == 0)

    result = {
        "feasible": feasible
    }

    if not feasible:
        first_breach = breach_years[0]
        result["failure"] = {
            "year": first_breach["year"],
            "age": first_breach["age"],
            "monthly_household_income": first_breach["monthly_household_income"],
            "total_monthly_sip": first_breach["total_monthly_sip"],
            "savings_ratio_pct": first_breach["savings_ratio_pct"],
            "message": "Total monthly SIP exceeds 50% of household monthly income."
        }

    return result


def compute_retirement_corpus(r: Retirement) -> dict:
    i = r.inflation_rate / 100
    rp = r.post_retirement_return / 100
    rpr = r.pre_retirement_return / 100
    n_acc = r.years_to_retirement
    n_ret = r.retirement_duration
    s = r.sip_raise_pct / 100

    # Step 1: Inflation-adjusted annual expense at retirement
    annual_expense_at_retirement = (
        r.current_monthly_expenses * 12 * (r.post_retirement_expense_pct / 100)
        * (1 + i) ** n_acc
    )

    # Step 2: Net annual withdrawal
    income_at_retirement = r.annual_post_retirement_income * (1 + i) ** n_acc
    net_withdrawal = annual_expense_at_retirement - income_at_retirement

    # Step 3: Required corpus — growing annuity
    if abs(rp - i) < 1e-9:
        corpus_required = net_withdrawal * n_ret
    else:
        corpus_required = (
            net_withdrawal
            * (1 - ((1 + i) / (1 + rp)) ** n_ret)
            / (rp - i)
        )

    # Step 4: FV of existing corpus
    fv_corpus = r.existing_corpus * (1 + rpr) ** n_acc

    # Step 5: FV of existing SIP with step-up
    if r.existing_monthly_sip > 0:
        annual_sip = r.existing_monthly_sip * 12
        if abs(rpr - s) < 1e-9:
            fv_sip = annual_sip * n_acc * (1 + rpr) ** (n_acc - 1)
        else:
            fv_sip = (
                annual_sip
                * ((1 + rpr) ** n_acc - (1 + s) ** n_acc)
                / (rpr - s)
            )
    else:
        fv_sip = 0.0

    fv_sip = _non_negative(fv_sip)

    # Step 6: Corpus gap
    corpus_gap = corpus_required - fv_corpus - fv_sip

    # Step 7: Required additional monthly SIP
    if corpus_gap <= 0:
        additional_sip_required = 0.0
        feasible = True
    else:
        if abs(rpr - s) < 1e-9:
            # Degenerate case
            additional_sip_required = corpus_gap / (
                n_acc * (1 + rpr) ** (n_acc - 1) * 12
            )
        else:
            additional_sip_required = (
                corpus_gap * (rpr - s)
                / (((1 + rpr) ** n_acc - (1 + s) ** n_acc) * (1 + rpr / 12))
            )
        feasible = (additional_sip_required + r.existing_monthly_sip) <= (
            r.current_income / 12 * 0.5  # rough 50% income cap check
        )

    return {
        "annual_expense_at_retirement": round(_non_negative(annual_expense_at_retirement), 2),
        "income_at_retirement": round(_non_negative(income_at_retirement), 2),
        "net_annual_withdrawal": round(_non_negative(net_withdrawal), 2),
        "corpus_required": round(_non_negative(corpus_required), 2),
        "fv_existing_corpus": round(_non_negative(fv_corpus), 2),
        "fv_existing_sip": round(_non_negative(fv_sip), 2),
        "corpus_gap": round(_non_negative(corpus_gap), 2),
        "additional_monthly_sip_required": round(_non_negative(additional_sip_required), 2),
        "feasible": feasible,
    }

def compute_bucket_strategy(
    corpus_required: float,
    net_annual_withdrawal: float,   # W — first year withdrawal at retirement
    inflation_rate: float,          # % — for projecting future withdrawals
    retirement_age: int,
    life_expectancy: int,
    current_age_at_review: Optional[int] = None  # for glide path if reviewing mid-retirement
) -> dict:
    i = inflation_rate / 100
    corpus_required = _non_negative(corpus_required)
    W = _non_negative(net_annual_withdrawal)
    review_age = current_age_at_review or retirement_age  # at retirement if first plan

    # ── Bucket 1: Years 1–3
    B1_size = W * 3
    # No equity at all — pure stability
    B1_equity_pct = 0.0
    B1_debt_pct   = 100.0

    # ── Bucket 2: Years 4–10 (7 years)
    # Sum of inflation-grown withdrawals for years 4 through 10
    if i > 1e-9:
        # Geometric sum: W*(1+i)^3 + W*(1+i)^4 + ... + W*(1+i)^9
        B2_size = W * (1 + i)**3 * ((1 + i)**7 - 1) / i
    else:
        B2_size = W * 7

    # Glide path for Bucket 2 equity based on age at review
    if review_age < 65:
        B2_equity_pct = 30.0
    elif review_age < 70:
        B2_equity_pct = 20.0
    else:
        B2_equity_pct = 10.0
    B2_debt_pct = 100.0 - B2_equity_pct

    # ── Bucket 3: Remainder — years 11 to life expectancy
    B3_size = corpus_required - B1_size - B2_size

    if B3_size < 0:
        # Corpus is too small to fill all three buckets properly
        # Prioritise B1 (immediate needs), compress B2, nothing left for B3
        B3_size = 0.0
        B2_size = max(corpus_required - B1_size, 0.0)

    # Glide path for Bucket 3 equity
    if review_age < 65:
        B3_equity_pct = 70.0
    elif review_age < 70:
        B3_equity_pct = 60.0
    elif review_age < 75:
        B3_equity_pct = 50.0
    else:
        B3_equity_pct = 40.0   # floor — never goes below this
    B3_debt_pct = 100.0 - B3_equity_pct

    def split(size, eq_pct):
        eq = size * eq_pct / 100
        return round(eq, 2), round(size - eq, 2)

    B1_eq, B1_debt = split(B1_size, B1_equity_pct)
    B2_eq, B2_debt = split(B2_size, B2_equity_pct)
    B3_eq, B3_debt = split(B3_size, B3_equity_pct)

    buckets = {
        "bucket_1": BucketAllocation(
            name="Bucket 1 — Stability",
            size=round(B1_size, 2),
            equity_pct=B1_equity_pct,
            debt_pct=B1_debt_pct,
            years_covered="Years 1–3",
            purpose="Immediate withdrawals. Never exposed to market risk.",
            equity_amount=B1_eq,
            debt_amount=B1_debt
        ),
        "bucket_2": BucketAllocation(
            name="Bucket 2 — Stability with Moderate Growth",
            size=round(B2_size, 2),
            equity_pct=B2_equity_pct,
            debt_pct=B2_debt_pct,
            years_covered="Years 4–10",
            purpose="Replenishes Bucket 1. Moderate equity for inflation protection.",
            equity_amount=B2_eq,
            debt_amount=B2_debt
        ),
        "bucket_3": BucketAllocation(
            name="Bucket 3 — Long-Term Growth",
            size=round(B3_size, 2),
            equity_pct=B3_equity_pct,
            debt_pct=B3_debt_pct,
            years_covered=f"Years 11–{life_expectancy - retirement_age}",
            purpose="Long-term growth engine. Untouched for first 10 years.",
            equity_amount=B3_eq,
            debt_amount=B3_debt
        )
    }

    # ── Sanity check
    total_allocated = B1_size + B2_size + B3_size
    unallocated = corpus_required - total_allocated

    return {
        "corpus_required":    round(_non_negative(corpus_required), 2),
        "total_allocated":    round(_non_negative(total_allocated), 2),
        "unallocated_buffer": round(_non_negative(unallocated), 2),  # should be ~0 or small positive
        "review_age":         review_age,
        "retirement_duration_years": life_expectancy - retirement_age,
        "buckets":            buckets,
        "refill_rules": {
            "B1_refill_trigger": "B1 balance falls below 1 year of current expenses",
            "B1_refill_source":  "Sell from Bucket 2 debt portion first",
            "B2_refill_trigger": "B2 balance falls below 2 years of current expenses",
            "B2_refill_source":  "Sell from Bucket 3 — only after equity has recovered",
            "downturn_rule":     "Never sell equity during a market downturn. Live off B1 cash."
        }
    }
# ── Function 4: Pre-retirement glide path ─────────────────────────
def compute_pre_retirement_glide_path(r: Retirement, monthly_sip: float) -> dict:
    i = r.inflation_rate / 100
    g = r.income_raise_pct / 100
    s = ((1 + g) / (1 + i)) - 1          # derived step-up rate

    n_acc = r.years_to_retirement
    schedule = []

    for year in range(n_acc):
        age_this_year       = r.age + year
        years_to_retirement = n_acc - year
        sip_this_year       = monthly_sip * (1 + s) ** year

        # Equity allocation driven by years remaining to retirement
        if years_to_retirement > 15:
            equity_pct = 75.0
        elif years_to_retirement > 10:
            equity_pct = 60.0
        elif years_to_retirement > 5:
            equity_pct = 40.0
        elif years_to_retirement > 2:
            equity_pct = 25.0
        else:
            equity_pct = 10.0

        debt_pct   = 100.0 - equity_pct
        sip_equity = round(sip_this_year * equity_pct / 100, 2)
        sip_debt   = round(sip_this_year * debt_pct   / 100, 2)

        schedule.append({
            "year":               year + 1,
            "age":                age_this_year,
            "years_to_retirement": years_to_retirement,
            "monthly_sip":        round(sip_this_year, 2),
            "equity_pct":         equity_pct,
            "debt_pct":           debt_pct,
            "sip_to_equity":      sip_equity,
            "sip_to_debt":        sip_debt,
        })

    # Summarise the allocation bands for a quick overview
    bands = {}
    for record in schedule:
        label = f"{int(record['equity_pct'])}% equity / {int(record['debt_pct'])}% debt"
        if label not in bands:
            bands[label] = {
                "equity_pct":    record["equity_pct"],
                "debt_pct":      record["debt_pct"],
                "from_age":      record["age"],
                "to_age":        record["age"],
                "from_year":     record["year"],
                "to_year":       record["year"],
                "years_in_band": 1
            }
        else:
            bands[label]["to_age"]      = record["age"]
            bands[label]["to_year"]     = record["year"]
            bands[label]["years_in_band"] += 1

    return {
        "accumulation_years":  n_acc,
        "retirement_age":      r.retirement_age,
        "sip_stepup_rate_pct": round(s * 100, 4),
        "allocation_bands":    list(bands.values()),   # quick summary
        "yearly_schedule":     schedule                # full year-by-year detail
    }


# ── Orchestrator: updated to include glide path ───────────────────
def get_retirement_plan(r: Retirement) -> dict:
    # Step 1: Corpus and SIP
    time_start = datetime.now()
    corpus_result = compute_retirement_corpus(r)

    # Step 2: Feasibility
    feasibility = check_feasibility_retirement(
        r,
        additional_monthly_sip=corpus_result["additional_monthly_sip_required"]
    )

    if not feasibility["feasible"]:
        return {
            "status":      "infeasible",
            "corpus":      corpus_result,
            "feasibility": feasibility,
            "glide_path":  None,
            "buckets":     None
        }

    # Step 3: Total monthly SIP the user needs to invest from month 1
    total_monthly_sip = (
        r.existing_monthly_sip
        + corpus_result["additional_monthly_sip_required"]
    )

    # Step 4: Pre-retirement glide path — how to invest that SIP each year
    glide_path = compute_pre_retirement_glide_path(r, total_monthly_sip)

    # Step 5: Post-retirement bucket strategy — how to draw down after retirement
    buckets = compute_bucket_strategy(
        corpus_required       = corpus_result["corpus_required"],
        net_annual_withdrawal = corpus_result["net_annual_withdrawal"],
        inflation_rate        = r.inflation_rate,
        retirement_age        = r.retirement_age,
        life_expectancy       = r.life_expectancy,
        current_age_at_review = r.retirement_age
    )
    
    time_end = datetime.now()
    logger.info({
        "event": "Retirement plan computed",
        "time_taken_seconds": (time_end - time_start).total_seconds(),
        "feasible": feasibility["feasible"],
        "corpus_required": corpus_result["corpus_required"],
        "additional_monthly_sip_required": corpus_result["additional_monthly_sip_required"]
    })

    return {
        "status":      "feasible",
        "corpus":      corpus_result,
        "feasibility": feasibility,
        "glide_path":  glide_path,   # pre-retirement  — accumulation roadmap
        "buckets":     buckets       # post-retirement — drawdown structure
    }


def format_inr(value: float) -> str:
    is_negative = value < 0
    value = abs(value)
    
    # Split integer and decimal parts
    integer_part = int(value)
    decimal_part = round(value - integer_part, 2)
    decimal_str = f"{decimal_part:.2f}".split(".")[1]
    
    # Indian grouping: last 3 digits, then groups of 2
    s = str(integer_part)
    if len(s) <= 3:
        formatted = s
    else:
        # Last 3 digits
        last3 = s[-3:]
        remaining = s[:-3]
        # Group remaining in pairs from right
        groups = []
        while len(remaining) > 2:
            groups.append(remaining[-2:])
            remaining = remaining[:-2]
        if remaining:
            groups.append(remaining)
        groups.reverse()
        formatted = ",".join(groups) + "," + last3

    result = f"₹{formatted}.{decimal_str}"
    return f"-{result}" if is_negative else result


def build_ai_payload(plan: dict) -> dict:
    corpus = plan["corpus"]
    buckets = plan["buckets"]["buckets"]
    glide_path = plan["glide_path"]
    
    # Extract user profile from available data
    first_year = glide_path["yearly_schedule"][0] if glide_path.get("yearly_schedule") else {}
    user_profile = {
        "age": first_year.get("age", "N/A"),
        "retirement_age": glide_path.get("retirement_age", "N/A"),
        "life_expectancy": plan.get("buckets", {}).get("review_age", 0) + 
                          plan.get("buckets", {}).get("retirement_duration_years", 0),
    }

    return {
        "user_profile": user_profile,
        "plan_summary": {
            # Pre-formatted — model copies exactly, never reformats
            "corpus_required":                 format_inr(corpus["corpus_required"]),
            "annual_expense_at_retirement":    format_inr(corpus["annual_expense_at_retirement"]),
            "income_at_retirement":            format_inr(corpus["income_at_retirement"]),
            "net_annual_withdrawal":           format_inr(corpus["net_annual_withdrawal"]),
            "fv_existing_corpus":              format_inr(corpus["fv_existing_corpus"]),
            "fv_existing_sip":                 format_inr(corpus["fv_existing_sip"]),
            "corpus_gap":                      format_inr(corpus["corpus_gap"]),
            "additional_monthly_sip_required": format_inr(corpus["additional_monthly_sip_required"]),
            "sip_stepup_rate_pct":             f"{glide_path.get('sip_stepup_rate_pct', 0):.2f}%",
        },
        "glide_path_summary":  glide_path.get("allocation_bands", []),
        "yearly_sip_schedule": [
            {
                **item,
                "monthly_sip": format_inr(item["monthly_sip"]),
                "sip_to_equity": format_inr(item["sip_to_equity"]),
                "sip_to_debt": format_inr(item["sip_to_debt"])
            }
            for item in glide_path.get("yearly_schedule", [])
        ],
        "bucket_summary": {
            "bucket_1_size": format_inr(buckets["bucket_1"]["size"]),
            "bucket_1_equity": format_inr(buckets["bucket_1"]["equity_amount"]),
            "bucket_1_debt": format_inr(buckets["bucket_1"]["debt_amount"]),
            "bucket_2_size": format_inr(buckets["bucket_2"]["size"]),
            "bucket_2_equity": format_inr(buckets["bucket_2"]["equity_amount"]),
            "bucket_2_debt": format_inr(buckets["bucket_2"]["debt_amount"]),
            "bucket_3_size": format_inr(buckets["bucket_3"]["size"]),
            "bucket_3_equity": format_inr(buckets["bucket_3"]["equity_amount"]),
            "bucket_3_debt": format_inr(buckets["bucket_3"]["debt_amount"]),
        }
    }


def explain_retirement_plan_with_ai(
    retirement_plan: dict,
    user_question: Optional[str] = None
) -> str:
    # Get HF token from environment
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        return "Error: HF_TOKEN not found in environment variables"
    
    # Remove quotes if present in the token
    hf_token = hf_token.strip('"').strip("'")
    
    # Load prompts from file
    prompt_file_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "retirement_agent_prompt.txt"
    )
    
    try:
        with open(prompt_file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
    except FileNotFoundError:
        return f"Error: System prompt file not found at {prompt_file_path}"
    
    # Parse SYSTEM_PROMPT and INITIAL_USER_PROMPT from file
    try:
        # Extract SYSTEM_PROMPT (everything between SYSTEM_PROMPT = """ and the next """)
        system_start = file_content.find('SYSTEM_PROMPT = """') + len('SYSTEM_PROMPT = """')
        system_end = file_content.find('"""', system_start)
        system_prompt_template = file_content[system_start:system_end]
        
        # Extract INITIAL_USER_PROMPT
        initial_start = file_content.find('INITIAL_USER_PROMPT = """') + len('INITIAL_USER_PROMPT = """')
        initial_end = file_content.find('"""', initial_start)
        initial_user_prompt = file_content[initial_start:initial_end]
        
    except Exception as e:
        return f"Error parsing prompt file: {str(e)}"
    
    # Use the default comprehensive prompt if no specific question is provided
    if user_question is None:
        user_question = initial_user_prompt
    
    # Get current date
    current_date = datetime.datetime.now().strftime("%B %d, %Y")
    
    # Build formatted payload with INR formatting
    formatted_payload = build_ai_payload(retirement_plan)
    plan_payload_json = json.dumps(formatted_payload, indent=2)
    
    system_prompt = system_prompt_template.format(
        current_date=current_date,
        plan_payload=plan_payload_json
    )
    
    # Initialize OpenAI client with HuggingFace
    try:
        time_start=datetime.now()
        client = OpenAI(
            base_url="https://router.huggingface.co/v1",
            api_key=hf_token,
        )
        
        # Get AI explanation
        completion = client.chat.completions.create(
            model="MiniMaxAI/MiniMax-M2.5:novita",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_question
                }
            ],
            max_tokens=10000,
            temperature=0.7
        )
        timedelta = datetime.now() - time_start
        logger.info({
            "event": "AI explanation generated for retirement plan",
            "model": "MiniMaxAI/MiniMax-M2.5:novita",
            "time_taken_seconds": timedelta.total_seconds(),
            "user_question_length": len(user_question),
            "response_length": len(completion.choices[0].message.content),
            "input_tokens": completion.choices[0].message.usage.input_tokens if hasattr(completion.choices[0].message.usage, 'input_tokens') else None,
            "output_tokens": completion.choices[0].message.usage.output_tokens if hasattr(completion.choices[0].message.usage, 'output_tokens') else None,
            "total_tokens": completion.choices[0].message.usage.total_tokens if hasattr(completion.choices[0].message.usage, 'total_tokens') else None
        })  
        return completion.choices[0].message.content
    
    except Exception as e:
        logger.info({
            "event": "Error generating AI explanation for retirement plan",
            "model": "MiniMaxAI/MiniMax-M2.5:novita",
            "user_question_length": len(user_question),
            "error": str(e),
        })
        return f"Error generating AI explanation: {str(e)}"
    

def save_retirement_plan(db, user_id: str, plan: dict, retirement_age: int):
    from app.models.db import RetirementPlan
    plan_record = RetirementPlan(
        user_id=user_id,
        plan_data=plan,
        retirement_age=retirement_age
    )
    db.add(plan_record)
    db.commit()
    db.refresh(plan_record)
    return plan_record

#____________________________________One-Time Goal Planning Service____________________________

def one_time_goal(data: OneTimeGoalRequest, user: "User") -> dict:
    # Extract user profile data from database
    monthly_income = user.current_income / 12
    monthly_expenses = user.current_monthly_expenses
    inflation_rate = user.inflation_rate / 100
    income_raise_pct = user.income_raise_pct / 100
    current_age = user.age
    
    # One-time goal feasibility uses a fixed 50% savings cap.
    # `user.savings_pct` is the conflict-engine floor, not the goal-feasibility ceiling.
    savings_cap_pct = 50.0
    
    time_start = datetime.now()
    # Calculate required SIP with step-up
    sip_report = calculate_sip(SIPRequest(
        goal_amount=data.goal_amount,
        years_to_goal=data.years_to_goal,
        pre_ret_return=data.pre_ret_return,
        inflation_rate=user.inflation_rate,  # as percentage
        income_raise_pct=user.income_raise_pct  # as percentage
    ))
    
    goal_target = sip_report["goal_at_target_date"]
    starting_monthly_sip = sip_report["starting_monthly_sip"]
    annual_step_up_pct = sip_report["annual_step_up_pct"]
    
    # Check feasibility against user's disposable income
    feasibility_report = check_feasibility(CheckFeasibilityRequest(
        starting_monthly_sip=starting_monthly_sip,
        annual_step_up_pct=annual_step_up_pct,
        monthly_income=monthly_income,
        income_raise_pct=user.income_raise_pct,
        monthly_expenses=monthly_expenses,
        years_to_goal=int(data.years_to_goal),
        existing_monthly_sip=data.existing_monthly_sip,
        savings_cap_pct=savings_cap_pct
    ))
    
    if not feasibility_report["feasible"]:
        return {
            "status": "infeasible",
            "goal_name": data.goal_name,
            "sip_report": sip_report,
            "feasibility_report": feasibility_report,
            "message": "This goal is not feasible with your current financial profile and assumptions.",
            "suggestion": "Consider either: (1) Extending the timeline, (2) Reducing the goal amount, or (3) Increasing your income/reducing expenses."
        }
    
    # Feasible — now calculate allocation and glide path
    # Map risk tolerance to allocation adjustment
    risk_map = {
        "low": "low",
        "moderate": "moderate", 
        "high": "high"
    }
    risk_level = risk_map.get(data.risk_tolerance.lower(), "moderate")
    
    # Suggest allocation based on time horizon and risk
    allocation = suggest_allocation(SuggestedAllocation(
        years=int(data.years_to_goal),
        risk=risk_level
    ))
    
    equity_allocation = allocation["equity_allocation"]
    debt_allocation = allocation["debt_allocation"]
    
    # Calculate glide path — gradually reduce equity as goal approaches
    # Conservative approach: reduce to 10-20% equity near goal date
    goal_age = current_age + int(data.years_to_goal)
    
    # End equity based on goal proximity: closer goals need more stability
    if data.years_to_goal < 3:
        end_equity = 10.0
    elif data.years_to_goal < 5:
        end_equity = 20.0
    else:
        end_equity = max(equity_allocation - 50, 10.0)
    
    glide_path = calculate_glide_path(GlidePathRequest(
        current_age=current_age,
        goal_age=goal_age,
        start_equity_percent=equity_allocation,
        end_equity_percent=end_equity
    ))
    
    # Calculate FV of existing corpus
    r = data.pre_ret_return /100
    n = data.years_to_goal
    fv_existing_corpus = data.existing_corpus * (1 + r) ** n if data.existing_corpus > 0 else 0.0
    
    time_end=datetime.now()
    logger.info({
        "event": "One-time goal plan computed",
        "time_taken_seconds": (time_end - time_start).total_seconds(),
        "feasible": feasibility_report["feasible"],
        "goal_amount": data.goal_amount,
        "goal_target_at_date": goal_target,
        "starting_monthly_sip": starting_monthly_sip,
        "annual_step_up_pct": annual_step_up_pct,
        "equity_allocation_start": equity_allocation,
        "equity_allocation_end": end_equity
    })
    
    return {
        "status": "feasible",
        "goal_name": data.goal_name,
        "goal_summary": {
            "goal_amount_today": round(data.goal_amount, 2),
            "goal_amount_at_target": round(goal_target, 2),
            "years_to_goal": data.years_to_goal,
            "target_age": goal_age,
            "expected_return_pct": data.pre_ret_return,
            "inflation_adjusted": True
        },
        "sip_plan": {
            "starting_monthly_sip": round(starting_monthly_sip, 2),
            "annual_step_up_pct": round(annual_step_up_pct, 2),
            "existing_monthly_sip": data.existing_monthly_sip,
            "total_first_year_sip": round(starting_monthly_sip + data.existing_monthly_sip, 2),
            "existing_corpus": data.existing_corpus,
            "fv_of_existing_corpus": round(fv_existing_corpus, 2)
        },
        "feasibility": feasibility_report,
        "allocation": {
            "initial_equity_pct": equity_allocation,
            "initial_debt_pct": debt_allocation,
            "final_equity_pct": end_equity,
            "final_debt_pct": 100 - end_equity,
            "risk_profile": data.risk_tolerance
        },
        "glide_path": glide_path
    }
    
def build_onetime_goal_ai_payload(plan: dict) -> dict:

    # Pre-format glide path as explicit string table
    # Forces model to copy text, not reconstruct numbers
    glide_rows = []
    for row in plan["glide_path"]["yearly_allocation_table"]:
        glide_rows.append(
            f"Year {row['year']} (Age {row['age']}): "
            f"equity {row['equity_percent']}%, "
            f"debt {row['debt_percent']}%"
        )
    glide_path_formatted = "\n".join(glide_rows)

    return {
        "goal_name":    plan["goal_name"],
        "status":       plan["status"],
        "goal_summary": {
            "goal_amount_today":     format_inr(plan["goal_summary"]["goal_amount_today"]),
            "goal_amount_at_target": format_inr(plan["goal_summary"]["goal_amount_at_target"]),
            "years_to_goal":         plan["goal_summary"]["years_to_goal"],
            "target_age":            plan["goal_summary"]["target_age"],
            "expected_return_pct":   plan["goal_summary"]["expected_return_pct"],
        },
        "sip_plan": {
            "starting_monthly_sip":  format_inr(plan["sip_plan"]["starting_monthly_sip"]),
            "annual_step_up_pct":    plan["sip_plan"]["annual_step_up_pct"],
            "existing_monthly_sip":  format_inr(plan["sip_plan"]["existing_monthly_sip"]),
            "fv_of_existing_corpus": format_inr(plan["sip_plan"]["fv_of_existing_corpus"]),
        },
        "feasibility": {
            "feasible":           plan["feasibility"]["feasible"],
            "peak_savings_ratio": plan["feasibility"]["peak_savings_ratio"],
            "breach_count":       plan["feasibility"]["breach_count"],
            "first_breach_year":  plan["feasibility"]["first_breach_year"],
            "monthly_shortfall":  format_inr(plan["feasibility"]["monthly_shortfall"]),
            "yearly_summary":     plan["feasibility"]["yearly_summary"],
        },
        "glide_path": {
            "start_equity_percent":   plan["glide_path"]["start_equity_percent"],
            "end_equity_percent":     plan["glide_path"]["end_equity_percent"],
            "total_years":            plan["glide_path"]["total_years"],

            # Pre-formatted string — model copies this directly, no reconstruction
            "yearly_allocation_table_formatted": glide_path_formatted,

            # Keep raw table too for reference
            "yearly_allocation_table": plan["glide_path"]["yearly_allocation_table"]
        }
    }
      
def explain_one_time_goal_with_ai(
    goal_plan: dict,
    user_question: Optional[str] = None
) -> str:
    
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        return "Error: HF_TOKEN not found in environment variables"
    
    # Remove quotes if present in the token
    hf_token = hf_token.strip('"').strip("'")
    
    # Load prompts from file
    prompt_file_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "one_time_agent_prompt.txt"
    )
    
    try:
        with open(prompt_file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
    except FileNotFoundError:
        return f"Error: System prompt file not found at {prompt_file_path}"
    
    # Parse SYSTEM_PROMPT and INITIAL_USER_PROMPT from file
    try:
        # Extract SYSTEM_PROMPT (everything between SYSTEM_PROMPT = """ and the next """)
        system_start = file_content.find('SYSTEM_PROMPT = """') + len('SYSTEM_PROMPT = """')
        system_end = file_content.find('"""', system_start)
        system_prompt_template = file_content[system_start:system_end]
        
        # Extract INITIAL_USER_PROMPT
        if goal_plan["status"] == "feasible":
            initial_prompt= 'ONETIME_GOAL_INITIAL_USER_PROMPT_FEASIBLE = """'
        else:
            initial_prompt= 'ONETIME_GOAL_INITIAL_USER_PROMPT_INFEASIBLE = """'
        initial_start = file_content.find(initial_prompt) + len(initial_prompt)
        initial_end = file_content.find('"""', initial_start)
        initial_user_prompt = file_content[initial_start:initial_end]
        
    except Exception as e:
        return f"Error parsing prompt file: {str(e)}"
    
    # Use the default comprehensive prompt if no specific question is provided
    if user_question is None:
        user_question = initial_user_prompt
    
    # Get current date
    current_date = datetime.datetime.now().strftime("%B %d, %Y")
    
    # Build formatted payload with INR formatting
    formatted_payload = build_onetime_goal_ai_payload(goal_plan)
    plan_payload_json = json.dumps(formatted_payload, indent=2)
    
    
    system_prompt = system_prompt_template.format(
        current_date=current_date,
        plan_payload=plan_payload_json
    )
    
    # Initialize OpenAI client with HuggingFace
    try:
        time_start=datetime.now()
        client = OpenAI(
            base_url="https://router.huggingface.co/v1",
            api_key=hf_token,
        )
        
        # Get AI explanation
        completion = client.chat.completions.create(
            model="MiniMaxAI/MiniMax-M2.5:fastest",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_question
                }
            ],
            max_tokens=10000,
            temperature=0.7
        )
        timedelta = datetime.now() - time_start
        logger.info({
            "event": "AI explanation generated for one time goal plan",
            "model": "MiniMaxAI/MiniMax-M2.5:novita",
            "time_taken_seconds": timedelta.total_seconds(),
            "user_question_length": len(user_question),
            "response_length": len(completion.choices[0].message.content),
            "input_tokens": completion.choices[0].message.usage.input_tokens if hasattr(completion.choices[0].message.usage, 'input_tokens') else None,
            "output_tokens": completion.choices[0].message.usage.output_tokens if hasattr(completion.choices[0].message.usage, 'output_tokens') else None,
            "total_tokens": completion.choices[0].message.usage.total_tokens if hasattr(completion.choices[0].message.usage, 'total_tokens') else None
        }) 
        return completion.choices[0].message.content
    
    except Exception as e:
        logger.info({
            "event": "Error generating AI explanation for one-time goal plan",
            "model": "MiniMaxAI/MiniMax-M2.5:novita",
            "user_question_length": len(user_question),
            "error": str(e),
        })
        return f"Error generating AI explanation: {str(e)}"
    

def save_one_time_goal_plan(db, user_id: str, plan: dict):
    from app.models.db import OneTimeGoalPlan, RecurringGoalPlan

    max_one_time_priority = db.query(OneTimeGoalPlan.priority).filter(
        OneTimeGoalPlan.user_id == user_id,
        OneTimeGoalPlan.is_active == True,
    ).order_by(OneTimeGoalPlan.priority.desc()).first()

    max_recurring_priority = db.query(RecurringGoalPlan.priority).filter(
        RecurringGoalPlan.user_id == user_id,
        RecurringGoalPlan.is_active == True,
    ).order_by(RecurringGoalPlan.priority.desc()).first()

    next_priority = max(
        max_one_time_priority[0] if max_one_time_priority and max_one_time_priority[0] is not None else 1,
        max_recurring_priority[0] if max_recurring_priority and max_recurring_priority[0] is not None else 1,
    ) + 1
    
    # Convert plan to JSON string for storage
    plan_json = json.dumps(plan, default=str)
    
    plan_record = OneTimeGoalPlan(
        user_id=user_id,
        goal_data=plan_json,
        goal_name=plan.get("goal_name", "Unnamed Goal"),
        target_amount=plan.get("goal_summary", {}).get("goal_amount_today", 0.0),
        future_value=plan.get("goal_summary", {}).get("goal_amount_at_target", 0.0),
        monthly_sip_required=plan.get("sip_plan", {}).get("starting_monthly_sip", 0.0),
        time_horizon_years=int(plan.get("goal_summary", {}).get("years_to_goal", 0)),
        status=plan.get("status", "unknown"),
        is_active=True,
        priority=next_priority
    )
    db.add(plan_record)
    db.commit()
    db.refresh(plan_record)
    return plan_record


def save_recurring_goal_plan(db, user_id: str, plan: dict):
    from app.models.db import OneTimeGoalPlan, RecurringGoalPlan

    max_one_time_priority = db.query(OneTimeGoalPlan.priority).filter(
        OneTimeGoalPlan.user_id == user_id,
        OneTimeGoalPlan.is_active == True,
    ).order_by(OneTimeGoalPlan.priority.desc()).first()

    max_recurring_priority = db.query(RecurringGoalPlan.priority).filter(
        RecurringGoalPlan.user_id == user_id,
        RecurringGoalPlan.is_active == True,
    ).order_by(RecurringGoalPlan.priority.desc()).first()

    next_priority = max(
        max_one_time_priority[0] if max_one_time_priority and max_one_time_priority[0] is not None else 1,
        max_recurring_priority[0] if max_recurring_priority and max_recurring_priority[0] is not None else 1,
    ) + 1

    plan_json = json.dumps(plan, default=str)

    # Use first occurrence as quick target amount and planning years for dashboard fields.
    first_occurrence = (plan.get("sip_plan", {}).get("occurrence_plans") or [{}])[0]

    plan_record = RecurringGoalPlan(
        user_id=user_id,
        goal_data=plan_json,
        goal_name=plan.get("goal_name", "Unnamed Goal"),
        target_amount=first_occurrence.get("cost_at_target", 0.0),
        future_value=first_occurrence.get("cost_at_target", 0.0),
        monthly_sip_required=plan.get("sip_plan", {}).get("total_monthly_sip", 0.0),
        time_horizon_years=int(plan.get("goal_summary", {}).get("total_planning_years", 0)),
        status=plan.get("status", "unknown"),
        is_active=True,
        priority=next_priority,
    )
    db.add(plan_record)
    db.commit()
    db.refresh(plan_record)
    return plan_record

#____________________Recurrin Goal Planning Service___________________________

def compute_occurrence_costs(data: RecurringGoalRequest) -> list[dict]:
    i = data.goal_inflation_pct / 100

    occurrences = []
    for k in range(1, data.num_occurrences + 1):
        years_to_k = data.years_to_first + (k - 1) * data.frequency_years
        cost_at_k  = data.current_cost * (1 + i) ** years_to_k

        occurrences.append({
            "occurrence":     k,
            "years_from_now": years_to_k,
            "cost_at_target": round(cost_at_k, 2)
        })

    return occurrences


def compute_sip_for_occurrence(
    target_corpus:    float,
    years_to_goal:    int,
    r:                float,    # annual return
    s:                float,    # real step-up rate (Fisher derived)
) -> float:

    if years_to_goal <= 0:
        return 0.0

    if abs(r - s) < 1e-9:
        annual_sip = target_corpus / (
            years_to_goal * (1 + r) ** (years_to_goal - 1)
        )
    else:
        annual_sip = (
            target_corpus * (r - s)
            / (((1 + r) ** years_to_goal - (1 + s) ** years_to_goal)
               * (1 + r / 12))
        )

    return annual_sip / 12   # monthly

def apply_existing_corpus(
    occurrence_costs: list[dict],
    existing_corpus:  float,
    r:                float,
    years_to_first:   int
) -> list[dict]:
    
    if existing_corpus <= 0:
        return occurrence_costs

    fv_corpus = existing_corpus * (1 + r) ** years_to_first

    adjusted = []
    for occ in occurrence_costs:
        if occ["occurrence"] == 1:
            adjusted_cost = max(0, occ["cost_at_target"] - fv_corpus)
            adjusted.append({**occ, "cost_at_target": round(adjusted_cost, 2),
                             "fv_existing_corpus": round(fv_corpus, 2)})
        else:
            adjusted.append({**occ, "fv_existing_corpus": 0.0})

    return adjusted

def compute_recurring_goal(data: RecurringGoalRequest) -> dict:
    r = data.expected_return_pct / 100
    i = data.goal_inflation_pct  / 100
    g = data.income_raise_pct    / 100
    s = ((1 + g) / (1 + i)) - 1     # derived real step-up rate
    
    if data.years_to_first <= 0:
        logger.info({
            "event":"Recurring goal",
            "status": "infeasible",
            "reason": "Goal is in the past or immediate. SIP not suitable."
        })  
        return {
            "status": "infeasible",
            "message": "If the goal is this year, use a lump sum, not a SIP."
        }
        
    time_start=datetime.now()
    # Step 1: cost at each occurrence
    occurrences = compute_occurrence_costs(data)

    # Step 2: adjust for existing corpus
    occurrences = apply_existing_corpus(
        occurrences,
        data.existing_corpus,
        r,
        data.years_to_first
    )

    # Step 3: SIP per occurrence
    total_monthly_sip = 0.0
    occurrence_plans  = []

    for occ in occurrences:
        monthly_sip = compute_sip_for_occurrence(
            target_corpus  = occ["cost_at_target"],
            years_to_goal  = occ["years_from_now"],
            r              = r,
            s              = s
        )
        total_monthly_sip += monthly_sip

        occurrence_plans.append({
            **occ,
            "monthly_sip": round(monthly_sip, 2)
        })

    # Step 4: feasibility across accumulation years
    feasibility = check_feasibility(CheckFeasibilityRequest(
        starting_monthly_sip = total_monthly_sip,
        annual_step_up_pct   = round(s * 100, 4),
        monthly_income       = data.monthly_income,
        income_raise_pct     = data.income_raise_pct,
        monthly_expenses     = data.monthly_expenses,
        years_to_goal        = data.years_to_first +
                               (data.num_occurrences - 1) * data.frequency_years,
        existing_monthly_sip = 0.0,
        savings_cap_pct      = 50.0
    ))

    # Step 5: glide path for each occurrence
    glide_paths = []
    
    for occ in occurrence_plans:
        years_to_occurrence = occ["years_from_now"]
        
        # Skip if occurrence is immediate (0 years) or has no SIP required
        if years_to_occurrence <= 0 or occ["monthly_sip"] <= 0:
            continue
        
        # Get allocation based on time horizon for this occurrence
        allocation = suggest_allocation(SuggestedAllocation(
            years=years_to_occurrence,
            risk="moderate"
        ))
        
        equity_allocation = allocation["equity_allocation"]
        
        # End equity based on goal proximity: closer goals need more stability
        if years_to_occurrence < 3:
            end_equity = 10.0
        elif years_to_occurrence < 5:
            end_equity = 20.0
        else:
            end_equity = max(equity_allocation - 50, 10.0)
        
        # Calculate glide path for this occurrence
        glide_path = calculate_glide_path(GlidePathRequest(
            current_age          = 0,      # use years, not age
            goal_age             = years_to_occurrence,
            start_equity_percent = equity_allocation,
            end_equity_percent   = end_equity
        ))
        
        glide_paths.append({
            "occurrence":      occ["occurrence"],
            "years_from_now":  years_to_occurrence,
            "glide_path":      glide_path
        })

    status = "feasible" if feasibility["feasible"] else "infeasible"
    
    time_end=datetime.now()
    logger.info({
        "event": "Recurring goal plan computed",
        "time_taken_seconds": (time_end - time_start).total_seconds(),
        "status": status,
        "total_monthly_sip": total_monthly_sip,
        "feasible": feasibility["feasible"],
        "num_occurrences": data.num_occurrences,
        "years_to_first_occurrence": data.years_to_first
    })
    
    return {
        "status":             status,
        "goal_name":          data.goal_name,
        "goal_summary": {
            "current_cost":         data.current_cost,
            "goal_inflation_pct":   data.goal_inflation_pct,
            "frequency_years":      data.frequency_years,
            "num_occurrences":      data.num_occurrences,
            "years_to_first":       data.years_to_first,
            "total_planning_years": data.years_to_first +
                                    (data.num_occurrences - 1) * data.frequency_years
        },
        "sip_plan": {
            "total_monthly_sip":  round(total_monthly_sip, 2),
            "sip_stepup_rate_pct": round(s * 100, 4),
            "occurrence_plans":   occurrence_plans
        },
        "feasibility": feasibility,
        "glide_paths":  glide_paths
    }
    

    
def explain_recurring_goal_with_ai(
    goal_plan: dict,
    user_question: Optional[str] = None
) -> str:
    
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        return "Error: HF_TOKEN not found in environment variables"
    
    # Remove quotes if present in the token
    hf_token = hf_token.strip('"').strip("'")
    
    # Load prompts from file
    prompt_file_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "one_time_agent_prompt.txt"
    )
    
    try:
        with open(prompt_file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
    except FileNotFoundError:
        return f"Error: System prompt file not found at {prompt_file_path}"
    
    # Parse SYSTEM_PROMPT and INITIAL_USER_PROMPT from file
    try:
        # Extract SYSTEM_PROMPT (everything between SYSTEM_PROMPT = """ and the next """)
        system_start = file_content.find('RECURRING_GOAL_SYSTEM_PROMPT = """') + len('RECURRING_GOAL_SYSTEM_PROMPT = """')
        system_end = file_content.find('"""', system_start)
        system_prompt_template = file_content[system_start:system_end]
        
        # Extract INITIAL_USER_PROMPT
        if goal_plan["status"] == "feasible":
            initial_prompt= 'RECURRING_GOAL_INITIAL_USER_PROMPT_FEASIBLE = """'
        else:
            initial_prompt= 'RECURRING_GOAL_INITIAL_USER_PROMPT_INFEASIBLE = """'
        initial_start = file_content.find(initial_prompt) + len(initial_prompt)
        initial_end = file_content.find('"""', initial_start)
        initial_user_prompt = file_content[initial_start:initial_end]
        
    except Exception as e:
        return f"Error parsing prompt file: {str(e)}"
    
    # Use the default comprehensive prompt if no specific question is provided
    if user_question is None:
        user_question = initial_user_prompt
    
    # Get current date
    current_date = datetime.datetime.now().strftime("%B %d, %Y")
    
    # Build formatted payload with INR formatting
    formatted_payload = build_onetime_goal_ai_payload(goal_plan)
    plan_payload_json = json.dumps(formatted_payload, indent=2)
    
    
    system_prompt = system_prompt_template.format(
        current_date=current_date,
        plan_payload=plan_payload_json
    )
    
    # Initialize OpenAI client with HuggingFace
    try:
        time_start=datetime.now()
        client = OpenAI(
            base_url="https://router.huggingface.co/v1",
            api_key=hf_token,
        )
        
        # Get AI explanation
        completion = client.chat.completions.create(
            model="MiniMaxAI/MiniMax-M2.5:fastest",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_question
                }
            ],
            max_tokens=10000,
            temperature=0.1
        )
        timedelta = datetime.now() - time_start
        logger.info({
            "event": "AI explanation generated for recurrung goal plan",
            "model": "MiniMaxAI/MiniMax-M2.5:novita",
            "time_taken_seconds": timedelta.total_seconds(),
            "user_question_length": len(user_question),
            "response_length": len(completion.choices[0].message.content),
            "input_tokens": completion.choices[0].message.usage.input_tokens if hasattr(completion.choices[0].message.usage, 'input_tokens') else None,
            "output_tokens": completion.choices[0].message.usage.output_tokens if hasattr(completion.choices[0].message.usage, 'output_tokens') else None,
            "total_tokens": completion.choices[0].message.usage.total_tokens if hasattr(completion.choices[0].message.usage, 'total_tokens') else None
        }) 
        return completion.choices[0].message.content
    
    except Exception as e:
        logger.info({
            "event": "Error generating AI explanation for recurring plan",
            "model": "MiniMaxAI/MiniMax-M2.5:novita",
            "user_question_length": len(user_question),
            "error": str(e),
        })
        return f"Error generating AI explanation: {str(e)}"
    


