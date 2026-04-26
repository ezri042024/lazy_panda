from .models import Account, Category


DEFAULT_CATEGORIES = [
    # Income
    {
        "name": "Salary",
        "category_type": "income",
        "icon": "bi-cash-stack",
        "color": "#16a34a",
    },
    {
        "name": "Freelance",
        "category_type": "income",
        "icon": "bi-laptop",
        "color": "#22c55e",
    },
    {
        "name": "Business",
        "category_type": "income",
        "icon": "bi-briefcase",
        "color": "#0f766e",
    },
    {
        "name": "Bonus",
        "category_type": "income",
        "icon": "bi-gift",
        "color": "#84cc16",
    },

    # Expenses
    {
        "name": "Food & Groceries",
        "category_type": "expense",
        "icon": "bi-basket",
        "color": "#f97316",
    },
    {
        "name": "Transportation",
        "category_type": "expense",
        "icon": "bi-bus-front",
        "color": "#0ea5e9",
    },
    {
        "name": "Rent / Housing",
        "category_type": "expense",
        "icon": "bi-house-door",
        "color": "#6366f1",
    },
    {
        "name": "Utilities",
        "category_type": "expense",
        "icon": "bi-lightning-charge",
        "color": "#eab308",
    },
    {
        "name": "Internet / Phone",
        "category_type": "expense",
        "icon": "bi-wifi",
        "color": "#06b6d4",
    },
    {
        "name": "Healthcare / Medicine",
        "category_type": "expense",
        "icon": "bi-capsule",
        "color": "#ef4444",
    },
    {
        "name": "Shopping",
        "category_type": "expense",
        "icon": "bi-bag",
        "color": "#ec4899",
    },
    {
        "name": "Dining Out",
        "category_type": "expense",
        "icon": "bi-cup-hot",
        "color": "#fb7185",
    },
    {
        "name": "Entertainment",
        "category_type": "expense",
        "icon": "bi-controller",
        "color": "#8b5cf6",
    },
    {
        "name": "Subscriptions",
        "category_type": "expense",
        "icon": "bi-credit-card",
        "color": "#64748b",
    },
    {
        "name": "Travel",
        "category_type": "expense",
        "icon": "bi-airplane",
        "color": "#14b8a6",
    },

    # Saving
    {
        "name": "Emergency Fund",
        "category_type": "saving",
        "icon": "bi-piggy-bank",
        "color": "#2563eb",
    },
    {
        "name": "Investments",
        "category_type": "saving",
        "icon": "bi-graph-up-arrow",
        "color": "#15803d",
    },

    # Debt
    {
        "name": "Credit Card Payment",
        "category_type": "debt",
        "icon": "bi-credit-card-2-front",
        "color": "#dc2626",
    },
    {
        "name": "Loan Payment",
        "category_type": "debt",
        "icon": "bi-bank",
        "color": "#7f1d1d",
    },
]


def create_default_finance_setup(user):
    """
    Creates default finance records for a new user.
    Safe to call multiple times because it uses get_or_create.
    """

    Account.objects.get_or_create(
        user=user,
        name="Cash Wallet",
        defaults={
            "account_type": "cash",
            "institution_name": "Cash",
            "opening_balance": 0,
            "current_balance": 0,
            "currency": "PHP",
            "is_active": True,
        },
    )

    for category in DEFAULT_CATEGORIES:
        Category.objects.get_or_create(
            user=user,
            name=category["name"],
            category_type=category["category_type"],
            defaults={
                "icon": category["icon"],
                "color": category["color"],
                "is_default": True,
                "is_active": True,
            },
        )