import calendar
from datetime import date

from django.core.exceptions import ValidationError
from django.db.models import F

from .models import Account, Debt, SavingsGoal, Bill, RecurringBill

LIABILITY_ACCOUNT_TYPES = ["credit_card", "loan"]


def account_allows_negative_balance(account):
    return account.account_type in LIABILITY_ACCOUNT_TYPES


def validate_account_can_decrease(account, amount):
    """
    Asset accounts cannot go below zero.
    Liability accounts are stored as positive amount owed,
    so payment cannot exceed current balance owed.
    """
    if account.account_type in LIABILITY_ACCOUNT_TYPES:
        if account.current_balance - amount < 0:
            raise ValidationError(
                f"{account.name} payment cannot exceed the current balance."
            )
        return

    if account.current_balance - amount < 0:
        raise ValidationError(
            f"{account.name} does not have enough balance."
        )


def increase_account_balance(account_id, amount):
    Account.objects.filter(id=account_id).update(
        current_balance=F("current_balance") + amount
    )


def decrease_account_balance(account_id, amount):
    account = Account.objects.select_for_update().get(id=account_id)

    validate_account_can_decrease(account, amount)

    Account.objects.filter(id=account_id).update(
        current_balance=F("current_balance") - amount
    )


def increase_debt_balance(debt_id, amount):
    Debt.objects.filter(id=debt_id).update(
        current_balance=F("current_balance") + amount
    )


def decrease_debt_balance(debt_id, amount):
    Debt.objects.filter(id=debt_id).update(
        current_balance=F("current_balance") - amount
    )


def increase_goal_amount(goal_id, amount):
    SavingsGoal.objects.filter(id=goal_id).update(
        current_amount=F("current_amount") + amount
    )


def decrease_goal_amount(goal_id, amount):
    SavingsGoal.objects.filter(id=goal_id).update(
        current_amount=F("current_amount") - amount
    )


def get_safe_due_date(year, month, due_day):
    last_day = calendar.monthrange(year, month)[1]
    safe_day = min(due_day, last_day)
    return date(year, month, safe_day)


def generate_bill_from_recurring_bill(recurring_bill, year, month):
    due_date = get_safe_due_date(
        year=year,
        month=month,
        due_day=recurring_bill.due_day,
    )

    if recurring_bill.start_date > due_date:
        return None, False

    if recurring_bill.end_date and recurring_bill.end_date < due_date:
        return None, False

    bill, created = Bill.objects.get_or_create(
        user=recurring_bill.user,
        recurring_bill=recurring_bill,
        due_date=due_date,
        defaults={
            "account": recurring_bill.account,
            "category": recurring_bill.category,
            "name": recurring_bill.name,
            "amount_due": recurring_bill.amount_due,
            "amount_paid": 0,
            "status": "unpaid",
            "notes": recurring_bill.notes,
        },
    )

    return bill, created


def generate_recurring_bills_for_user(user, year, month):
    recurring_bills = RecurringBill.objects.filter(
        user=user,
        is_active=True,
        auto_generate=True,
    )

    created_bills = []
    skipped_count = 0

    for recurring_bill in recurring_bills:
        bill, created = generate_bill_from_recurring_bill(
            recurring_bill=recurring_bill,
            year=year,
            month=month,
        )

        if created:
            created_bills.append(bill)
        else:
            skipped_count += 1

    return created_bills, skipped_count
