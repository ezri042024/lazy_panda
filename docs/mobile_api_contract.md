# Mobile API Contract

This document is the API reference for the mobile app. It explains what endpoints the Flutter/mobile client should call, what data to send, what responses to expect, and common errors.

---

## Base URLs

### Android Emulator

```text
http://10.0.2.2:8000/api
```

### Browser / Desktop Localhost

```text
http://127.0.0.1:8000/api
```

### Authentication Header

All protected endpoints require this header:

```http
Authorization: Bearer <access_token>
```

Example:

```http
GET /api/finance/dashboard/
Authorization: Bearer eyJhbGciOi...
```

---

# 1. Authentication

## Register

```http
POST /auth/register/
```

### Request

```json
{
  "username": "oneil",
  "email": "oneil@example.com",
  "first_name": "Oneil",
  "last_name": "Valenciano",
  "password": "StrongPass123!",
  "password_confirm": "StrongPass123!"
}
```

### Response

```json
{
  "user": {
    "id": 1,
    "username": "oneil",
    "email": "oneil@example.com",
    "first_name": "Oneil",
    "last_name": "Valenciano",
    "full_name": "Oneil Valenciano"
  },
  "refresh": "refresh_token_here",
  "access": "access_token_here"
}
```

### Notes

After registration, the backend automatically creates:

```text
Cash Wallet
Default income categories
Default expense categories
Default saving/debt categories
```

---

## Login

```http
POST /auth/login/
```

### Request

```json
{
  "username": "oneil",
  "password": "StrongPass123!"
}
```

### Response

```json
{
  "refresh": "refresh_token_here",
  "access": "access_token_here"
}
```

---

## Refresh Token

```http
POST /auth/token/refresh/
```

### Request

```json
{
  "refresh": "refresh_token_here"
}
```

### Response

```json
{
  "access": "new_access_token_here",
  "refresh": "new_refresh_token_here"
}
```

Depending on the SimpleJWT settings, the response may or may not include a new refresh token.

---

## Current User

```http
GET /auth/me/
```

### Response

```json
{
  "id": 1,
  "username": "oneil",
  "email": "oneil@example.com",
  "first_name": "Oneil",
  "last_name": "Valenciano",
  "full_name": "Oneil Valenciano"
}
```

---

# 2. Setup Status

## Get Setup Status

```http
GET /finance/setup-status/
```

### Response

```json
{
  "has_accounts": true,
  "has_income_categories": true,
  "has_expense_categories": true,
  "has_default_cash_account": true,
  "can_add_transaction": true,
  "recommended_next_step": "ready"
}
```

### Possible `recommended_next_step` Values

```text
ready
create_account
create_categories
```

---

# 3. Accounts

## List Accounts

```http
GET /finance/accounts/
```

### Response

```json
[
  {
    "id": 1,
    "name": "Cash Wallet",
    "account_type": "cash",
    "institution_name": "Cash",
    "account_number_last4": "",
    "opening_balance": "0.00",
    "current_balance": "0.00",
    "credit_limit": "0.00",
    "available_credit": null,
    "billing_day": null,
    "due_day": null,
    "currency": "PHP",
    "is_active": true,
    "created_at": "2026-04-25T10:00:00Z"
  }
]
```

---

## Create Account

```http
POST /finance/accounts/
```

### Bank Account Request

```json
{
  "name": "BDO Savings",
  "account_type": "bank",
  "institution_name": "BDO",
  "account_number_last4": "1234",
  "opening_balance": "10000.00",
  "current_balance": "10000.00",
  "currency": "PHP",
  "is_active": true
}
```

### E-Wallet Request

```json
{
  "name": "GCash Personal",
  "account_type": "ewallet",
  "institution_name": "GCash",
  "opening_balance": "500.00",
  "current_balance": "500.00",
  "currency": "PHP",
  "is_active": true
}
```

### Credit Card Request

```json
{
  "name": "UnionBank Rewards Visa",
  "account_type": "credit_card",
  "institution_name": "UnionBank",
  "account_number_last4": "9876",
  "opening_balance": "0.00",
  "current_balance": "0.00",
  "credit_limit": "50000.00",
  "billing_day": 15,
  "due_day": 5,
  "currency": "PHP",
  "is_active": true
}
```

### Notes

Credit cards and loan accounts are allowed to go negative.

```text
0.00 → expense 1000.00 → -1000.00
```

Cash, bank, e-wallet, and investment accounts cannot go negative.

---

## Update Account

```http
PATCH /finance/accounts/{id}/
```

### Request

```json
{
  "name": "BDO Main Savings"
}
```

---

## Delete Account

```http
DELETE /finance/accounts/{id}/
```

---

# 4. Categories

## List Categories

```http
GET /finance/categories/
```

### Optional Filters

```http
GET /finance/categories/?type=expense
GET /finance/categories/?type=income
GET /finance/categories/?type=saving
GET /finance/categories/?type=debt
```

### Response

```json
[
  {
    "id": 1,
    "name": "Food & Groceries",
    "category_type": "expense",
    "icon": "bi-basket",
    "color": "#f97316",
    "is_default": true,
    "is_active": true,
    "created_at": "2026-04-25T10:00:00Z"
  }
]
```

---

## Create Category

```http
POST /finance/categories/
```

### Request

```json
{
  "name": "Pets",
  "category_type": "expense",
  "icon": "bi-heart",
  "color": "#ec4899",
  "is_active": true
}
```

---

# 5. Transactions

Transactions are for income, expenses, and adjustments.

## List Transactions

```http
GET /finance/transactions/
```

### Optional Filters

```http
GET /finance/transactions/?type=expense
GET /finance/transactions/?month=4&year=2026
GET /finance/transactions/?account=1
GET /finance/transactions/?category=3
```

---

## Create Expense

```http
POST /finance/transactions/
```

### Request

```json
{
  "account": 1,
  "category": 2,
  "transaction_type": "expense",
  "title": "Lunch",
  "amount": "150.00",
  "transaction_date": "2026-04-25",
  "notes": "Jollibee"
}
```

### Balance Effect

```text
Account balance decreases by 150.00
```

---

## Create Income

```http
POST /finance/transactions/
```

### Request

```json
{
  "account": 1,
  "category": 1,
  "transaction_type": "income",
  "title": "Salary",
  "amount": "25000.00",
  "transaction_date": "2026-04-25",
  "notes": "April salary"
}
```

### Balance Effect

```text
Account balance increases by 25000.00
```

---

## Update Transaction

```http
PATCH /finance/transactions/{id}/
```

### Request

```json
{
  "amount": "200.00"
}
```

The backend reverses the old transaction effect, then applies the new one.

---

## Delete Transaction

```http
DELETE /finance/transactions/{id}/
```

The backend reverses the transaction effect.

---

# 6. Transfers

Transfers move money between accounts.

## List Transfers

```http
GET /finance/transfers/
```

### Optional Filters

```http
GET /finance/transfers/?month=4&year=2026
GET /finance/transfers/?from_account=1
GET /finance/transfers/?to_account=2
```

---

## Create Transfer

```http
POST /finance/transfers/
```

### Request

```json
{
  "from_account": 1,
  "to_account": 2,
  "amount": "1000.00",
  "transfer_date": "2026-04-25",
  "notes": "Cash in to GCash"
}
```

### Balance Effect

```text
from_account decreases by 1000.00
to_account increases by 1000.00
```

Asset accounts cannot transfer more than their available balance.

---

## Update Transfer

```http
PATCH /finance/transfers/{id}/
```

### Request

```json
{
  "amount": "1500.00"
}
```

The backend reverses the old transfer, then applies the new one.

---

## Delete Transfer

```http
DELETE /finance/transfers/{id}/
```

The backend reverses the transfer effect.

---

# 7. Budgets

## List Budgets

```http
GET /finance/budgets/
```

### Optional Filters

```http
GET /finance/budgets/?month=4&year=2026
```

---

## Create Budget

```http
POST /finance/budgets/
```

### Request

```json
{
  "category": 2,
  "amount_limit": "8000.00",
  "month": 4,
  "year": 2026
}
```

### Rules

```text
Category must belong to the user
Category must be an expense category
Only one budget per category/month/year
Amount must be greater than zero
```

---

# 8. Bills

## List Bills

```http
GET /finance/bills/
```

### Optional Filters

```http
GET /finance/bills/?status=unpaid
GET /finance/bills/?month=4&year=2026
```

---

## Create Bill

```http
POST /finance/bills/
```

### Request

```json
{
  "account": 1,
  "category": 2,
  "name": "Internet Bill",
  "amount_due": "1500.00",
  "amount_paid": "0.00",
  "due_date": "2026-04-30",
  "status": "unpaid",
  "notes": "Monthly internet"
}
```

---

## Mark Bill as Paid

```http
POST /finance/bills/{id}/mark_paid/
```

### Balance Effect

```text
Account balance decreases by remaining amount
```

Example:

```text
amount_due: 1500.00
amount_paid: 500.00
remaining: 1000.00

account decreases by 1000.00
```

---

# 9. Debts

## List Debts

```http
GET /finance/debts/
```

---

## Create Debt

```http
POST /finance/debts/
```

### Request

```json
{
  "name": "UnionBank Credit Card",
  "lender": "UnionBank",
  "original_amount": "16966.00",
  "current_balance": "16966.00",
  "interest_rate": "3.00",
  "minimum_payment": "1000.00",
  "due_day": 5,
  "is_active": true
}
```

---

# 10. Debt Payments

## List Debt Payments

```http
GET /finance/debt-payments/
```

### Optional Filters

```http
GET /finance/debt-payments/?debt=1
GET /finance/debt-payments/?account=2
GET /finance/debt-payments/?month=4&year=2026
```

---

## Create Debt Payment

```http
POST /finance/debt-payments/
```

### Request

```json
{
  "debt": 1,
  "account": 2,
  "amount": "3000.00",
  "principal_amount": "2500.00",
  "interest_amount": "500.00",
  "payment_date": "2026-04-25",
  "notes": "April credit card payment"
}
```

### Balance Effect

```text
Account decreases by 3000.00
Debt balance decreases by 2500.00
```

### Validation

```text
principal_amount + interest_amount must equal amount
principal_amount cannot exceed debt current_balance
```

---

# 11. Savings Goals

## List Savings Goals

```http
GET /finance/savings-goals/
```

---

## Create Savings Goal

```http
POST /finance/savings-goals/
```

### Request

```json
{
  "name": "Emergency Fund",
  "target_amount": "100000.00",
  "current_amount": "0.00",
  "target_date": "2026-12-31",
  "is_completed": false
}
```

---

# 12. Goal Contributions

## List Goal Contributions

```http
GET /finance/goal-contributions/
```

### Optional Filters

```http
GET /finance/goal-contributions/?goal=1
GET /finance/goal-contributions/?account=2
GET /finance/goal-contributions/?month=4&year=2026
```

---

## Create Goal Contribution

```http
POST /finance/goal-contributions/
```

### Request

```json
{
  "goal": 1,
  "account": 2,
  "amount": "2000.00",
  "contribution_date": "2026-04-25",
  "notes": "Emergency fund contribution"
}
```

### Balance Effect

```text
Account decreases by 2000.00
Savings goal current_amount increases by 2000.00
```

### Validation

```text
Contribution cannot exceed remaining target amount
```

---

# 13. Receipts

## List Receipts

```http
GET /finance/receipts/
```

---

## Upload Receipt

```http
POST /finance/receipts/
```

Use `multipart/form-data`.

### Fields

```text
transaction: 1
file: receipt.jpg
```

### Allowed Files

```text
JPG
PNG
WEBP
PDF
```

### Max Size

```text
5MB
```

---

# 14. Dashboard

## Get Dashboard

```http
GET /finance/dashboard/
```

### Optional Period

```http
GET /finance/dashboard/?month=4&year=2026
```

### Response

```json
{
  "period": {
    "month": 4,
    "year": 2026
  },
  "summary": {
    "total_assets": "11000.00",
    "total_liabilities": "-3000.00",
    "net_worth": "8000.00",
    "total_income": "25000.00",
    "total_expense": "2750.00",
    "net_cashflow": "22250.00",
    "unpaid_bills_total": "2000.00",
    "total_debt_balance": "7000.00",
    "total_goal_saved": "10000.00",
    "total_goal_target": "50000.00"
  },
  "accounts": [
    {
      "id": 1,
      "name": "Cash Wallet",
      "account_type": "cash",
      "institution_name": "Cash",
      "current_balance": "1000.00",
      "currency": "PHP"
    }
  ],
  "expense_by_category": [
    {
      "category__id": 2,
      "category__name": "Food",
      "total": "1750.00"
    }
  ],
  "income_by_category": [
    {
      "category__id": 1,
      "category__name": "Salary",
      "total": "25000.00"
    }
  ],
  "recent_transactions": [],
  "due_soon_bills": [],
  "overdue_bills": [],
  "goal_progress": [
    {
      "id": 1,
      "name": "Emergency Fund",
      "target_amount": "50000.00",
      "current_amount": "10000.00",
      "progress_percent": 20.0,
      "target_date": "2026-12-31"
    }
  ]
}
```

---

# 15. Common Error Responses

## Not Authenticated

```json
{
  "detail": "Authentication credentials were not provided."
}
```

---

## Not Enough Balance

```json
{
  "detail": [
    "BDO Savings does not have enough balance."
  ]
}
```

---

## Invalid User-Owned Record

```json
{
  "account": [
    "Invalid account."
  ]
}
```

---

## Validation Error

```json
{
  "amount": [
    "Amount must be greater than zero."
  ]
}
```

---

# 16. Recommended Mobile Startup Flow

```text
Open app
↓
Check stored access token
↓
If no token, show Login screen
↓
If token exists, call GET /auth/me/
↓
If token expired, call POST /auth/token/refresh/
↓
Call GET /finance/setup-status/
↓
If ready, call GET /finance/dashboard/
↓
Show Dashboard
```

---

# 17. Notes for Flutter

## Amounts

Amounts are returned as strings, for example:

```json
{
  "amount": "150.00"
}
```

In Flutter, parse them using `double.tryParse()` or a decimal-safe package if you need precise money calculations.

## Dates

Dates use this format:

```text
YYYY-MM-DD
```

Example:

```json
{
  "transaction_date": "2026-04-25"
}
```

## Tokens

Store access and refresh tokens securely. For Flutter, use secure storage rather than plain shared preferences.
