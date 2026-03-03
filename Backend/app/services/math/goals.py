from typing import Optional
from app.models.user import Retirement, BucketAllocation
import os
from openai import OpenAI
import datetime
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


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
        "annual_expense_at_retirement": round(annual_expense_at_retirement, 2),
        "income_at_retirement": round(income_at_retirement, 2),
        "net_annual_withdrawal": round(net_withdrawal, 2),
        "corpus_required": round(corpus_required, 2),
        "fv_existing_corpus": round(fv_corpus, 2),
        "fv_existing_sip": round(fv_sip, 2),
        "corpus_gap": round(corpus_gap, 2),
        "additional_monthly_sip_required": round(max(additional_sip_required, 0), 2),
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
    W = net_annual_withdrawal
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
        "corpus_required":    round(corpus_required, 2),
        "total_allocated":    round(total_allocated, 2),
        "unallocated_buffer": round(unallocated, 2),  # should be ~0 or small positive
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
        
        return completion.choices[0].message.content
    
    except Exception as e:
        return f"Error generating AI explanation: {str(e)}"