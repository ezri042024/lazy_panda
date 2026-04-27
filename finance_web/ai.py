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


import base64
import json
from decimal import Decimal, InvalidOperation

from django.conf import settings
from openai import OpenAI


def analyze_receipt_image_with_openai(uploaded_file):
    """
    Reads a receipt image using OpenAI vision and returns:
    {
        "merchant": "...",
        "total_amount": "123.45",
        "category_hint": "...",
        "transaction_date": "YYYY-MM-DD" or "",
        "notes": "..."
    }
    """

    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured.")

    content_type = getattr(uploaded_file, "content_type", None) or "image/jpeg"

    allowed_content_types = [
        "image/jpeg",
        "image/png",
        "image/webp",
    ]

    if content_type not in allowed_content_types:
        raise ValueError("Only JPG, PNG, and WEBP receipt images are allowed.")

    image_bytes = uploaded_file.read()
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    prompt = """
You are a receipt reader for a personal finance app.

Read the receipt image and extract the purchase details.

Return ONLY valid JSON. Do not include markdown.

JSON format:
{
  "merchant": "",
  "total_amount": "",
  "category_hint": "",
  "transaction_date": "",
  "notes": ""
}

Rules:
- total_amount must be the final amount paid by the customer.
- Prefer GRAND TOTAL, TOTAL, AMOUNT DUE, or AMOUNT PAID.
- Ignore change, cash received, subtotal, VAT, tax, and discounts as the total amount.
- Use Philippine Peso context if currency is not clear.
- merchant should be the store/business name.
- category_hint should be simple, like Food, Groceries, Transport, Utilities, Shopping, Health, Entertainment, or Other.
- transaction_date should be YYYY-MM-DD if visible, otherwise empty string.
- notes should be short.
- If you are not sure about the amount, leave total_amount empty.
"""

    response = client.responses.create(
        model="gpt-5.4",
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt,
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:{content_type};base64,{b64_image}",
                    },
                ],
            }
        ],
    )

    raw_text = response.output_text.strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        raise ValueError(f"OpenAI returned invalid JSON: {raw_text}")

    merchant = str(data.get("merchant") or "").strip()
    total_amount = str(data.get("total_amount") or "").strip()
    category_hint = str(data.get("category_hint") or "").strip()
    transaction_date = str(data.get("transaction_date") or "").strip()
    notes = str(data.get("notes") or "").strip()

    if not merchant:
        merchant = "Receipt purchase"

    try:
        amount = Decimal(total_amount.replace(",", ""))
    except (InvalidOperation, AttributeError):
        amount = None

    if not amount or amount <= 0:
        raise ValueError("I read the receipt, but I could not confidently find the total amount.")

    return {
        "merchant": merchant[:150],
        "amount": amount,
        "category_hint": category_hint,
        "transaction_date": transaction_date,
        "notes": notes,
        "raw": data,
    }