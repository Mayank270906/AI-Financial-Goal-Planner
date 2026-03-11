# GoalPath — Financial Planning Backend

A production-grade FastAPI backend that provides deterministic financial planning calculations, multi-agent AI explanations, and a priority-aware conflict engine — all in one service.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Tech Stack](#2-tech-stack)
3. [System Architecture](#3-system-architecture)
4. [Directory Structure](#4-directory-structure)
5. [Authentication & Security](#5-authentication--security)
6. [Database Schema](#6-database-schema)
7. [API Reference](#7-api-reference)
8. [Math Engine](#8-math-engine)
   - [Retirement Planning](#81-retirement-planning)
   - [One-Time Goal Planning](#82-one-time-goal-planning)
   - [Recurring Goal Planning](#83-recurring-goal-planning)
   - [General Calculation Utilities](#84-general-calculation-utilities)
9. [Multi-Agent Architecture](#9-multi-agent-architecture)
   - [Design Philosophy](#91-design-philosophy)
   - [Retirement Agent](#92-retirement-agent)
   - [One-Time Goal Agent](#93-one-time-goal-agent)
   - [Recurring Goal Agent](#94-recurring-goal-agent)
   - [Numeric Containment Rule](#95-numeric-containment-rule)
10. [Conflict Engine](#10-conflict-engine)
    - [Overview](#101-overview)
    - [Corridor Model](#102-corridor-model)
    - [Priority Ordering](#103-priority-ordering)
    - [Surplus Waterfall](#104-surplus-waterfall)
    - [Year-by-Year Simulation](#105-year-by-year-simulation)
    - [Conflict Results Storage](#106-conflict-results-storage)
11. [Structured Logging](#11-structured-logging)
12. [Environment & Configuration](#12-environment--configuration)
13. [Running Locally with Docker](#13-running-locally-with-docker)
14. [Deployment on Render](#14-deployment-on-render)
15. [Running Tests](#15-running-tests)

---

## 1. Project Overview

GoalPath is a personal financial planning engine that helps users model, compute, and understand their financial goals. It handles three distinct goal types — retirement, one-time purchases, and recurring expenditures — and runs a real-time conflict engine after every goal save to ensure the user's full portfolio of goals remains fundable within their income constraints.

The AI layer sits on top of the math layer and is deliberately separated from it. Three specialised AI agents explain pre-computed plans in plain language. They are architecturally forbidden from performing any arithmetic; every number they reference must come verbatim from the JSON payload produced by the math engine.

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI (Python 3.11) |
| ASGI server | Uvicorn with standard extras |
| ORM | SQLAlchemy 2.x |
| Database | Supabase PostgreSQL (via `psycopg2-binary`) |
| Auth | JWT (HS256) via `authlib` + `passlib`/`bcrypt` |
| AI agents | OpenAI SDK |
| Validation | Pydantic v2 |
| Logging | Structured JSON (`JSONFormatter`) |
| Containerisation | Docker |
| Hosting | Render (Web Service) |
| Testing | pytest — unit, integration, e2e smoke |

---

## 3. System Architecture

```
                        ┌─────────────────────────────────────────────────┐
                        │                  FastAPI App                     │
                        │                                                  │
                        │   /auth      /user     /goals    /calculation    │
                        └──────┬──────────┬──────────┬──────────┬─────────┘
                               │          │          │          │
                    ┌──────────▼──┐  ┌────▼────┐  ┌─▼──────────▼──────────┐
                    │  Auth Route │  │  User   │  │     Goals Route        │
                    │  login,     │  │  CRUD   │  │  retirement /          │
                    │  profile    │  │         │  │  one_time_goal /       │
                    └──────┬──────┘  └────┬────┘  │  recurring_goal /      │
                           │              │       │  explain_*             │
                    ┌──────▼──────────────▼────┐  └────────────┬───────────┘
                    │   SQLAlchemy ORM          │               │
                    │   Supabase PostgreSQL     │               │
                    └───────────────────────────┘      ┌────────▼─────────────┐
                                                        │   Math Engine         │
                                                        │  services/math/       │
                                                        │  ├─ goals.py          │
                                                        │  ├─ calculation.py    │
                                                        │  └─ conflict_engine.py│
                                                        └────────┬─────────────┘
                                                                 │
                                                  ┌──────────────▼──────────────────┐
                                                  │   Conflict Engine (auto-runs)    │
                                                  │   Corridor check → Waterfall     │
                                                  │   → ConflictResults saved to DB  │
                                                  └──────────────┬──────────────────┘
                                                                 │
                                          ┌──────────────────────▼──────────────────────┐
                                          │             AI Agent Layer (OpenAI)          │
                                          │  Retirement Agent | One-Time | Recurring     │
                                          │  Explain-only — never compute, never guess   │
                                          └─────────────────────────────────────────────┘
```

Every goal-creation endpoint follows this invariant pipeline:

```
Form input → Pydantic validation → Math engine → Save to DB → Conflict engine → Return plan
```

The AI explanation agents are invoked separately on demand.

---

## 4. Directory Structure

```
Backend/
├── app/
│   ├── main.py                  # FastAPI app factory, router registration, startup event
│   ├── databse.py               # DB engine, session factory, URL normalisation
│   ├── models/
│   │   └── db.py                # All 6 SQLAlchemy ORM models
│   ├── routes/
│   │   ├── auth.py              # /auth — login, profile, token decode
│   │   ├── user.py              # /user — registration, CRUD, onboarding
│   │   ├── goals.py             # /goals — retirement, one-time, recurring, explain
│   │   └── calaculation.py      # /calculation — utility math endpoints
│   ├── schemas/
│   │   ├── user.py              # Retirement, CreateUser, UpdateUser, BucketAllocation
│   │   ├── goals.py             # OneTimeGoalRequest, RecurringGoalRequest
│   │   └── calculation.py       # FutureValue, SIPRequest, BlendedReturn, etc.
│   ├── services/
│   │   ├── auth.py              # JWT creation and verification (authlib)
│   │   ├── utils.py             # bcrypt password hashing and verification
│   │   ├── retirement_agent_prompt.txt   # System prompt — Retirement AI Agent
│   │   ├── one_time_agent_prompt.txt     # System prompt — One-Time Goal AI Agent
│   │   ├── recurring_agent_prompt.txt    # System prompt — Recurring Goal AI Agent
│   │   └── math/
│   │       ├── goals.py         # Core goal math: corpus, SIP, bucket, glide path
│   │       ├── calculation.py   # Utility math: FV, SIP, blended return, feasibility
│   │       └── conflict_engine.py  # Corridor model, waterfall, simulation
│   └── utils/
│       └── log_format.py        # JSONFormatter for structured logging
├── tests/
│   ├── conftest.py
│   ├── unit_test/
│   │   ├── test_calculation.py
│   │   ├── test_one_time_goal.py
│   │   └── test_retirement.py
│   └── integration_test/
│       ├── test_calculations.py
│       ├── test_one_time_goal.py
│       └── test_retirement.py
├── test_e2e_smoke.py
├── requirements.txt
└── .dockerignore
```

---

## 5. Authentication & Security

### JWT Flow

Authentication uses the OAuth2 password grant (username/password → Bearer token).

```
POST /auth/login
  Content-Type: application/x-www-form-urlencoded
  Body: username=<email>&password=<password>

Response: { "access_token": "<jwt>", "token_type": "bearer" }
```

Subsequent requests must include:
```
Authorization: Bearer <access_token>
```

### Implementation Details

- **Token creation** (`app/services/auth.py`): `authlib.jose.jwt.encode()` — HS256 algorithm, configurable expiry via `ACCESS_TOKEN_EXPIRE_MINUTES` env var (default 30 minutes).
- **Token verification** (`verify_tokens`): `jwt.decode()` + `claims.validate()` — raises HTTP 401 on any `JoseError`.
- **Password hashing** (`app/services/utils.py`): `passlib.CryptContext` with `bcrypt` scheme.
- **User lookup** (`get_current_user`): resolves the JWT `sub` claim against `User.id` first, then `User.email` as fallback. Raises HTTP 401 if user is not found.

### Environment Variables for Auth

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | JWT signing secret | **Required** |
| `ALGORITHM` | JWT algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token TTL in minutes | `30` |

---

## 6. Database Schema

All tables are auto-created at startup via `Base.metadata.create_all(bind=engine)`. All primary keys are UUID strings (36 characters).

### `users`
| Column | Type | Notes |
|---|---|---|
| `id` | String(36) PK | UUID |
| `full_name` | String | |
| `email` | String | Unique |
| `phone_number` | String | |
| `hashed_password` | String | bcrypt |
| `marital_status` | String | `Single` / `Married` |
| `age` | Integer | |
| `current_income` | Float | Annual |
| `income_raise_pct` | Float | |
| `current_monthly_expenses` | Float | |
| `inflation_rate` | Float | |
| `spouse_age` | Float | Nullable |
| `spouse_income` | Float | Nullable |
| `spouse_income_raise_pct` | Float | Nullable |
| `savings_pct` | Float | Default 20.0 — corridor floor |
| `buffer_pct` | Float | Default 10.0 — corridor buffer |
| `onboarding_complete` | Boolean | |
| `onboarding_step` | Integer | |

### `retirement_plans`
Stores the full computed retirement plan as a JSON `plan_data` column. Foreign key → `users.id`.

### `goal_plans`
Generic goal container. Foreign key → `users.id`.

### `one_time_goal_plans`
Stores full one-time goal plan JSON. Foreign key → `users.id`.

### `recurring_goal_plans`
Stores full recurring goal plan JSON. Foreign key → `users.id`.

### `conflict_results`
| Column | Type | Notes |
|---|---|---|
| `id` | String(36) PK | UUID |
| `user_id` | String(36) FK | → `users.id` |
| `result` | JSON | Full conflict engine output |
| `is_latest` | Boolean | Only one record is `True` per user at any time |
| `created_at` | DateTime | |

On every conflict engine run, all previous records for that user are marked `is_latest = False` before the new result is inserted.

---

## 7. API Reference

### Auth — `/auth`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/login` | No | Exchange credentials for a Bearer token |
| GET | `/auth/profile` | Yes | Return the authenticated user's profile |

### User — `/user`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/user/register` | No | Create a new user account |
| GET | `/user/me` | Yes | Fetch own user record |
| PATCH | `/user/update` | Yes | Update financial profile fields |

### Goals — `/goals`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/goals/retirement` | Yes | Compute and save a retirement plan |
| POST | `/goals/explain_retirement_plan` | Yes | AI explanation of a retirement plan |
| POST | `/goals/one_time_goal` | Yes | Compute and save a one-time goal plan |
| POST | `/goals/explain_one_time_goal` | Yes | AI explanation of a one-time goal plan |
| POST | `/goals/recurring_goal` | Yes | Compute and save a recurring goal plan |
| GET | `/goals/profile_overview` | Yes | Aggregated view of all goals + conflict status |

> All goal-creation endpoints (`POST /retirement`, `POST /one_time_goal`, `POST /recurring_goal`) automatically run the conflict engine and save the result before returning the plan.

### Calculation — `/calculation`

Utility math endpoints that operate statelessly on the provided inputs and return results immediately without touching the database.

| Method | Path | Description |
|---|---|---|
| POST | `/calculation/future_value` | Compound-growth future value |
| POST | `/calculation/blended_return` | Weighted equity/debt blended return |
| POST | `/calculation/required_annual_saving` | Annual saving required to reach a future value |
| POST | `/calculation/suggest_allocation` | Equity/debt split by horizon and risk tolerance |
| POST | `/calculation/check_feasibility` | Year-by-year SIP feasibility against income cap |
| POST | `/calculation/sip` | Monthly SIP required for a target corpus |
| POST | `/calculation/glide_path` | Pre-retirement equity glide path schedule |

---

## 8. Math Engine

The math engine is implemented in pure Python with no external financial libraries. All computations are deterministic and reproducible. Logging is emitted at each calculation step with timing information.

### 8.1 Retirement Planning

**File**: `app/services/math/goals.py`

#### Step 1 — Feasibility Check (`check_feasibility_retirement`)

Before computing any plan, the engine validates that the required SIP does not exceed 50% of total household income in any accumulation year.

- Iterates year by year from today to retirement.
- User income grows at `income_raise_pct`; spouse income (if married) grows at `spouse_income_raise_pct`.
- SIP steps up at the derived real rate: `s = ((1 + g) / (1 + i)) - 1`, where `g` = income growth, `i` = inflation.
- Returns `feasible: false` with a `failure` object pointing to the first breach year if the cap is exceeded.

#### Step 2 — Corpus Computation (`compute_retirement_corpus`)

Calculates the retirement corpus required and the additional monthly SIP needed to reach it.

Key formulas:

| Quantity | Formula |
|---|---|
| Real post-retirement return | `rpr = ((1 + r_post) / (1 + i)) - 1` |
| Annual net withdrawal at retirement | `W = (net_expense - pension_income) × (1 + i)^n_acc` |
| Corpus required (growing annuity) | `C = W × (1 - ((1+i)/(1+r_post))^n_ret) / (r_post - i)` |
| FV of existing corpus | `FV_c = corpus × (1 + rpr)^n_acc` |
| FV of existing SIP (step-up annuity) | `FV_s = SIP_annual × ((1+rpr)^n - (1+s)^n) / (rpr - s)` |
| Corpus gap | `gap = C - FV_c - FV_s` |
| Additional monthly SIP | Derived from gap using step-up SIP inverse formula |

where `n_acc` = years to retirement, `n_ret` = retirement duration (life expectancy - retirement age).

#### Step 3 — Bucket Strategy (`compute_bucket_strategy`)

Post-retirement corpus allocation across three time-segregated buckets:

| Bucket | Purpose | Horizon | Equity | Debt |
|---|---|---|---|---|
| Bucket 1 — Stability | Immediate withdrawals, no market exposure | Years 1–3 | 0% | 100% |
| Bucket 2 — Moderate Growth | Replenishes Bucket 1 | Years 4–10 | 10–30%* | 70–90%* |
| Bucket 3 — Long-Term Growth | Untouched for 10+ years, long-horizon growth engine | Years 11 → EOL | 40–70%* | 30–60%* |

*Glide path adjustment applied based on age at review (see below).

Bucket sizing:
- B1 = 3 × first-year withdrawal amount
- B2 = sum of inflation-grown withdrawals for years 4–10 (geometric sum)
- B3 = remaining corpus after B1 and B2

If the total corpus is too small to fill all three buckets, B1 is preserved in full, B2 is compressed to absorb the shortfall, and B3 receives nothing.

**Refill rules** (embedded in the plan output):
- B1 is refilled from B2's debt portion when B1 drops below one year of expenses.
- B2 is refilled from B3 only after equity has recovered from a downturn.
- During a market downturn, equity is never sold; the user lives off B1 cash reserves.

#### Step 4 — Pre-Retirement Glide Path (`compute_pre_retirement_glide_path`)

Produces a year-by-year schedule of SIP amounts and equity/debt allocation ratios for the accumulation phase. Equity allocation starts high (up to 80%) and reduces as the user approaches retirement, shifting to capital preservation in the final years. The schedule animates the full transition from aggressive growth to conservative pre-retirement positioning.

---

### 8.2 One-Time Goal Planning

**File**: `app/services/math/goals.py` — `one_time_goal()`

A one-time goal is any significant future expenditure: a car, a house down payment, a child's education, a wedding, or a foreign trip.

**Calculation flow:**
1. Inflate the today's-cost amount to the target date using the configured inflation rate.
2. Compute the future value of any existing corpus and existing monthly SIP contribution.
3. Calculate the gap between the inflated goal amount and existing resources.
4. Derive the required monthly SIP to close the gap using the standard SIP future value formula.
5. Apply `suggest_allocation` to recommend an equity/debt split based on the time horizon and the user's declared risk tolerance.
6. Run a year-by-year feasibility check (same SIP-to-income ratio logic as retirement).

The plan output includes a `status` field — `feasible` or `infeasible` — and a detailed SIP plan with annual step-up rates.

---

### 8.3 Recurring Goal Planning

**File**: `app/services/math/goals.py` — `compute_recurring_goal()`

A recurring goal repeats at a fixed frequency: annual travel, a medical procedure every few years, school fees, or family events.

**Key characteristics:**
- Every future occurrence costs more than the previous due to **goal-specific inflation** (which may differ from general inflation).
- The engine creates a **separate sinking fund SIP** for each occurrence, running simultaneously from today until that occurrence's due date.
- Each occurrence's SIP is independently sized to fund that specific inflated cost.
- The total monthly burden is the sum of all active occurrence SIPs in any given month.

**Plan output structure** — `occurrence_plans[]`:
Each occurrence gets its own entry containing the inflated cost at that future date and the monthly SIP required to fund it. The total SIP at any point in time is the sum of all SIPs whose horizon has not yet been reached.

---

### 8.4 General Calculation Utilities

**File**: `app/services/math/calculation.py`

| Function | Description |
|---|---|
| `future_value_goal` | Standard compound growth: `FV = P × (1 + r)^n` |
| `blended_return` | Weighted average of equity and debt returns |
| `required_annual_saving` | Annual saving needed to reach a future value using the standard sinking fund formula |
| `suggest_allocation` | Time-and-risk-based equity allocation: < 3 years → 20%; 3–7 years → 50%; > 7 years → 70%; adjusted ±20% for risk tolerance |
| `check_feasibility` | Year-by-year SIP-to-disposable-income ratio check with configurable savings cap |
| `calculate_sip` | Monthly SIP required for a target corpus: `SIP = PV × r / (1 - (1+r)^-n)` |
| `calculate_glide_path` | Generic glide path schedule for any horizon |

---

## 9. Multi-Agent Architecture

### 9.1 Design Philosophy

The AI layer is architecturally isolated from the math layer. The separation is enforced by design:

```
Math Engine             AI Agent
──────────              ──────────
Computes numbers  →     Receives JSON payload
Saves results     →     Reads only from payload
Returns to API    →     Explains in plain language
                        NEVER recomputes
                        NEVER estimates
                        NEVER guesses
```

Each goal type has its own dedicated agent with a bespoke system prompt stored in a `.txt` file in `app/services/`. The agents are invoked via the OpenAI SDK with the plan JSON and an optional user question.

Why separate agents per goal type? The reasoning structure and vocabulary differ significantly across goal types. Retirement plans require explaining corpus dynamics, bucket strategy, and decades-long glide paths. One-time goals focus on a single future event and its SIP. Recurring goals require explaining layered, simultaneous sinking funds. One generic agent would result in misaligned explanations.

### 9.2 Retirement Agent

- **Prompt file**: `app/services/retirement_agent_prompt.txt`
- **Invocation function**: `explain_retirement_plan_with_ai(retirement_plan: dict, user_question: Optional[str])`
- **Route**: `POST /goals/explain_retirement_plan`
- **Identity**: GoalPath AI — a retirement and financial planning guide

**Explanation scope** (sections the agent is authorised to discuss):
1. Corpus Summary — target, gap, existing contributions, and what closing the gap requires
2. SIP & Step-Up — why the SIP amount is what it is, why it steps up annually, asset-class differences (no product names)
3. Pre-retirement Glide Path — why equity starts high and reduces, what each allocation band means
4. Bucket Strategy — the three-bucket post-retirement structure, refill rules, market-downturn behaviour
5. Feasibility — what the 50% savings ratio cap means and what the plan assumes about the user's income trajectory

### 9.3 One-Time Goal Agent

- **Prompt file**: `app/services/one_time_agent_prompt.txt`
- **Invocation function**: `explain_one_time_goal_with_ai(goal_plan: dict, user_question: Optional[str])`
- **Route**: `POST /goals/explain_one_time_goal`
- **Identity**: GoalPath AI — a goal-based financial planning guide

The agent reads the plan's `status` field (`feasible` / `infeasible`) before composing any response and follows entirely different explanation paths for each case:
- **Feasible**: walks through goal summary (today's cost vs. inflated cost), SIP plan (starting SIP, step-up, existing corpus contribution), and allocation rationale.
- **Infeasible**: explains the specific constraint that was breached, what the shortfall means, and what options exist (higher SIP, longer horizon, lower goal amount) — without computing any revised figures.

### 9.4 Recurring Goal Agent

- **Prompt file**: `app/services/recurring_agent_prompt.txt`
- **Invocation function**: part of `compute_recurring_goal()` return value processing
- **Identity**: GoalPath AI — recurring goal planning guide

This agent has extra explanation scope around the layered sinking-fund model. It explains why each future occurrence has its own dedicated SIP and how the total monthly burden evolves as occurrences are funded and their SIPs expire.

### 9.5 Numeric Containment Rule

All three agents share the most critical architectural constraint: **Numeric Containment**.

```
AGENTS MUST:
  ✓ Reference ONLY numbers that appear explicitly in the JSON payload
  ✓ Copy all INR values exactly as formatted — character by character
  ✓ Present figures in their original time period (annual stays annual)

AGENTS MUST NOT:
  ✗ Perform any arithmetic on payload values
  ✗ Add, subtract, multiply, or divide any two figures
  ✗ Convert between time periods (monthly ↔ annual)
  ✗ Estimate, approximate, or extrapolate any value
  ✗ Express one figure as a percentage of another
  ✗ Introduce any number not present in the payload
  ✗ Use words like "approximately", "roughly", or "about" before a figure
  ✗ Reformat INR values (₹12,05,88,890.81 must stay exactly that)
```

This rule exists because the agents operate through a language model, which can silently introduce numeric errors. All correct numbers already exist in the payload; the agent's only job is to explain their meaning in context.

Every agent response ends with a mandatory disclosure: the plan is based on stated assumptions, markets are not guaranteed, and the system is not SEBI-registered.

---

## 10. Conflict Engine

### 10.1 Overview

The conflict engine is a deterministic simulation that runs automatically after every goal save. It evaluates whether the user's entire portfolio of goals is simultaneously fundable within their income, flags overcommitment, and assigns funding status to each goal based on priority.

**File**: `app/services/math/conflict_engine.py`
**Entry point**: `run_and_save_conflict_engine(user_id, db)` — an async function called from every goal route.

### 10.2 Corridor Model

The corridor model defines a safe savings zone as a percentage of **disposable income** (income minus fixed expenses). The corridor has three configurable bands:

```
Disposable Income
   100% ──────────────────────────────────────── (all income)
    70% ──── CEILING ────────────────────────── (over_invested threshold)
    63% ──── APPROACHING_CEILING warning ─────── (90% of ceiling)
    20% ──── FLOOR ──────────────────────────── (under_saving threshold)
     0% ──── ZERO ───────────────────────────── (critical: no disposable income)
```

**Alert levels**:

| Status | Alert Level | Condition |
|---|---|---|
| `over_invested` | critical | Total SIP > 70% of disposable income |
| `approaching_ceiling` | warning | Total SIP > 63% of disposable income |
| `under_saving` | advisory | Total SIP < 20% of disposable income |
| `in_corridor` | none | 20% ≤ Total SIP ≤ 63% |
| (zero income) | critical | Disposable income = 0 but SIPs exist |

The `savings_pct` (floor) and `buffer_pct` defaults are 20% and 10% respectively, stored on the `User` model and configurable per user.

### 10.3 Priority Ordering

Retirement is always assigned **priority rank 1** — it cannot be demoted. All other goals (one-time and recurring) receive ranks 2+ based on the user-supplied `priority_order` list. Goals not present in the priority list fall to rank 99.

```python
retirement → priority_rank = 1  (hard-coded, immutable)
goal_A     → priority_rank = 2  (first in priority_order)
goal_B     → priority_rank = 3  (second in priority_order)
goal_C     → priority_rank = 99 (not listed)
```

This ordering governs which goals receive funds first in the surplus waterfall.

### 10.4 Surplus Waterfall

The waterfall determines how the user's disposable income is allocated across all goals in the simulation's first year.

**Allocation sequence:**
```
Disposable Income
  └── Reserved: savings_pct (default 20%) → long-term general savings
  └── Reserved: buffer_pct (default 10%)  → emergency buffer
  └── Remaining pool → distributed by priority rank:
        Priority 1 (Retirement) → funded first
        Priority 2 (next goal)  → funded second
        ...
        Pool exhausted → remaining goals are deferred
```

Each goal can have one of three waterfall statuses:

| Status | Meaning |
|---|---|
| `funded` | Full SIP met from the remaining pool |
| `partially_funded` | Pool had some money remaining but not enough for the full SIP |
| `deferred` | Pool was exhausted; goal receives no funding this period |

### 10.5 Year-by-Year Simulation

`compute_max_horizon` scans all active goals to find the longest planning horizon. The simulation then runs from year 1 through that maximum horizon.

For each simulation year:
1. `compute_all_goal_sips_for_year` — projects each goal's SIP, stepped up by its configured annual increase rate for that year.
2. `prioritised_goal` — assembles prioritised goal list with that year's SIPs.
3. `compute_corridor_status` — checks whether total SIP is inside the safe corridor.
4. `compute_surplus_waterfall` — allocates the disposable pool across goals in priority order.

This produces a year-by-year table showing funding status for every goal across the full planning horizon.

### 10.6 Conflict Results Storage

After simulation completes, `save_conflict_result` is called:
1. All existing `ConflictResults` rows for this user are updated to `is_latest = False`.
2. A new `ConflictResults` row is inserted with `is_latest = True` and the full simulation output serialised as JSON.

The `GET /goals/profile_overview` endpoint fetches the latest conflict result along with all goal summaries to produce a consolidated portfolio view.

---

## 11. Structured Logging

Every service module uses the same `JSONFormatter` from `app/utils/log_format.py`. Log records are emitted as JSON objects, which makes them parseable by log aggregation tools (Render Log Stream, Datadog, etc.).

Typical log record shape:
```json
{
  "event": "Feasibility check completed",
  "time_taken_seconds": 0.0012,
  "feasible": true,
  "peak_savings_ratio_pct": 38.4,
  "breach_count": 0
}
```

Each calculation function logs its execution time, enabling performance profiling of individual math operations. Auth events log success and failure at appropriate levels (`INFO` / `WARNING`) without leaking credential data.

---

## 12. Environment & Configuration

Copy `.env.example` to `.env` and populate the values:

```env
# Database
SQLALCHEMY_DATABASE_URL=postgresql+psycopg2://<user>:<password>@<host>:<port>/<dbname>

# Alternative env var names (fallback chain: SQLALCHEMY_DATABASE_URL → DATABASE_URL → SUPABASE_DB_URL)
# DATABASE_URL=...
# SUPABASE_DB_URL=...

# Auth
SECRET_KEY=<random-secret-min-32-chars>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# OpenAI
OPENAI_API_KEY=sk-...
```

### Supabase URL Notes

If your database URL uses the `postgres://` scheme, `app/databse.py` will automatically rewrite it to `postgresql://` at startup. SSL (`sslmode=require`) is automatically appended to connection strings targeting any `*.supabase.co` or `*.supabase.com` host.

If your Supabase password contains special characters (e.g. `@`), **URL-encode** them before placing in the connection string (`@` → `%40`).

---

## 13. Running Locally with Docker

```bash
# Build the image
docker build -t goalpath-backend ./Backend/app

# Run with your .env file
docker run --env-file Backend/.env -p 8000:8000 goalpath-backend
```

Health check endpoint:
```
GET http://localhost:8000/health
```

The container is configured with a Docker health check that polls `/health` every 30 seconds. The app is healthy when `Application startup complete` appears in the logs.

---

## 14. Deployment on Render

1. Push the repository to GitHub.
2. Create a new **Web Service** on Render pointing to the repository.
3. Set **Root Directory** to `Backend/app` (where `Dockerfile` lives) or configure the build command accordingly.
4. Add the following environment variables in the Render dashboard:

| Variable | Value |
|---|---|
| `SQLALCHEMY_DATABASE_URL` | Your Supabase PostgreSQL connection string |
| `SECRET_KEY` | A strong random secret |
| `OPENAI_API_KEY` | Your OpenAI API key |

> Do not bake `.env` into the image. The `.dockerignore` file already excludes `.env` and `.env.*` from the build context.

---

## 15. Running Tests

```bash
cd Backend

# Install dependencies
pip install -r requirements.txt

# Run all tests
pytest

# Unit tests only
pytest tests/unit_test/

# Integration tests only
pytest tests/integration_test/

# End-to-end smoke test
pytest tests/test_e2e_smoke.py -v
```

The integration tests require a reachable database. Set `SQLALCHEMY_DATABASE_URL` in your environment before running them. Unit tests are pure math assertions and need no database.
