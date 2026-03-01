intent_categories = [
    "GOAL_PLANNING",
    "PLAN_REVIEW",
    "EMERGENCY_FUND",
    "BUDGETING",
    "EDUCATION",
    "BLOCKED_INVESTMENT_ADVICE"
]


INTENT_KEYWORDS = {
    "BLOCKED_INVESTMENT_ADVICE": [
        "stock", "stocks", "share", "shares", "buy", "sell", "trade", "trading",
        "ticker", "which stock", "what stock", "stock pick", "stock recommendation",
        "invest in which", "should i buy", "should i sell", "best stock", "top stock",
        "stock tip", "stock tips", "day trading", "swing trading", "penny stock",
        "upcoming ipo", "ipo", "which company", "stock market tip", "short sell",
        "options trading", "forex", "cryptocurrency trade", "crypto trade", "bitcoin trade",
        "when to buy", "when to sell", "buy signal", "sell signal", "technical analysis stock"
    ],
    "GOAL_PLANNING": [
        "goal", "plan", "retirement", "house", "home", "car", "education fund",
        "save for", "saving for", "future", "target", "dream", "achieve", "milestone"
    ],
    "EMERGENCY_FUND": [
        "emergency", "emergency fund", "rainy day", "contingency", "safety net",
        "unexpected expense", "backup fund"
    ],
    "BUDGETING": [
        "budget", "expense", "spending", "income", "monthly", "track", "allocate",
        "manage money", "cash flow"
    ],
    "PLAN_REVIEW": [
        "review", "check plan", "progress", "status", "how am i doing", "portfolio review",
        "rebalance", "assessment"
    ],
    "EDUCATION": [
        "learn", "what is", "how does", "explain", "understand", "meaning of",
        "difference between", "types of", "help me understand"
    ]
}


def categorize_intent(user_input: str) -> str:
    user_input_lower = user_input.lower()
    
    # Score each category based on keyword matches
    category_scores = {category: 0 for category in intent_categories}
    
    for category, keywords in INTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in user_input_lower:
                category_scores[category] += 1
    
    # Return the category with highest score, or EDUCATION as default
    max_category = max(category_scores, key=category_scores.get)
    
    return max_category if category_scores[max_category] > 0 else "EDUCATION"

