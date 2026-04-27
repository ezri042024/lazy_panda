from django.conf import settings
from openai import OpenAI


def generate_report_ai_summary(report_data):
    if not settings.OPENAI_API_KEY:
        return "AI summary is unavailable because OPENAI_API_KEY is not configured."

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    prompt = f"""
You are a personal finance assistant.

Analyze this user's monthly finance report and write a short, practical summary.

Rules:
- Be concise.
- Use Philippine Peso amounts.
- Mention the strongest insight.
- Mention one possible warning.
- Give 2 to 3 practical suggestions.
- Do not sound judgmental.
- Do not invent data.
- If data is missing, say so.

Report data:
Month/Year: {report_data["month"]}/{report_data["year"]}

Income: ₱{report_data["total_income"]}
Expenses: ₱{report_data["total_expense"]}
Net cashflow: ₱{report_data["net_cashflow"]}

Assets: ₱{report_data["total_assets"]}
Liabilities: ₱{report_data["total_liabilities"]}
Net worth: ₱{report_data["net_worth"]}

Budget limit: ₱{report_data["total_budget_limit"]}
Budget spent: ₱{report_data["total_budget_spent"]}
Budget remaining: ₱{report_data["total_budget_remaining"]}
Budget usage percent: {report_data["budget_usage_percent"]}%

Bills due: ₱{report_data["total_bills_due"]}
Bills paid: ₱{report_data["total_bills_paid"]}
Unpaid bills: ₱{report_data["unpaid_bills_total"]}

Debt balance: ₱{report_data["total_debt_balance"]}

Goal target: ₱{report_data["total_goal_target"]}
Goal saved: ₱{report_data["total_goal_saved"]}
Goal progress percent: {report_data["goal_progress_percent"]}%

Expense by category:
{report_data["expense_by_category_text"]}

Budget categories:
{report_data["budget_rows_text"]}
"""

    response = client.responses.create(
        model="gpt-5.4",
        input=prompt,
    )

    return response.output_text.strip()