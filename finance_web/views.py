import re
from decimal import InvalidOperation, Decimal

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from django.http import JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from finance.defaults import create_default_finance_setup
from finance.models import Account, Transaction, Bill, Debt, SavingsGoal, Budget, Category, RecurringBill, Transfer, \
    DebtPayment, GoalContribution, MoneyLent, MoneyLentPayment
from finance.services import decrease_account_balance, increase_account_balance, generate_recurring_bills_for_user, \
    increase_debt_balance, decrease_debt_balance, decrease_goal_amount, increase_goal_amount, create_money_lent, \
    add_money_lent_payment
from finance.views import BillViewSet
from .ai import generate_report_ai_summary, analyze_receipt_image_with_openai

from .forms import WebLoginForm, WebRegisterForm, AccountWebForm, TransactionWebForm, RecurringBillWebForm, BillWebForm, \
    TransferWebForm, DebtPaymentWebForm, DebtWebForm, SavingsGoalWebForm, GoalContributionWebForm, CategoryWebForm, \
    BudgetWebForm, MoneyLentWebForm, MoneyLentPaymentWebForm

from django.contrib import messages
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction as db_transaction


def web_login_view(request):
    if request.user.is_authenticated:
        return redirect("finance_web_dashboard")

    form = WebLoginForm(request, data=request.POST or None)

    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect("finance_web_dashboard")

    return render(request, "finance_web/auth/login.html", {
        "form": form,
    })


def web_register_view(request):
    if request.user.is_authenticated:
        return redirect("finance_web_dashboard")

    form = WebRegisterForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.set_password(form.cleaned_data["password"])
        user.save()
        create_default_finance_setup(user)
        login(request, user)
        messages.success(request, "Account created successfully.")
        return redirect("finance_web_dashboard")

    return render(request, "finance_web/auth/register.html", {
        "form": form,
    })


def web_logout_view(request):
    logout(request)
    return redirect("finance_web_login")


@login_required
def dashboard_view(request):
    today = timezone.localdate()

    month = int(request.GET.get("month", today.month))
    year = int(request.GET.get("year", today.year))

    accounts = Account.objects.filter(
        user=request.user,
        is_active=True,
    )

    transactions = Transaction.objects.filter(
        user=request.user,
        transaction_date__month=month,
        transaction_date__year=year,
    )

    recent_card_payments = Transfer.objects.filter(
        user=request.user,
        to_account__account_type__in=["credit_card", "loan"],
        transfer_date__month=month,
        transfer_date__year=year,
    ).select_related(
        "from_account",
        "to_account",
    ).order_by("-transfer_date", "-created_at")[:5]

    bills = Bill.objects.filter(user=request.user)
    debts = Debt.objects.filter(user=request.user, is_active=True)
    goals = SavingsGoal.objects.filter(user=request.user, is_completed=False)
    budgets = Budget.objects.filter(user=request.user, month=month, year=year)

    total_assets = accounts.exclude(
        account_type__in=["credit_card", "loan"]
    ).aggregate(total=Sum("current_balance"))["total"] or 0

    liability_accounts = accounts.filter(
        account_type__in=["credit_card", "loan"]
    )

    total_account_liabilities = sum(
        abs(account.current_balance)
        for account in liability_accounts
        if account.current_balance != 0
    )

    total_debt_balance = debts.aggregate(
        total=Sum("current_balance")
    )["total"] or 0

    total_liabilities = total_account_liabilities + total_debt_balance
    net_worth = total_assets - total_liabilities

    total_income = transactions.filter(
        transaction_type="income"
    ).aggregate(total=Sum("amount"))["total"] or 0

    total_expense = transactions.filter(
        transaction_type="expense"
    ).aggregate(total=Sum("amount"))["total"] or 0

    net_cashflow = total_income - total_expense

    unpaid_bills_total = bills.filter(
        status__in=["unpaid", "partial", "overdue"]
    ).aggregate(total=Sum("amount_due"))["total"] or 0

    recent_transactions = transactions.select_related(
        "account",
        "category",
    ).order_by("-transaction_date", "-created_at")[:8]

    due_soon_bills = bills.filter(
        status__in=["unpaid", "partial"],
        due_date__gte=today,
        due_date__lte=today + timezone.timedelta(days=7),
    ).order_by("due_date")[:5]

    overdue_bills = bills.filter(
        status__in=["unpaid", "partial", "overdue"],
        due_date__lt=today,
    ).order_by("due_date")[:5]

    expense_by_category = (
        transactions
        .filter(transaction_type="expense", category__isnull=False)
        .values("category__name")
        .annotate(total=Sum("amount"))
        .order_by("-total")[:5]
    )

    total_budget_limit = budgets.aggregate(
        total=Sum("amount_limit")
    )["total"] or 0

    budget_category_ids = list(budgets.values_list("category_id", flat=True))

    total_budget_spent = transactions.filter(
        transaction_type="expense",
        category_id__in=budget_category_ids,
    ).aggregate(
        total=Sum("amount")
    )["total"] or 0

    total_budget_remaining = total_budget_limit - total_budget_spent

    context = {
        "month": month,
        "year": year,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": net_worth,
        "total_income": total_income,
        "total_expense": total_expense,
        "net_cashflow": net_cashflow,
        "unpaid_bills_total": unpaid_bills_total,
        "recent_transactions": recent_transactions,
        "due_soon_bills": due_soon_bills,
        "overdue_bills": overdue_bills,
        "expense_by_category": expense_by_category,
        "total_budget_limit": total_budget_limit,
        "total_budget_spent": total_budget_spent,
        "total_budget_remaining": total_budget_remaining,
        "recent_card_payments": recent_card_payments,
    }

    return render(request, "finance_web/dashboard.html", context)


@login_required
def transactions_view(request):
    today = timezone.localdate()

    month = int(request.GET.get("month", today.month))
    year = int(request.GET.get("year", today.year))
    transaction_type = request.GET.get("type", "all")
    account_id = request.GET.get("account", "")
    category_id = request.GET.get("category", "")

    transactions = Transaction.objects.filter(
        user=request.user,
        transaction_date__month=month,
        transaction_date__year=year,
    ).select_related("account", "category")

    if transaction_type and transaction_type != "all":
        transactions = transactions.filter(transaction_type=transaction_type)

    if account_id:
        transactions = transactions.filter(account_id=account_id)

    if category_id:
        transactions = transactions.filter(category_id=category_id)

    transactions = transactions.order_by("-transaction_date", "-created_at")

    total_income = transactions.filter(
        transaction_type="income"
    ).aggregate(total=Sum("amount"))["total"] or 0

    total_expense = transactions.filter(
        transaction_type="expense"
    ).aggregate(total=Sum("amount"))["total"] or 0

    net_total = total_income - total_expense

    accounts = Account.objects.filter(
        user=request.user,
        is_active=True,
    ).order_by("account_type", "name")

    categories = Category.objects.filter(
        user=request.user,
        is_active=True,
    ).order_by("category_type", "name")

    context = {
        "month": month,
        "year": year,
        "transaction_type": transaction_type,
        "selected_account_id": account_id,
        "selected_category_id": category_id,
        "transactions": transactions,
        "accounts": accounts,
        "categories": categories,
        "total_income": total_income,
        "total_expense": total_expense,
        "net_total": net_total,
    }

    return render(request, "finance_web/transactions.html", context)


@login_required
def accounts_view(request):
    accounts = Account.objects.filter(
        user=request.user,
        is_active=True,
    ).order_by("account_type", "institution_name", "name")

    asset_types = ["cash", "bank", "ewallet", "investment"]
    liability_types = ["credit_card", "loan"]

    asset_accounts = accounts.filter(account_type__in=asset_types)
    liability_accounts = accounts.filter(account_type__in=liability_types)

    total_assets = asset_accounts.aggregate(
        total=Sum("current_balance")
    )["total"] or 0

    total_liabilities = sum(
        abs(account.current_balance)
        for account in liability_accounts
        if account.current_balance != 0
    )

    net_worth = total_assets - total_liabilities

    context = {
        "accounts": accounts,
        "asset_accounts": asset_accounts,
        "liability_accounts": liability_accounts,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": net_worth,
    }

    return render(request, "finance_web/accounts.html", context)


LIABILITY_ACCOUNT_TYPES = ["credit_card", "loan"]


def apply_transaction_balance_effect(transaction_obj):
    account = transaction_obj.account
    amount = transaction_obj.amount
    transaction_type = transaction_obj.transaction_type

    if transaction_type == "income":
        increase_account_balance(account.id, amount)

    elif transaction_type == "expense":
        if account.account_type in LIABILITY_ACCOUNT_TYPES:
            increase_account_balance(account.id, amount)
        else:
            decrease_account_balance(account.id, amount)

    elif transaction_type == "adjustment":
        increase_account_balance(account.id, amount)


def reverse_transaction_balance_effect(transaction_obj):
    account = transaction_obj.account
    amount = transaction_obj.amount
    transaction_type = transaction_obj.transaction_type

    if transaction_type == "income":
        decrease_account_balance(account.id, amount)

    elif transaction_type == "expense":
        if account.account_type in LIABILITY_ACCOUNT_TYPES:
            decrease_account_balance(account.id, amount)
        else:
            increase_account_balance(account.id, amount)

    elif transaction_type == "adjustment":
        decrease_account_balance(account.id, amount)


@login_required
def account_create_view(request):
    form = AccountWebForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        account = form.save(commit=False)
        account.user = request.user
        account.save()

        messages.success(request, "Account created successfully.")
        return redirect("finance_web_accounts")

    return render(request, "finance_web/account_form.html", {
        "form": form,
        "mode": "create",
    })


@login_required
def account_edit_view(request, pk):
    account = get_object_or_404(
        Account,
        pk=pk,
        user=request.user,
    )

    form = AccountWebForm(request.POST or None, instance=account)

    if request.method == "POST" and form.is_valid():
        form.save()

        messages.success(request, "Account updated successfully.")
        return redirect("finance_web_accounts")

    return render(request, "finance_web/account_form.html", {
        "form": form,
        "mode": "edit",
        "account": account,
    })


@login_required
@db_transaction.atomic
def transaction_create_view(request):
    form = TransactionWebForm(
        request.POST or None,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        transaction_obj = form.save(commit=False)
        transaction_obj.user = request.user
        transaction_obj.save()

        try:
            apply_transaction_balance_effect(transaction_obj)
        except DjangoValidationError as error:
            transaction_obj.delete()
            form.add_error(None, error.message if hasattr(error, "message") else str(error))
        else:
            messages.success(request, "Transaction created successfully.")
            return redirect("finance_web_transactions")

    return render(request, "finance_web/transaction_form.html", {
        "form": form,
        "mode": "create",
    })


@login_required
@db_transaction.atomic
def transaction_edit_view(request, pk):
    transaction_obj = get_object_or_404(
        Transaction.objects.select_related("account", "category"),
        pk=pk,
        user=request.user,
    )

    # Prevent editing bill payment transactions for now.
    # This avoids mismatch between the paid bill and the transaction amount.
    if transaction_obj.paid_bills.exists():
        messages.error(
            request,
            "This transaction was created from a paid bill and cannot be edited here.",
        )
        return redirect("finance_web_transactions")

    form = TransactionWebForm(
        request.POST or None,
        instance=transaction_obj,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        old_transaction = Transaction.objects.select_related("account").get(
            pk=transaction_obj.pk,
            user=request.user,
        )

        old_snapshot = Transaction(
            user=old_transaction.user,
            account=old_transaction.account,
            category=old_transaction.category,
            transaction_type=old_transaction.transaction_type,
            title=old_transaction.title,
            amount=old_transaction.amount,
            transaction_date=old_transaction.transaction_date,
            notes=old_transaction.notes,
            reference_no=old_transaction.reference_no,
        )

        try:
            reverse_transaction_balance_effect(old_snapshot)

            updated_transaction = form.save()
            apply_transaction_balance_effect(updated_transaction)

        except DjangoValidationError as error:
            apply_transaction_balance_effect(old_snapshot)
            form.add_error(None, error.message if hasattr(error, "message") else str(error))
        else:
            messages.success(request, "Transaction updated successfully.")
            return redirect("finance_web_transactions")

    return render(request, "finance_web/transaction_form.html", {
        "form": form,
        "mode": "edit",
        "transaction_obj": transaction_obj,
    })

@login_required
@db_transaction.atomic
def transaction_delete_view(request, pk):
    transaction_obj = get_object_or_404(
        Transaction.objects.select_related("account", "category"),
        pk=pk,
        user=request.user,
    )

    if request.method != "POST":
        return redirect("finance_web_transactions")

    if transaction_obj.paid_bills.exists():
        messages.error(
            request,
            "This transaction was created from a paid bill. Use Unmark Paid on the bill to reverse it.",
        )
        return redirect("finance_web_transactions")

    try:
        reverse_transaction_balance_effect(transaction_obj)
        transaction_obj.delete()
    except Exception as error:
        messages.error(request, str(error))
        return redirect("finance_web_transactions")

    messages.success(request, "Transaction deleted and account balance restored.")
    return redirect("finance_web_transactions")


@login_required
def bills_view(request):
    today = timezone.localdate()

    month = int(request.GET.get("month", today.month))
    year = int(request.GET.get("year", today.year))
    status_filter = request.GET.get("status", "all")

    bills = Bill.objects.filter(
        user=request.user,
        due_date__month=month,
        due_date__year=year,
    ).select_related("account", "category", "payment_transaction")

    if status_filter and status_filter != "all":
        bills = bills.filter(status=status_filter)

    bills = bills.order_by("due_date", "name")

    total_due = bills.aggregate(total=Sum("amount_due"))["total"] or 0
    total_paid = bills.aggregate(total=Sum("amount_paid"))["total"] or 0
    total_unpaid = total_due - total_paid

    overdue_count = bills.filter(
        status__in=["unpaid", "partial", "overdue"],
        due_date__lt=today,
    ).count()

    context = {
        "month": month,
        "year": year,
        "status_filter": status_filter,
        "bills": bills,
        "total_due": total_due,
        "total_paid": total_paid,
        "total_unpaid": total_unpaid,
        "overdue_count": overdue_count,
    }

    return render(request, "finance_web/bills.html", context)


@login_required
def bill_create_view(request):
    form = BillWebForm(request.POST or None, user=request.user)

    if request.method == "POST" and form.is_valid():
        bill = form.save(commit=False)
        bill.user = request.user
        bill.save()

        messages.success(request, "Bill created successfully.")
        return redirect("finance_web_bills")

    return render(request, "finance_web/bill_form.html", {
        "form": form,
        "mode": "create",
    })


@login_required
def bill_edit_view(request, pk):
    bill = get_object_or_404(
        Bill,
        pk=pk,
        user=request.user,
    )

    original_status = bill.status

    form = BillWebForm(
        request.POST or None,
        instance=bill,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        new_status = form.cleaned_data.get("status")

        if (
            original_status == "paid"
            and new_status != "paid"
            and bill.payment_transaction_id
        ):
            messages.error(
                request,
                "Use the Unmark Paid button to reverse this bill payment. "
                "Changing the status manually will not restore the account balance.",
            )
            return redirect("finance_web_bill_edit", pk=bill.pk)

        form.save()

        messages.success(request, "Bill updated successfully.")
        return redirect("finance_web_bills")

    return render(request, "finance_web/bill_form.html", {
        "form": form,
        "mode": "edit",
        "bill": bill,
    })


@login_required
@db_transaction.atomic
def bill_mark_paid_view(request, pk):
    bill = get_object_or_404(
        Bill,
        pk=pk,
        user=request.user,
    )

    if request.method != "POST":
        return redirect("finance_web_bills")

    try:
        viewset = BillViewSet()
        viewset.request = request
        viewset.kwargs = {"pk": pk}
        viewset.get_object = lambda: bill
        viewset.get_serializer = lambda obj: None

        # Reuse the same behavior conceptually, but simpler for web:
        if bill.status == "paid":
            messages.info(request, "This bill is already paid.")
            return redirect("finance_web_bills")

        if not bill.account_id:
            messages.error(request, "Please assign an account before marking this bill as paid.")
            return redirect("finance_web_bill_edit", pk=bill.pk)

        if not bill.category_id:
            messages.error(request, "Please assign a category before marking this bill as paid.")
            return redirect("finance_web_bill_edit", pk=bill.pk)

        amount_to_pay = bill.amount_due - bill.amount_paid

        if amount_to_pay <= 0:
            messages.error(request, "This bill has no remaining amount to pay.")
            return redirect("finance_web_bills")

        payment_account = bill.account

        payment_transaction = Transaction.objects.create(
            user=request.user,
            account=payment_account,
            category=bill.category,
            transaction_type="expense",
            title=bill.name,
            amount=amount_to_pay,
            transaction_date=timezone.localdate(),
            notes=f"Payment for bill #{bill.id}: {bill.name}",
        )

        apply_transaction_balance_effect(payment_transaction)

        bill.amount_paid = bill.amount_due
        bill.status = "paid"
        bill.paid_date = timezone.localdate()

        if hasattr(bill, "payment_transaction"):
            bill.payment_transaction = payment_transaction
            bill.save(update_fields=[
                "amount_paid",
                "status",
                "paid_date",
                "payment_transaction",
            ])
        else:
            bill.save(update_fields=[
                "amount_paid",
                "status",
                "paid_date",
            ])

        messages.success(request, "Bill marked as paid and transaction recorded.")
    except Exception as error:
        messages.error(request, str(error))

    return redirect("finance_web_bills")


@login_required
@db_transaction.atomic
def bill_unmark_paid_view(request, pk):
    bill = get_object_or_404(
        Bill,
        pk=pk,
        user=request.user,
    )

    if request.method != "POST":
        return redirect("finance_web_bills")

    if bill.status != "paid":
        messages.error(request, "Only paid bills can be unmarked.")
        return redirect("finance_web_bills")

    if not bill.payment_transaction_id:
        messages.error(
            request,
            "This bill has no linked payment transaction to reverse.",
        )
        return redirect("finance_web_bills")

    payment_transaction = bill.payment_transaction

    previous_amount_paid = bill.amount_due - payment_transaction.amount

    if previous_amount_paid < 0:
        previous_amount_paid = 0

    try:
        reverse_transaction_balance_effect(payment_transaction)
    except Exception as error:
        messages.error(request, str(error))
        return redirect("finance_web_bills")

    bill.payment_transaction = None
    bill.amount_paid = previous_amount_paid
    bill.status = "partial" if previous_amount_paid > 0 else "unpaid"
    bill.paid_date = None

    bill.save(
        update_fields=[
            "payment_transaction",
            "amount_paid",
            "status",
            "paid_date",
        ]
    )

    payment_transaction.delete()

    messages.success(
        request,
        "Bill payment reversed. Linked transaction was deleted.",
    )

    return redirect("finance_web_bills")


@login_required
def recurring_bills_view(request):
    recurring_bills = RecurringBill.objects.filter(
        user=request.user,
    ).select_related("account", "category").order_by("due_day", "name")

    active_count = recurring_bills.filter(is_active=True).count()
    total_monthly = recurring_bills.filter(is_active=True).aggregate(
        total=Sum("amount_due")
    )["total"] or 0

    context = {
        "recurring_bills": recurring_bills,
        "active_count": active_count,
        "total_monthly": total_monthly,
    }

    return render(request, "finance_web/recurring_bills.html", context)


@login_required
def recurring_bill_create_view(request):
    form = RecurringBillWebForm(request.POST or None, user=request.user)

    if request.method == "POST" and form.is_valid():
        recurring_bill = form.save(commit=False)
        recurring_bill.user = request.user
        recurring_bill.save()

        messages.success(request, "Recurring bill created successfully.")
        return redirect("finance_web_recurring_bills")

    return render(request, "finance_web/recurring_bill_form.html", {
        "form": form,
        "mode": "create",
    })


@login_required
def recurring_bill_edit_view(request, pk):
    recurring_bill = get_object_or_404(
        RecurringBill,
        pk=pk,
        user=request.user,
    )

    form = RecurringBillWebForm(
        request.POST or None,
        instance=recurring_bill,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        form.save()

        messages.success(request, "Recurring bill updated successfully.")
        return redirect("finance_web_recurring_bills")

    return render(request, "finance_web/recurring_bill_form.html", {
        "form": form,
        "mode": "edit",
        "recurring_bill": recurring_bill,
    })


@login_required
@db_transaction.atomic
def recurring_bills_generate_view(request):
    today = timezone.localdate()

    month = int(request.POST.get("month", today.month))
    year = int(request.POST.get("year", today.year))

    created_bills, skipped_count = generate_recurring_bills_for_user(
        user=request.user,
        year=year,
        month=month,
    )

    messages.success(
        request,
        f"Generated {len(created_bills)} bill(s). Skipped {skipped_count} existing or inactive bill(s).",
    )

    return redirect("finance_web_recurring_bills")


LIABILITY_ACCOUNT_TYPES = ["credit_card", "loan"]


def apply_transfer_balance_effect(transfer_obj):
    decrease_account_balance(
        transfer_obj.from_account_id,
        transfer_obj.amount,
    )

    if transfer_obj.to_account.account_type in LIABILITY_ACCOUNT_TYPES:
        decrease_account_balance(
            transfer_obj.to_account_id,
            transfer_obj.amount,
        )
    else:
        increase_account_balance(
            transfer_obj.to_account_id,
            transfer_obj.amount,
        )


def reverse_transfer_balance_effect(transfer_obj):
    increase_account_balance(
        transfer_obj.from_account_id,
        transfer_obj.amount,
    )

    if transfer_obj.to_account.account_type in LIABILITY_ACCOUNT_TYPES:
        increase_account_balance(
            transfer_obj.to_account_id,
            transfer_obj.amount,
        )
    else:
        decrease_account_balance(
            transfer_obj.to_account_id,
            transfer_obj.amount,
        )


@login_required
def transfers_view(request):
    today = timezone.localdate()

    month = int(request.GET.get("month", today.month))
    year = int(request.GET.get("year", today.year))
    from_account_id = request.GET.get("from_account", "")
    to_account_id = request.GET.get("to_account", "")

    transfers = Transfer.objects.filter(
        user=request.user,
        transfer_date__month=month,
        transfer_date__year=year,
    ).select_related(
        "from_account",
        "to_account",
    )

    if from_account_id:
        transfers = transfers.filter(from_account_id=from_account_id)

    if to_account_id:
        transfers = transfers.filter(to_account_id=to_account_id)

    transfers = transfers.order_by("-transfer_date", "-created_at")

    total_transferred = transfers.aggregate(
        total=Sum("amount")
    )["total"] or 0

    credit_card_payments = transfers.filter(
        to_account__account_type__in=["credit_card", "loan"]
    ).aggregate(
        total=Sum("amount")
    )["total"] or 0

    accounts = Account.objects.filter(
        user=request.user,
        is_active=True,
    ).order_by("account_type", "name")

    context = {
        "month": month,
        "year": year,
        "from_account_id": from_account_id,
        "to_account_id": to_account_id,
        "transfers": transfers,
        "accounts": accounts,
        "total_transferred": total_transferred,
        "credit_card_payments": credit_card_payments,
    }

    return render(request, "finance_web/transfers.html", context)


@login_required
@db_transaction.atomic
def transfer_create_view(request):
    form = TransferWebForm(
        request.POST or None,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        transfer_obj = form.save(commit=False)
        transfer_obj.user = request.user
        transfer_obj.save()

        try:
            apply_transfer_balance_effect(transfer_obj)
        except Exception as error:
            transfer_obj.delete()
            form.add_error(None, str(error))
        else:
            messages.success(request, "Transfer created successfully.")
            return redirect("finance_web_transfers")

    return render(request, "finance_web/transfer_form.html", {
        "form": form,
        "mode": "create",
    })


@login_required
@db_transaction.atomic
def transfer_edit_view(request, pk):
    transfer_obj = get_object_or_404(
        Transfer.objects.select_related("from_account", "to_account"),
        pk=pk,
        user=request.user,
    )

    form = TransferWebForm(
        request.POST or None,
        instance=transfer_obj,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        old_transfer = Transfer.objects.select_related(
            "from_account",
            "to_account",
        ).get(
            pk=transfer_obj.pk,
            user=request.user,
        )

        old_snapshot = Transfer(
            user=old_transfer.user,
            from_account=old_transfer.from_account,
            to_account=old_transfer.to_account,
            amount=old_transfer.amount,
            transfer_date=old_transfer.transfer_date,
            notes=old_transfer.notes,
        )

        old_snapshot.from_account_id = old_transfer.from_account_id
        old_snapshot.to_account_id = old_transfer.to_account_id

        try:
            reverse_transfer_balance_effect(old_snapshot)

            updated_transfer = form.save()
            apply_transfer_balance_effect(updated_transfer)

        except Exception as error:
            apply_transfer_balance_effect(old_snapshot)
            form.add_error(None, str(error))
        else:
            messages.success(request, "Transfer updated successfully.")
            return redirect("finance_web_transfers")

    return render(request, "finance_web/transfer_form.html", {
        "form": form,
        "mode": "edit",
        "transfer_obj": transfer_obj,
    })


@login_required
@db_transaction.atomic
def transfer_delete_view(request, pk):
    transfer_obj = get_object_or_404(
        Transfer.objects.select_related("from_account", "to_account"),
        pk=pk,
        user=request.user,
    )

    if request.method != "POST":
        return redirect("finance_web_transfers")

    try:
        reverse_transfer_balance_effect(transfer_obj)
        transfer_obj.delete()
    except Exception as error:
        messages.error(request, str(error))
        return redirect("finance_web_transfers")

    messages.success(request, "Transfer deleted and account balances restored.")
    return redirect("finance_web_transfers")


@login_required
def debts_view(request):
    debts = Debt.objects.filter(
        user=request.user,
    ).order_by("is_active", "name")

    active_debts = debts.filter(is_active=True)

    total_original = active_debts.aggregate(
        total=Sum("original_amount")
    )["total"] or 0

    total_balance = active_debts.aggregate(
        total=Sum("current_balance")
    )["total"] or 0

    total_minimum = active_debts.aggregate(
        total=Sum("minimum_payment")
    )["total"] or 0

    payments = DebtPayment.objects.filter(
        user=request.user,
    ).select_related(
        "debt",
        "account",
    ).order_by("-payment_date", "-created_at")[:10]

    context = {
        "debts": debts,
        "payments": payments,
        "total_original": total_original,
        "total_balance": total_balance,
        "total_minimum": total_minimum,
        "active_count": active_debts.count(),
    }

    return render(request, "finance_web/debts.html", context)


@login_required
def debt_create_view(request):
    form = DebtWebForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        debt = form.save(commit=False)
        debt.user = request.user
        debt.save()

        messages.success(request, "Debt created successfully.")
        return redirect("finance_web_debts")

    return render(request, "finance_web/debt_form.html", {
        "form": form,
        "mode": "create",
    })


@login_required
def debt_edit_view(request, pk):
    debt = get_object_or_404(
        Debt,
        pk=pk,
        user=request.user,
    )

    form = DebtWebForm(request.POST or None, instance=debt)

    if request.method == "POST" and form.is_valid():
        form.save()

        messages.success(request, "Debt updated successfully.")
        return redirect("finance_web_debts")

    return render(request, "finance_web/debt_form.html", {
        "form": form,
        "mode": "edit",
        "debt": debt,
    })


@login_required
@db_transaction.atomic
def debt_payment_create_view(request):
    debt_id = request.GET.get("debt")
    debt = None

    if debt_id:
        debt = get_object_or_404(
            Debt,
            pk=debt_id,
            user=request.user,
        )

    form = DebtPaymentWebForm(
        request.POST or None,
        user=request.user,
        debt=debt,
    )

    if request.method == "POST" and form.is_valid():
        payment = form.save(commit=False)
        payment.user = request.user

        try:
            if payment.account_id:
                decrease_account_balance(payment.account_id, payment.amount)

            decrease_debt_balance(payment.debt_id, payment.principal_amount)

            payment.save()

        except Exception as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, "Debt payment recorded successfully.")
            return redirect("finance_web_debts")

    return render(request, "finance_web/debt_payment_form.html", {
        "form": form,
        "mode": "create",
    })


@login_required
@db_transaction.atomic
def debt_payment_edit_view(request, pk):
    payment = get_object_or_404(
        DebtPayment.objects.select_related("debt", "account"),
        pk=pk,
        user=request.user,
    )

    form = DebtPaymentWebForm(
        request.POST or None,
        instance=payment,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        old_payment = DebtPayment.objects.select_related("debt", "account").get(
            pk=payment.pk,
            user=request.user,
        )

        try:
            # Reverse old effect
            if old_payment.account_id:
                increase_account_balance(old_payment.account_id, old_payment.amount)

            increase_debt_balance(old_payment.debt_id, old_payment.principal_amount)

            # Save new payment
            updated_payment = form.save(commit=False)

            # Apply new effect
            if updated_payment.account_id:
                decrease_account_balance(updated_payment.account_id, updated_payment.amount)

            decrease_debt_balance(updated_payment.debt_id, updated_payment.principal_amount)

            updated_payment.save()

        except Exception as error:
            # Restore old effect if new save fails
            if old_payment.account_id:
                decrease_account_balance(old_payment.account_id, old_payment.amount)

            decrease_debt_balance(old_payment.debt_id, old_payment.principal_amount)

            form.add_error(None, str(error))
        else:
            messages.success(request, "Debt payment updated successfully.")
            return redirect("finance_web_debts")

    return render(request, "finance_web/debt_payment_form.html", {
        "form": form,
        "mode": "edit",
        "payment": payment,
    })


@login_required
@db_transaction.atomic
def debt_payment_delete_view(request, pk):
    payment = get_object_or_404(
        DebtPayment.objects.select_related("debt", "account"),
        pk=pk,
        user=request.user,
    )

    if request.method != "POST":
        return redirect("finance_web_debts")

    try:
        if payment.account_id:
            increase_account_balance(payment.account_id, payment.amount)

        increase_debt_balance(payment.debt_id, payment.principal_amount)

        payment.delete()

    except Exception as error:
        messages.error(request, str(error))
        return redirect("finance_web_debts")

    messages.success(request, "Debt payment deleted and balances restored.")
    return redirect("finance_web_debts")


def update_money_lent_status(money_lent):
    if money_lent.current_balance <= 0:
        money_lent.current_balance = 0
        money_lent.status = "paid"
    elif money_lent.current_balance < money_lent.original_amount:
        money_lent.status = "partial"
    else:
        money_lent.status = "active"

    money_lent.save(update_fields=["current_balance", "status"])


def increase_money_lent_balance(money_lent_id, amount):
    money_lent = MoneyLent.objects.select_for_update().get(id=money_lent_id)
    money_lent.current_balance += amount
    update_money_lent_status(money_lent)


def decrease_money_lent_balance(money_lent_id, amount):
    money_lent = MoneyLent.objects.select_for_update().get(id=money_lent_id)

    if money_lent.current_balance - amount < 0:
        raise DjangoValidationError("Payment cannot exceed remaining balance.")

    money_lent.current_balance -= amount
    update_money_lent_status(money_lent)


@login_required
def money_lent_view(request):
    money_lent_records = MoneyLent.objects.filter(
        user=request.user,
    ).select_related("account").order_by("-lent_date", "-created_at")

    active_records = money_lent_records.filter(
        status__in=["active", "partial"]
    )

    total_lent = money_lent_records.aggregate(
        total=Sum("original_amount")
    )["total"] or 0

    total_receivable = active_records.aggregate(
        total=Sum("current_balance")
    )["total"] or 0

    paid_count = money_lent_records.filter(status="paid").count()

    payments = MoneyLentPayment.objects.filter(
        user=request.user,
    ).select_related(
        "money_lent",
        "account",
    ).order_by("-payment_date", "-created_at")[:10]

    context = {
        "money_lent_records": money_lent_records,
        "payments": payments,
        "total_lent": total_lent,
        "total_receivable": total_receivable,
        "active_count": active_records.count(),
        "paid_count": paid_count,
    }

    return render(request, "finance_web/money_lent.html", context)


@login_required
@db_transaction.atomic
def money_lent_create_view(request):
    initial = {
        "lent_date": timezone.localdate(),
    }

    form = MoneyLentWebForm(
        request.POST or None,
        user=request.user,
        initial=initial,
    )

    if request.method == "POST" and form.is_valid():
        money_lent = form.save(commit=False)
        money_lent.user = request.user
        money_lent.current_balance = money_lent.original_amount

        try:
            if money_lent.account_id:
                decrease_account_balance(
                    money_lent.account_id,
                    money_lent.original_amount,
                )

            money_lent.save()

        except Exception as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, "Money lent recorded successfully.")
            return redirect("finance_web_money_lent")

    return render(request, "finance_web/money_lent_form.html", {
        "form": form,
        "mode": "create",
    })


@login_required
@db_transaction.atomic
def money_lent_edit_view(request, pk):
    money_lent = get_object_or_404(
        MoneyLent.objects.select_related("account"),
        pk=pk,
        user=request.user,
    )

    form = MoneyLentWebForm(
        request.POST or None,
        instance=money_lent,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        old_money_lent = MoneyLent.objects.select_related("account").get(
            pk=money_lent.pk,
            user=request.user,
        )

        old_account_id = old_money_lent.account_id
        old_original_amount = old_money_lent.original_amount

        total_payments = old_money_lent.payments.aggregate(
            total=Sum("amount")
        )["total"] or 0

        try:
            # Reverse old lend effect.
            if old_account_id:
                increase_account_balance(old_account_id, old_original_amount)

            updated_money_lent = form.save(commit=False)
            updated_money_lent.user = request.user
            updated_money_lent.current_balance = (
                updated_money_lent.original_amount - total_payments
            )

            if updated_money_lent.current_balance < 0:
                raise DjangoValidationError(
                    "Original amount cannot be lower than total payments."
                )

            # Apply new lend effect.
            if updated_money_lent.account_id:
                decrease_account_balance(
                    updated_money_lent.account_id,
                    updated_money_lent.original_amount,
                )

            updated_money_lent.save()
            update_money_lent_status(updated_money_lent)

        except Exception as error:
            # Restore old effect if edit fails.
            if old_account_id:
                decrease_account_balance(old_account_id, old_original_amount)

            form.add_error(None, str(error))
        else:
            messages.success(request, "Money lent updated successfully.")
            return redirect("finance_web_money_lent")

    return render(request, "finance_web/money_lent_form.html", {
        "form": form,
        "mode": "edit",
        "money_lent": money_lent,
    })


@login_required
@db_transaction.atomic
def money_lent_delete_view(request, pk):
    money_lent = get_object_or_404(
        MoneyLent.objects.select_related("account"),
        pk=pk,
        user=request.user,
    )

    if request.method != "POST":
        return redirect("finance_web_money_lent")

    try:
        # Reverse all received payments first.
        payments = MoneyLentPayment.objects.filter(
            money_lent=money_lent,
            user=request.user,
        ).select_related("account")

        for payment in payments:
            if payment.account_id:
                decrease_account_balance(payment.account_id, payment.amount)

        # Reverse original money lent.
        if money_lent.account_id:
            increase_account_balance(
                money_lent.account_id,
                money_lent.original_amount,
            )

        money_lent.delete()

    except Exception as error:
        messages.error(request, str(error))
        return redirect("finance_web_money_lent")

    messages.success(request, "Money lent record deleted and balances restored.")
    return redirect("finance_web_money_lent")


@login_required
@db_transaction.atomic
def money_lent_payment_create_view(request):
    money_lent_id = request.GET.get("money_lent")
    money_lent = None

    if money_lent_id:
        money_lent = get_object_or_404(
            MoneyLent,
            pk=money_lent_id,
            user=request.user,
        )

    initial = {
        "payment_date": timezone.localdate(),
    }

    form = MoneyLentPaymentWebForm(
        request.POST or None,
        user=request.user,
        money_lent=money_lent,
        initial=initial,
    )

    if request.method == "POST" and form.is_valid():
        payment = form.save(commit=False)
        payment.user = request.user

        try:
            if payment.account_id:
                increase_account_balance(payment.account_id, payment.amount)

            decrease_money_lent_balance(
                payment.money_lent_id,
                payment.amount,
            )

            payment.save()

        except Exception as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, "Money lent payment recorded successfully.")
            return redirect("finance_web_money_lent")

    return render(request, "finance_web/money_lent_payment_form.html", {
        "form": form,
        "mode": "create",
    })


@login_required
@db_transaction.atomic
def money_lent_payment_edit_view(request, pk):
    payment = get_object_or_404(
        MoneyLentPayment.objects.select_related("money_lent", "account"),
        pk=pk,
        user=request.user,
    )

    form = MoneyLentPaymentWebForm(
        request.POST or None,
        instance=payment,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        old_payment = MoneyLentPayment.objects.select_related(
            "money_lent",
            "account",
        ).get(
            pk=payment.pk,
            user=request.user,
        )

        try:
            # Reverse old payment effect.
            if old_payment.account_id:
                decrease_account_balance(
                    old_payment.account_id,
                    old_payment.amount,
                )

            increase_money_lent_balance(
                old_payment.money_lent_id,
                old_payment.amount,
            )

            # Apply updated payment effect.
            updated_payment = form.save(commit=False)
            updated_payment.user = request.user

            if updated_payment.account_id:
                increase_account_balance(
                    updated_payment.account_id,
                    updated_payment.amount,
                )

            decrease_money_lent_balance(
                updated_payment.money_lent_id,
                updated_payment.amount,
            )

            updated_payment.save()

        except Exception as error:
            # Restore old effect if edit fails.
            if old_payment.account_id:
                increase_account_balance(
                    old_payment.account_id,
                    old_payment.amount,
                )

            decrease_money_lent_balance(
                old_payment.money_lent_id,
                old_payment.amount,
            )

            form.add_error(None, str(error))
        else:
            messages.success(request, "Money lent payment updated successfully.")
            return redirect("finance_web_money_lent")

    return render(request, "finance_web/money_lent_payment_form.html", {
        "form": form,
        "mode": "edit",
        "payment": payment,
    })


@login_required
@db_transaction.atomic
def money_lent_payment_delete_view(request, pk):
    payment = get_object_or_404(
        MoneyLentPayment.objects.select_related("money_lent", "account"),
        pk=pk,
        user=request.user,
    )

    if request.method != "POST":
        return redirect("finance_web_money_lent")

    try:
        if payment.account_id:
            decrease_account_balance(payment.account_id, payment.amount)

        increase_money_lent_balance(
            payment.money_lent_id,
            payment.amount,
        )

        payment.delete()

    except Exception as error:
        messages.error(request, str(error))
        return redirect("finance_web_money_lent")

    messages.success(request, "Money lent payment deleted and balances restored.")
    return redirect("finance_web_money_lent")


@login_required
def goals_view(request):
    goals = SavingsGoal.objects.filter(
        user=request.user,
    ).order_by("is_completed", "target_date", "name")

    active_goals = goals.filter(is_completed=False)

    total_target = active_goals.aggregate(
        total=Sum("target_amount")
    )["total"] or 0

    total_saved = active_goals.aggregate(
        total=Sum("current_amount")
    )["total"] or 0

    overall_progress = 0
    if total_target > 0:
        overall_progress = round((total_saved / total_target) * 100, 2)

    contributions = GoalContribution.objects.filter(
        user=request.user,
    ).select_related(
        "goal",
        "account",
    ).order_by("-contribution_date", "-created_at")[:10]

    context = {
        "goals": goals,
        "contributions": contributions,
        "active_count": active_goals.count(),
        "total_target": total_target,
        "total_saved": total_saved,
        "overall_progress": overall_progress,
    }

    return render(request, "finance_web/goals.html", context)


@login_required
def goal_create_view(request):
    form = SavingsGoalWebForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        goal = form.save(commit=False)
        goal.user = request.user
        goal.save()

        messages.success(request, "Savings goal created successfully.")
        return redirect("finance_web_goals")

    return render(request, "finance_web/goal_form.html", {
        "form": form,
        "mode": "create",
    })


@login_required
def goal_edit_view(request, pk):
    goal = get_object_or_404(
        SavingsGoal,
        pk=pk,
        user=request.user,
    )

    form = SavingsGoalWebForm(
        request.POST or None,
        instance=goal,
    )

    if request.method == "POST" and form.is_valid():
        form.save()

        messages.success(request, "Savings goal updated successfully.")
        return redirect("finance_web_goals")

    return render(request, "finance_web/goal_form.html", {
        "form": form,
        "mode": "edit",
        "goal": goal,
    })


@login_required
@db_transaction.atomic
def goal_contribution_create_view(request):
    goal_id = request.GET.get("goal")
    goal = None

    if goal_id:
        goal = get_object_or_404(
            SavingsGoal,
            pk=goal_id,
            user=request.user,
        )

    form = GoalContributionWebForm(
        request.POST or None,
        user=request.user,
        goal=goal,
    )

    if request.method == "POST" and form.is_valid():
        contribution = form.save(commit=False)
        contribution.user = request.user

        try:
            if contribution.account_id:
                decrease_account_balance(
                    contribution.account_id,
                    contribution.amount,
                )

            increase_goal_amount(
                contribution.goal_id,
                contribution.amount,
            )

            contribution.save()

            # Auto-complete the goal if target is reached.
            contribution.goal.refresh_from_db()
            if contribution.goal.current_amount >= contribution.goal.target_amount:
                contribution.goal.is_completed = True
                contribution.goal.save(update_fields=["is_completed"])

        except Exception as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, "Goal contribution recorded successfully.")
            return redirect("finance_web_goals")

    return render(request, "finance_web/goal_contribution_form.html", {
        "form": form,
        "mode": "create",
    })


@login_required
@db_transaction.atomic
def goal_contribution_edit_view(request, pk):
    contribution = get_object_or_404(
        GoalContribution.objects.select_related("goal", "account"),
        pk=pk,
        user=request.user,
    )

    form = GoalContributionWebForm(
        request.POST or None,
        instance=contribution,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        old_contribution = GoalContribution.objects.select_related(
            "goal",
            "account",
        ).get(
            pk=contribution.pk,
            user=request.user,
        )

        try:
            # Reverse old effect.
            if old_contribution.account_id:
                increase_account_balance(
                    old_contribution.account_id,
                    old_contribution.amount,
                )

            decrease_goal_amount(
                old_contribution.goal_id,
                old_contribution.amount,
            )

            # Save new contribution.
            updated_contribution = form.save(commit=False)

            # Apply new effect.
            if updated_contribution.account_id:
                decrease_account_balance(
                    updated_contribution.account_id,
                    updated_contribution.amount,
                )

            increase_goal_amount(
                updated_contribution.goal_id,
                updated_contribution.amount,
            )

            updated_contribution.save()

            updated_contribution.goal.refresh_from_db()
            updated_contribution.goal.is_completed = (
                updated_contribution.goal.current_amount >= updated_contribution.goal.target_amount
            )
            updated_contribution.goal.save(update_fields=["is_completed"])

            old_contribution.goal.refresh_from_db()
            old_contribution.goal.is_completed = (
                old_contribution.goal.current_amount >= old_contribution.goal.target_amount
            )
            old_contribution.goal.save(update_fields=["is_completed"])

        except Exception as error:
            # Restore old effect if new save fails.
            if old_contribution.account_id:
                decrease_account_balance(
                    old_contribution.account_id,
                    old_contribution.amount,
                )

            increase_goal_amount(
                old_contribution.goal_id,
                old_contribution.amount,
            )

            form.add_error(None, str(error))
        else:
            messages.success(request, "Goal contribution updated successfully.")
            return redirect("finance_web_goals")

    return render(request, "finance_web/goal_contribution_form.html", {
        "form": form,
        "mode": "edit",
        "contribution": contribution,
    })


@login_required
@db_transaction.atomic
def goal_contribution_delete_view(request, pk):
    contribution = get_object_or_404(
        GoalContribution.objects.select_related("goal", "account"),
        pk=pk,
        user=request.user,
    )

    if request.method != "POST":
        return redirect("finance_web_goals")

    goal = contribution.goal

    try:
        if contribution.account_id:
            increase_account_balance(
                contribution.account_id,
                contribution.amount,
            )

        decrease_goal_amount(
            contribution.goal_id,
            contribution.amount,
        )

        contribution.delete()

        goal.refresh_from_db()
        goal.is_completed = goal.current_amount >= goal.target_amount
        goal.save(update_fields=["is_completed"])

    except Exception as error:
        messages.error(request, str(error))
        return redirect("finance_web_goals")

    messages.success(request, "Goal contribution deleted and balances restored.")
    return redirect("finance_web_goals")


@login_required
def categories_view(request):
    category_type = request.GET.get("type", "all")
    status = request.GET.get("status", "active")

    categories = Category.objects.filter(
        user=request.user,
    ).order_by("category_type", "name")

    if category_type and category_type != "all":
        categories = categories.filter(category_type=category_type)

    if status == "active":
        categories = categories.filter(is_active=True)
    elif status == "inactive":
        categories = categories.filter(is_active=False)

    income_count = Category.objects.filter(
        user=request.user,
        category_type="income",
        is_active=True,
    ).count()

    expense_count = Category.objects.filter(
        user=request.user,
        category_type="expense",
        is_active=True,
    ).count()

    transfer_count = Category.objects.filter(
        user=request.user,
        category_type="transfer",
        is_active=True,
    ).count()

    context = {
        "categories": categories,
        "category_type": category_type,
        "status": status,
        "income_count": income_count,
        "expense_count": expense_count,
        "transfer_count": transfer_count,
    }

    return render(request, "finance_web/categories.html", context)


@login_required
def category_create_view(request):
    form = CategoryWebForm(
        request.POST or None,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        category = form.save(commit=False)
        category.user = request.user
        category.save()

        messages.success(request, "Category created successfully.")
        return redirect("finance_web_categories")

    return render(request, "finance_web/category_form.html", {
        "form": form,
        "mode": "create",
    })


@login_required
def category_edit_view(request, pk):
    category = get_object_or_404(
        Category,
        pk=pk,
        user=request.user,
    )

    form = CategoryWebForm(
        request.POST or None,
        instance=category,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        form.save()

        messages.success(request, "Category updated successfully.")
        return redirect("finance_web_categories")

    return render(request, "finance_web/category_form.html", {
        "form": form,
        "mode": "edit",
        "category": category,
    })


@login_required
def reports_view(request):
    today = timezone.localdate()

    month = int(request.GET.get("month", today.month))
    year = int(request.GET.get("year", today.year))

    transactions = Transaction.objects.filter(
        user=request.user,
        transaction_date__month=month,
        transaction_date__year=year,
    ).select_related("account", "category")

    accounts = Account.objects.filter(
        user=request.user,
        is_active=True,
    )

    bills = Bill.objects.filter(
        user=request.user,
        due_date__month=month,
        due_date__year=year,
    )

    budgets = Budget.objects.filter(
        user=request.user,
        month=month,
        year=year,
    ).select_related("category")

    debts = Debt.objects.filter(
        user=request.user,
        is_active=True,
    )

    goals = SavingsGoal.objects.filter(
        user=request.user,
    )

    total_income = transactions.filter(
        transaction_type="income",
    ).aggregate(total=Sum("amount"))["total"] or 0

    total_expense = transactions.filter(
        transaction_type="expense",
    ).aggregate(total=Sum("amount"))["total"] or 0

    net_cashflow = total_income - total_expense

    expense_by_category = (
        transactions
        .filter(transaction_type="expense", category__isnull=False)
        .values("category__name")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )

    income_by_category = (
        transactions
        .filter(transaction_type="income", category__isnull=False)
        .values("category__name")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )

    asset_types = ["cash", "bank", "ewallet", "investment"]
    liability_types = ["credit_card", "loan"]

    total_assets = accounts.filter(
        account_type__in=asset_types,
    ).aggregate(total=Sum("current_balance"))["total"] or 0

    liability_accounts = accounts.filter(
        account_type__in=liability_types,
    )

    total_account_liabilities = sum(
        abs(account.current_balance)
        for account in liability_accounts
        if account.current_balance != 0
    )

    total_debt_balance = debts.aggregate(
        total=Sum("current_balance"),
    )["total"] or 0

    total_liabilities = total_account_liabilities + total_debt_balance
    net_worth = total_assets - total_liabilities

    total_bills_due = bills.aggregate(
        total=Sum("amount_due"),
    )["total"] or 0

    total_bills_paid = bills.aggregate(
        total=Sum("amount_paid"),
    )["total"] or 0

    unpaid_bills_total = total_bills_due - total_bills_paid

    paid_bills_count = bills.filter(status="paid").count()
    unpaid_bills_count = bills.exclude(status="paid").count()

    total_budget_limit = budgets.aggregate(
        total=Sum("amount_limit")
    )["total"] or 0

    budget_category_ids = list(
        budgets.values_list("category_id", flat=True)
    )

    total_budget_spent = transactions.filter(
        transaction_type="expense",
        category_id__in=budget_category_ids,
    ).aggregate(
        total=Sum("amount")
    )["total"] or 0

    total_budget_remaining = total_budget_limit - total_budget_spent

    budget_usage_percent = 0
    if total_budget_limit > 0:
        budget_usage_percent = round((total_budget_spent / total_budget_limit) * 100, 2)

    budget_rows = []

    for budget in budgets:
        spent = transactions.filter(
            transaction_type="expense",
            category=budget.category,
        ).aggregate(total=Sum("amount"))["total"] or 0

        remaining = budget.amount_limit - spent

        progress_percent = 0
        if budget.amount_limit > 0:
            progress_percent = round((spent / budget.amount_limit) * 100, 2)

        budget_rows.append({
            "category_name": budget.category.name,
            "amount_limit": budget.amount_limit,
            "spent": spent,
            "remaining": remaining,
            "progress_percent": progress_percent,
            "is_over": spent > budget.amount_limit,
        })

    total_goal_target = goals.aggregate(
        total=Sum("target_amount"),
    )["total"] or 0

    total_goal_saved = goals.aggregate(
        total=Sum("current_amount"),
    )["total"] or 0

    goal_progress_percent = 0
    if total_goal_target > 0:
        goal_progress_percent = round((total_goal_saved / total_goal_target) * 100, 2)

    expense_by_category_text = "\n".join(
        [
            f"- {item['category__name']}: ₱{item['total']}"
            for item in expense_by_category
        ]
    ) or "No expense category data."

    budget_rows_text = "\n".join(
        [
            (
                f"- {row['category_name']}: "
                f"spent ₱{row['spent']} of ₱{row['amount_limit']} "
                f"({row['progress_percent']}% used)"
            )
            for row in budget_rows
        ]
    ) or "No budget category data."

    ai_summary = None

    if request.GET.get("ai") == "1":
        report_data = {
            "month": month,
            "year": year,
            "total_income": total_income,
            "total_expense": total_expense,
            "net_cashflow": net_cashflow,
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "net_worth": net_worth,
            "total_budget_limit": total_budget_limit,
            "total_budget_spent": total_budget_spent,
            "total_budget_remaining": total_budget_remaining,
            "budget_usage_percent": budget_usage_percent,
            "total_bills_due": total_bills_due,
            "total_bills_paid": total_bills_paid,
            "unpaid_bills_total": unpaid_bills_total,
            "total_debt_balance": total_debt_balance,
            "total_goal_target": total_goal_target,
            "total_goal_saved": total_goal_saved,
            "goal_progress_percent": goal_progress_percent,
            "expense_by_category_text": expense_by_category_text,
            "budget_rows_text": budget_rows_text,
        }

        try:
            ai_summary = generate_report_ai_summary(report_data)
        except Exception as error:
            ai_summary = f"AI summary failed: {error}"

    context = {
        "month": month,
        "year": year,

        "total_income": total_income,
        "total_expense": total_expense,
        "net_cashflow": net_cashflow,

        "expense_by_category": expense_by_category,
        "income_by_category": income_by_category,

        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": net_worth,

        "total_bills_due": total_bills_due,
        "total_bills_paid": total_bills_paid,
        "unpaid_bills_total": unpaid_bills_total,
        "paid_bills_count": paid_bills_count,
        "unpaid_bills_count": unpaid_bills_count,

        "total_budget_limit": total_budget_limit,
        "total_budget_spent": total_budget_spent,
        "total_budget_remaining": total_budget_remaining,
        "budget_usage_percent": budget_usage_percent,
        "budget_rows": budget_rows,

        "total_debt_balance": total_debt_balance,
        "total_goal_target": total_goal_target,
        "total_goal_saved": total_goal_saved,
        "goal_progress_percent": goal_progress_percent,

        "ai_summary": ai_summary,
    }

    return render(request, "finance_web/reports.html", context)


@login_required
def budgets_view(request):
    today = timezone.localdate()

    month = int(request.GET.get("month", today.month))
    year = int(request.GET.get("year", today.year))

    budgets = Budget.objects.filter(
        user=request.user,
        month=month,
        year=year,
    ).select_related("category").order_by("category__name")

    transactions = Transaction.objects.filter(
        user=request.user,
        transaction_type="expense",
        transaction_date__month=month,
        transaction_date__year=year,
    )

    budget_rows = []

    total_limit = 0
    total_spent = 0

    for budget in budgets:
        spent = transactions.filter(
            category=budget.category,
        ).aggregate(total=Sum("amount"))["total"] or 0

        remaining = budget.amount_limit - spent

        progress_percent = 0
        if budget.amount_limit > 0:
            progress_percent = round((spent / budget.amount_limit) * 100, 2)

        total_limit += budget.amount_limit
        total_spent += spent

        budget_rows.append({
            "budget": budget,
            "spent": spent,
            "remaining": remaining,
            "progress_percent": progress_percent,
            "is_over": spent > budget.amount_limit,
        })

    total_remaining = total_limit - total_spent

    total_usage_percent = 0
    if total_limit > 0:
        total_usage_percent = round((total_spent / total_limit) * 100, 2)

    context = {
        "month": month,
        "year": year,
        "budgets": budgets,
        "budget_rows": budget_rows,
        "total_limit": total_limit,
        "total_spent": total_spent,
        "total_remaining": total_remaining,
        "total_usage_percent": total_usage_percent,
    }

    return render(request, "finance_web/budgets.html", context)


@login_required
def budget_create_view(request):
    today = timezone.localdate()

    initial = {
        "month": request.GET.get("month", today.month),
        "year": request.GET.get("year", today.year),
    }

    form = BudgetWebForm(
        request.POST or None,
        user=request.user,
        initial=initial,
    )

    if request.method == "POST" and form.is_valid():
        budget = form.save(commit=False)
        budget.user = request.user
        budget.save()

        messages.success(request, "Budget created successfully.")
        return redirect("finance_web_budgets")

    return render(request, "finance_web/budget_form.html", {
        "form": form,
        "mode": "create",
    })


@login_required
def budget_edit_view(request, pk):
    budget = get_object_or_404(
        Budget,
        pk=pk,
        user=request.user,
    )

    form = BudgetWebForm(
        request.POST or None,
        instance=budget,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        form.save()

        messages.success(request, "Budget updated successfully.")
        return redirect("finance_web_budgets")

    return render(request, "finance_web/budget_form.html", {
        "form": form,
        "mode": "edit",
        "budget": budget,
    })


@login_required
def budget_delete_view(request, pk):
    budget = get_object_or_404(
        Budget,
        pk=pk,
        user=request.user,
    )

    if request.method != "POST":
        return redirect("finance_web_budgets")

    budget.delete()

    messages.success(request, "Budget deleted successfully.")
    return redirect("finance_web_budgets")


def extract_amount(text):
    matches = re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", text)

    if not matches:
        return None

    raw_amount = matches[-1].replace(",", "")

    try:
        return Decimal(raw_amount)
    except InvalidOperation:
        return None


def remove_amount_from_text(text, amount):
    if amount is None:
        return text.strip()

    amount_text = str(amount).rstrip("0").rstrip(".")
    cleaned = re.sub(r"\d+(?:,\d{3})*(?:\.\d+)?", "", text, count=1)
    return cleaned.strip()

def find_account_by_text(user, account_text):
    account_text = clean_search_text(account_text)

    accounts = Account.objects.filter(
        user=user,
        is_active=True,
    )

    for account in accounts:
        haystack = clean_search_text(
            f"{account.name or ''} {account.institution_name or ''}"
        )

        if account_text and account_text in haystack:
            return account

        for word in account_text.split():
            if len(word) >= 2 and word in haystack:
                return account

    return None


def parse_transfer_command(user, message, amount):
    text = message.lower()

    patterns = [
        # transfer 100 from BPI to BDO
        r"(?:transfer|send|move)?\s*\d+(?:,\d{3})*(?:\.\d+)?\s+from\s+(.+?)\s+to\s+(.+)$",

        # transfer from BPI to BDO 100
        r"(?:transfer|send|move)?\s*from\s+(.+?)\s+to\s+(.+?)\s+\d+(?:,\d{3})*(?:\.\d+)?$",

        # BPI to BDO 100
        r"(.+?)\s+to\s+(.+?)\s+\d+(?:,\d{3})*(?:\.\d+)?$",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue

        from_text = clean_search_text(match.group(1))
        to_text = clean_search_text(match.group(2))

        from_account = find_account_by_text(user, from_text)
        to_account = find_account_by_text(user, to_text)

        return from_account, to_account

    return None, None


def find_best_account(user, text):
    text = text.lower()

    accounts = Account.objects.filter(
        user=user,
        is_active=True,
    )

    for account in accounts:
        haystack = f"{account.name} {account.institution_name}".lower()
        if account.name.lower() in text or any(word in haystack for word in text.split()):
            return account

    return accounts.exclude(
        account_type__in=["credit_card", "loan"]
    ).first()


def find_expense_category(user, text):
    text = text.lower()

    categories = Category.objects.filter(
        user=user,
        is_active=True,
        category_type="expense",
    )

    keyword_map = {
        "groceries": [
            "grocery", "groceries", "supermarket", "market",
            "puregold", "sm", "savemore", "waltermart",
            "landmark", "robinsons", "s&r", "snr",
            "vegetable", "meat", "fish", "rice"
        ],
        "food": [
            "jollibee", "mcdo", "mcdonald", "kfc", "chowking",
            "restaurant", "dining", "meal", "lunch", "dinner",
            "breakfast", "coffee", "starbucks"
        ],
        "utilities": [
            "meralco", "electric", "water", "internet", "wifi", "bill"
        ],
        "transport": [
            "grab", "taxi", "gas", "fuel", "fare"
        ],
        "entertainment": [
            "netflix", "spotify", "game", "movie"
        ],
    }

    # Exact/partial category name match first.
    for category in categories:
        category_name = category.name.lower()

        if category_name in text:
            return category

    # Keyword-based category match.
    for keyword, words in keyword_map.items():
        if not any(word in text for word in words):
            continue

        for category in categories:
            category_name = category.name.lower()

            if keyword in category_name:
                return category

            if keyword == "groceries" and "grocery" in category_name:
                return category

            if keyword == "groceries" and "food" in category_name and "grocer" in category_name:
                return category

            if keyword == "food" and "dining" in category_name:
                return category

    return categories.first()


def find_income_category(user, text):
    text = text.lower()

    categories = Category.objects.filter(
        user=user,
        is_active=True,
        category_type="income",
    )

    for category in categories:
        if category.name.lower() in text:
            return category

    salary_category = categories.filter(name__icontains="salary").first()
    return salary_category or categories.first()


def extract_account_from_text(user, text):
    """
    Detect account phrases like:
    - pay from BPI
    - from BPI
    - using GCash
    - via Cash Wallet
    - paid with BPI
    """
    lowered = text.lower()

    account_phrase_patterns = [
        r"(?:pay\s+from|from|using|via|with|paid\s+with)\s+(.+)$",
    ]

    possible_account_text = ""

    for pattern in account_phrase_patterns:
        match = re.search(pattern, lowered)
        if match:
            possible_account_text = match.group(1).strip()
            break

    accounts = Account.objects.filter(
        user=user,
        is_active=True,
    )

    # If phrase found, prioritize matching that part only.
    if possible_account_text:
        possible_account_text = re.sub(
            r"\d+(?:,\d{3})*(?:\.\d+)?",
            "",
            possible_account_text,
        ).strip()

        for account in accounts:
            haystack = f"{account.name} {account.institution_name}".lower()

            if possible_account_text in haystack:
                return account

            for word in possible_account_text.split():
                if len(word) >= 2 and word in haystack:
                    return account

    # Fallback: look at the whole message.
    for account in accounts:
        haystack = f"{account.name} {account.institution_name}".lower()

        if account.name.lower() in lowered:
            return account

        if account.institution_name and account.institution_name.lower() in lowered:
            return account

    return None


def clean_expense_title(text, amount):
    title = remove_amount_from_text(text, amount)

    # Remove account instruction phrases from title.
    title = re.sub(
        r",?\s*(pay\s+from|from|using|via|with|paid\s+with)\s+.+$",
        "",
        title,
        flags=re.IGNORECASE,
    )

    # Clean extra commas/spaces.
    title = title.strip(" ,.-")

    return title


def extract_destination_account_from_text(user, text):
    lowered = text.lower()

    patterns = [
        r"(?:to|in|into|deposit\s+to|received\s+in)\s+(.+)$",
    ]

    possible_account_text = ""

    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            possible_account_text = match.group(1).strip()
            break

    accounts = Account.objects.filter(
        user=user,
        is_active=True,
    )

    if possible_account_text:
        possible_account_text = re.sub(
            r"\d+(?:,\d{3})*(?:\.\d+)?",
            "",
            possible_account_text,
        ).strip()

        for account in accounts:
            haystack = f"{account.name} {account.institution_name}".lower()

            if possible_account_text in haystack:
                return account

            for word in possible_account_text.split():
                if len(word) >= 2 and word in haystack:
                    return account

    return None


def clean_search_text(text):
    text = text.lower()

    # Remove punctuation that commonly comes from chat messages.
    text = re.sub(r"[^\w\s]", " ", text)

    # Collapse multiple spaces.
    text = re.sub(r"\s+", " ", text)

    return text.strip()


import random


def lazy_reply(message):
    prefixes = [
        "Alright… ",
        "Okay, okay… ",
        "Fine, I checked… ",
        "Hmm… ",
        "Yup, found it… ",
    ]

    suffixes = [
        " 😴",
        " Lazy but done.",
        " Not bad.",
        " I’ll do the boring part.",
        " Easy enough.",
    ]

    return f"{random.choice(prefixes)}{message}{random.choice(suffixes)}"


def assistant_account_choices(user):
    accounts = Account.objects.filter(
        user=user,
        is_active=True,
    ).exclude(
        account_type__in=["credit_card", "loan"]
    ).order_by("account_type", "name")

    return [
        {
            "id": account.id,
            "name": account.name,
            "type": account.account_type,
            "balance": str(account.current_balance),
        }
        for account in accounts
    ]


def find_receivable_by_borrower(user, borrower_name):
    if not borrower_name:
        return None

    borrower_name = clean_search_text(borrower_name)

    receivables = MoneyLent.objects.filter(
        user=user,
    ).exclude(
        status="paid"
    )

    # Exact-ish match first
    for item in receivables:
        if borrower_name == clean_search_text(item.borrower_name):
            return item

    # Partial match fallback
    for item in receivables:
        cleaned_name = clean_search_text(item.borrower_name)

        if borrower_name in cleaned_name or cleaned_name in borrower_name:
            return item

    # Word fallback
    for item in receivables:
        cleaned_name = clean_search_text(item.borrower_name)

        for word in borrower_name.split():
            if len(word) >= 2 and word in cleaned_name:
                return item

    return None


def extract_borrower_for_lent(text, amount):
    cleaned = remove_amount_from_text(text, amount)
    cleaned = clean_search_text(cleaned)

    remove_words = [
        "borrowed",
        "borrow",
        "lent",
        "lend",
        "loaned",
        "loan",
        "to",
        "from",
        "me",
        "i",
        "gave",
        "cash",
        "money",
    ]

    words = [
        word for word in cleaned.split()
        if word not in remove_words
    ]

    # Remove account names if message contains "from BPI"
    if " from " in f" {text.lower()} ":
        before_from = text.lower().split(" from ")[0]
        cleaned = remove_amount_from_text(before_from, amount)
        cleaned = clean_search_text(cleaned)

        words = [
            word for word in cleaned.split()
            if word not in remove_words
        ]

    return " ".join(words).strip().title()


def extract_borrower_for_payment(text, amount):
    cleaned = remove_amount_from_text(text, amount)
    cleaned = clean_search_text(cleaned)

    remove_words = [
        "paid",
        "pay",
        "payment",
        "returned",
        "return",
        "gave",
        "back",
        "me",
        "to",
        "into",
        "in",
        "received",
        "from",
    ]

    # For "John paid me 500 to BPI", keep before " to "
    lowered = text.lower()

    for separator in [" to ", " into ", " in "]:
        if separator in lowered:
            lowered = lowered.split(separator)[0]
            break

    cleaned = remove_amount_from_text(lowered, amount)
    cleaned = clean_search_text(cleaned)

    words = [
        word for word in cleaned.split()
        if word not in remove_words
    ]

    return " ".join(words).strip().title()


def is_money_lent_intent(text):
    lent_keywords = [
        "borrowed",
        "borrow",
        "lent",
        "lend",
        "loaned",
        "loan",
    ]

    repayment_keywords = [
        "paid me",
        "paid back",
        "returned",
        "gave back",
    ]

    if any(keyword in text for keyword in repayment_keywords):
        return False

    return any(keyword in text for keyword in lent_keywords)


def is_money_lent_payment_intent(text):
    payment_keywords = [
        "paid me",
        "paid back",
        "returned",
        "gave back",
        "pay me back",
    ]

    return any(keyword in text for keyword in payment_keywords)


def is_show_receivables_intent(text):
    keywords = [
        "show receivables",
        "show people who owe me",
        "who owes me",
        "who still owes me",
        "people who owe me",
        "borrowed money",
        "money lent",
    ]

    return any(keyword in text for keyword in keywords)


def serialize_preview(preview):
    data = {}

    for key, value in preview.items():
        if isinstance(value, Decimal):
            data[key] = str(value)
        elif hasattr(value, "id"):
            data[key] = {
                "id": value.id,
                "name": getattr(value, "name", str(value)),
            }
        else:
            data[key] = value

    return data


@login_required
@require_POST
def finance_assistant_receipt_view(request):
    uploaded_file = request.FILES.get("receipt")

    if not uploaded_file:
        return JsonResponse({
            "ok": False,
            "reply": lazy_reply("I did not receive an image. Upload it again, slowly this time."),
        })

    max_size = 8 * 1024 * 1024

    if uploaded_file.size > max_size:
        return JsonResponse({
            "ok": False,
            "reply": lazy_reply("That image is too large. Keep it under 8MB, please. I am lazy."),
        })

    try:
        receipt_data = analyze_receipt_image_with_openai(uploaded_file)
    except Exception as error:
        return JsonResponse({
            "ok": False,
            "reply": lazy_reply(str(error)),
        })

    merchant = receipt_data["merchant"]
    amount = receipt_data["amount"]
    category_hint = receipt_data.get("category_hint") or ""
    transaction_date = receipt_data.get("transaction_date") or ""
    notes = receipt_data.get("notes") or ""

    category_search_text = f"{merchant} {category_hint} {notes}"
    category = find_expense_category(request.user, category_search_text)

    if not category:
        return JsonResponse({
            "ok": False,
            "reply": lazy_reply("I read the receipt, but you need to create an expense category first."),
        })

    choices = assistant_account_choices(request.user)

    if not choices:
        return JsonResponse({
            "ok": False,
            "reply": lazy_reply("Please create an account first."),
        })

    receipt_note_parts = ["Added from receipt upload via finance assistant"]

    if transaction_date:
        receipt_note_parts.append(f"Receipt date: {transaction_date}")

    if notes:
        receipt_note_parts.append(notes)

    request.session["finance_assistant_preview"] = {
        "intent": "expense",
        "title": merchant,
        "amount": str(amount),
        "category_id": category.id,
        "category_name": category.name,
        "needs_account": True,
        "notes": " | ".join(receipt_note_parts),
    }

    return JsonResponse({
        "ok": True,
        "needs_choice": True,
        "choice_type": "account",
        "choices": choices,
        "reply": lazy_reply(
            f"I read the receipt as `{merchant}` for ₱{amount:,.2f} under {category.name}. "
            f"Which account should I use?"
        ),
    })


@login_required
@require_POST
def finance_assistant_view(request):
    message = request.POST.get("message", "").strip()

    if not message:
        return JsonResponse({
            "ok": False,
            "reply": "Please type something like `jollibee 500` or `pay meralco bill`.",
        })

    text = message.lower()
    amount = extract_amount(text)

    # Show receivables intent
    if is_show_receivables_intent(text) and not amount:
        records = (
            MoneyLent.objects
            .filter(user=request.user)
            .exclude(status="paid")
            .order_by("expected_payment_date", "-lent_date", "-created_at")
        )

        if not records.exists():
            return JsonResponse({
                "ok": True,
                "reply": lazy_reply("Nobody owes you money right now. Suspiciously peaceful."),
            })

        lines = []
        total_remaining = Decimal("0.00")

        for item in records:
            remaining = item.current_balance
            total_remaining += remaining

            due_text = f" due on {item.expected_payment_date}" if item.expected_payment_date else ""
            lines.append(
                f"• {item.borrower_name}: ₱{remaining:,.2f}{due_text}"
            )

        reply = (
            "Here are the people who still owe you money:\n\n"
            + "\n".join(lines)
            + f"\n\nTotal receivable: ₱{total_remaining:,.2f}."
        )

        return JsonResponse({
            "ok": True,
            "reply": lazy_reply(reply),
        })

    # Pay bill intent
    if "pay" in text and "bill" in text:
        search_text = text.replace("pay", "").replace("bill", "")
        search_text = clean_search_text(search_text)

        bill_queryset = Bill.objects.filter(
            user=request.user,
            status__in=["unpaid", "partial", "overdue"],
        ).select_related("account", "category")

        bill = bill_queryset.filter(
            Q(name__icontains=search_text) |
            Q(category__name__icontains=search_text)
        ).order_by("due_date").first()

        # Fallback: match any word, useful for messages like "pay my meralco electric bill"
        if not bill and search_text:
            words = [word for word in search_text.split() if len(word) >= 3]

            query = Q()
            for word in words:
                query |= Q(name__icontains=word)
                query |= Q(category__name__icontains=word)

            bill = bill_queryset.filter(query).order_by("due_date").first()

        if not bill.account_id:
            choices = assistant_account_choices(request.user)

            if not choices:
                return JsonResponse({
                    "ok": False,
                    "reply": "Please create an account first.",
                })

            amount_to_pay = bill.amount_due - bill.amount_paid

            request.session["finance_assistant_preview"] = {
                "intent": "pay_bill",
                "bill_id": bill.id,
                "bill_name": bill.name,
                "amount": str(amount_to_pay),
                "needs_account": True,
            }

            return JsonResponse({
                "ok": True,
                "needs_choice": True,
                "choice_type": "account",
                "choices": choices,
                "reply": f"I found `{bill.name}` for ₱{amount_to_pay:,.2f}. Which account should pay it?",
            })

        if not bill.category_id:
            return JsonResponse({
                "ok": False,
                "reply": f"I found `{bill.name}`, but it has no category assigned. Please edit the bill first.",
            })

        amount_to_pay = bill.amount_due - bill.amount_paid

        preview = {
            "intent": "pay_bill",
            "bill_id": bill.id,
            "bill_name": bill.name,
            "account_name": bill.account.name,
            "category_name": bill.category.name,
            "amount": amount_to_pay,
            "reply": (
                f"I found unpaid bill `{bill.name}` for ₱{amount_to_pay:,.2f}. "
                f"Pay from {bill.account.name}?"
            ),
        }

        request.session["finance_assistant_preview"] = serialize_preview(preview)

        return JsonResponse({
            "ok": True,
            "needs_confirmation": True,
            "preview": serialize_preview(preview),
            "reply": lazy_reply(preview["reply"]),
        })

    # Money lent intent
    # Examples:
    # "John borrowed 1000 from BPI"
    # "lend 500 to Mark from Cash Wallet"
    # "I lent Anna 300"
    if amount and is_money_lent_intent(text):
        borrower_name = extract_borrower_for_lent(message, amount)
        account = extract_account_from_text(request.user, message)

        if not borrower_name:
            return JsonResponse({
                "ok": False,
                "reply": lazy_reply("Who borrowed the money? My lazy brain needs a name first."),
            })

        if not account:
            choices = assistant_account_choices(request.user)

            if not choices:
                return JsonResponse({
                    "ok": False,
                    "reply": lazy_reply("Please create an account first."),
                })

            request.session["finance_assistant_preview"] = {
                "intent": "money_lent",
                "borrower_name": borrower_name,
                "amount": str(amount),
                "description": "Added via finance assistant",
                "needs_account": True,
            }

            return JsonResponse({
                "ok": True,
                "needs_choice": True,
                "choice_type": "account",
                "choices": choices,
                "reply": lazy_reply(
                    f"`{borrower_name}` borrowed ₱{amount:,.2f}. "
                    f"Which account did the money come from?"
                ),
            })

        preview = {
            "intent": "money_lent",
            "borrower_name": borrower_name,
            "amount": amount,
            "account_id": account.id,
            "account_name": account.name,
            "description": "Added via finance assistant",
            "reply": (
                f"Add receivable: `{borrower_name}` borrowed "
                f"₱{amount:,.2f} from {account.name}?"
            ),
        }

        request.session["finance_assistant_preview"] = serialize_preview(preview)

        return JsonResponse({
            "ok": True,
            "needs_confirmation": True,
            "preview": serialize_preview(preview),
            "reply": lazy_reply(preview["reply"]),
        })

    if " to " in text and amount:
        from_account, to_account = parse_transfer_command(
            request.user,
            message,
            amount,
        )

        if from_account and to_account:
            preview = {
                "intent": "transfer",
                "from_account_id": from_account.id,
                "from_account_name": from_account.name,
                "to_account_id": to_account.id,
                "to_account_name": to_account.name,
                "amount": amount,
                "reply": (
                    f"Transfer ₱{amount:,.2f} from {from_account.name} "
                    f"to {to_account.name}?"
                ),
            }

            request.session["finance_assistant_preview"] = serialize_preview(preview)

            return JsonResponse({
                "ok": True,
                "needs_confirmation": True,
                "preview": serialize_preview(preview),
                "reply": lazy_reply(preview["reply"]),
            })

        if "transfer" in text or "send" in text or "move" in text or " from " in text:
            return JsonResponse({
                "ok": False,
                "reply": "I couldn't clearly find the source or destination account.",
            })

        preview = {
            "intent": "transfer",
            "from_account_id": from_account.id,
            "from_account_name": from_account.name,
            "to_account_id": to_account.id,
            "to_account_name": to_account.name,
            "amount": amount,
            "reply": (
                f"Transfer ₱{amount:,.2f} from {from_account.name} "
                f"to {to_account.name}?"
            ),
        }

        request.session["finance_assistant_preview"] = serialize_preview(preview)

        return JsonResponse({
            "ok": True,
            "needs_confirmation": True,
            "preview": serialize_preview(preview),
            "reply": lazy_reply(preview["reply"]),
        })


    # Money lent payment intent
    # Examples:
    # "John paid me 500"
    # "Anna paid back 300 to Cash Wallet"
    # "Mark returned 1000 to BPI"
    if amount and is_money_lent_payment_intent(text):
        borrower_name = extract_borrower_for_payment(message, amount)
        receivable = find_receivable_by_borrower(request.user, borrower_name)

        if not borrower_name:
            return JsonResponse({
                "ok": False,
                "reply": lazy_reply("Who paid you back? I am lazy, not psychic."),
            })

        if not receivable:
            return JsonResponse({
                "ok": False,
                "reply": lazy_reply(f"I couldn't find an unpaid receivable for `{borrower_name}`."),
            })

        if amount > receivable.current_balance:
            return JsonResponse({
                "ok": False,
                "reply": lazy_reply(
                    f"`{receivable.borrower_name}` only owes ₱{receivable.current_balance:,.2f}. "
                    f"Payment of ₱{amount:,.2f} is too much."
                ),
            })

        account = extract_destination_account_from_text(request.user, message)

        if not account:
            choices = assistant_account_choices(request.user)

            if not choices:
                return JsonResponse({
                    "ok": False,
                    "reply": lazy_reply("Please create an account first."),
                })

            request.session["finance_assistant_preview"] = {
                "intent": "money_lent_payment",
                "money_lent_id": receivable.id,
                "borrower_name": receivable.borrower_name,
                "amount": str(amount),
                "needs_account": True,
            }

            return JsonResponse({
                "ok": True,
                "needs_choice": True,
                "choice_type": "account",
                "choices": choices,
                "reply": lazy_reply(
                    f"`{receivable.borrower_name}` paid ₱{amount:,.2f}. "
                    f"Which account received the money?"
                ),
            })

        preview = {
            "intent": "money_lent_payment",
            "money_lent_id": receivable.id,
            "borrower_name": receivable.borrower_name,
            "amount": amount,
            "account_id": account.id,
            "account_name": account.name,
            "reply": (
                f"Record payment from `{receivable.borrower_name}` for "
                f"₱{amount:,.2f} into {account.name}?"
            ),
        }

        request.session["finance_assistant_preview"] = serialize_preview(preview)

        return JsonResponse({
            "ok": True,
            "needs_confirmation": True,
            "preview": serialize_preview(preview),
            "reply": lazy_reply(preview["reply"]),
        })

    # Income intent
    income_keywords = ["salary", "income", "received", "bonus", "allowance"]
    if amount and any(keyword in text for keyword in income_keywords):
        title = remove_amount_from_text(message, amount)
        account = extract_destination_account_from_text(request.user, message)
        if not account:
            account = extract_account_from_text(request.user, message)
        if not account:
            account = find_best_account(request.user, text)
        category = find_income_category(request.user, text)

        if not account:
            return JsonResponse({
                "ok": False,
                "reply": "Please create an account first.",
            })

        if not category:
            return JsonResponse({
                "ok": False,
                "reply": "Please create an income category first.",
            })

        preview = {
            "intent": "income",
            "title": title or "Income",
            "amount": amount,
            "account_id": account.id,
            "account_name": account.name,
            "category_id": category.id,
            "category_name": category.name,
            "reply": (
                f"Add income `{title or 'Income'}` for ₱{amount:,.2f} "
                f"to {account.name}?"
            ),
        }

        request.session["finance_assistant_preview"] = serialize_preview(preview)

        return JsonResponse({
            "ok": True,
            "needs_confirmation": True,
            "preview": serialize_preview(preview),
            "reply": lazy_reply(preview["reply"]),
        })

    # Default expense intent:
    # Examples:
    # "jollibee 500"
    # "jollibee 500, pay from BPI"
    # "jollibee 500 using GCash"
    if amount:
        title = clean_expense_title(message, amount)

        account = extract_account_from_text(request.user, message)

        category = find_expense_category(request.user, text)

        if not account:
            choices = assistant_account_choices(request.user)

            if not choices:
                return JsonResponse({
                    "ok": False,
                    "reply": "Please create an account first.",
                })

            pending = {
                "intent": "expense",
                "title": title or "Expense",
                "amount": str(amount),
                "category_id": category.id if category else None,
                "category_name": category.name if category else None,
                "needs_account": True,
            }

            request.session["finance_assistant_preview"] = pending

            return JsonResponse({
                "ok": True,
                "needs_choice": True,
                "choice_type": "account",
                "choices": choices,
                "reply": lazy_reply(
                    f"Which account should I use for `{title or 'Expense'}` ₱{amount:,.2f}?"
                ),
            })

        if not category:
            return JsonResponse({
                "ok": False,
                "reply": "Please create an expense category first.",
            })

        preview = {
            "intent": "expense",
            "title": title or "Expense",
            "amount": amount,
            "account_id": account.id,
            "account_name": account.name,
            "category_id": category.id,
            "category_name": category.name,
            "reply": (
                f"Add expense `{title or 'Expense'}` for ₱{amount:,.2f} "
                f"from {account.name} under {category.name}?"
            ),
        }

        request.session["finance_assistant_preview"] = serialize_preview(preview)

        return JsonResponse({
            "ok": True,
            "needs_confirmation": True,
            "preview": serialize_preview(preview),
            "reply": lazy_reply(preview["reply"]),
        })

    return JsonResponse({
        "ok": False,
        "reply": (
            "I didn't understand that yet. Try `jollibee 500`, "
            "`salary 10000`, `pay meralco bill`, "
            "`John borrowed 1000`, or `John paid me 500`."
        ),
    })


@login_required
@require_POST
@db_transaction.atomic
def finance_assistant_confirm_view(request):
    preview = request.session.get("finance_assistant_preview")

    if not preview:
        return JsonResponse({
            "ok": False,
            "reply": "There is no pending action to confirm.",
        })

    intent = preview.get("intent")

    try:
        if intent == "expense":
            account = Account.objects.get(
                id=preview["account_id"],
                user=request.user,
            )
            category = Category.objects.get(
                id=preview["category_id"],
                user=request.user,
            )

            transaction_obj = Transaction.objects.create(
                user=request.user,
                account=account,
                category=category,
                transaction_type="expense",
                title=preview["title"],
                amount=Decimal(preview["amount"]),
                transaction_date=timezone.localdate(),
                notes=preview.get("notes") or "Added via finance assistant",
            )

            apply_transaction_balance_effect(transaction_obj)

            reply = lazy_reply(
                f"Done. Added expense `{transaction_obj.title}` for ₱{transaction_obj.amount:,.2f}."
            )

        elif intent == "income":
            account = Account.objects.get(
                id=preview["account_id"],
                user=request.user,
            )
            category = Category.objects.get(
                id=preview["category_id"],
                user=request.user,
            )

            transaction_obj = Transaction.objects.create(
                user=request.user,
                account=account,
                category=category,
                transaction_type="income",
                title=preview["title"],
                amount=Decimal(preview["amount"]),
                transaction_date=timezone.localdate(),
                notes="Added via finance assistant",
            )

            apply_transaction_balance_effect(transaction_obj)

            reply = lazy_reply(
                f"Done. Added income `{transaction_obj.title}` for ₱{transaction_obj.amount:,.2f}."
            )

        elif intent == "pay_bill":
            bill = Bill.objects.select_related("account", "category").get(
                id=preview["bill_id"],
                user=request.user,
            )

            if bill.status == "paid":
                return JsonResponse({
                    "ok": False,
                    "reply": "This bill is already paid.",
                })

            amount_to_pay = bill.amount_due - bill.amount_paid

            payment_account = bill.account

            if preview.get("account_id"):
                payment_account = Account.objects.get(
                    id=preview["account_id"],
                    user=request.user,
                    is_active=True,
                )

            payment_transaction = Transaction.objects.create(
                user=request.user,
                account=payment_account,
                category=bill.category,
                transaction_type="expense",
                title=bill.name,
                amount=amount_to_pay,
                transaction_date=timezone.localdate(),
                notes=f"Payment for bill #{bill.id}: {bill.name}",
            )

            apply_transaction_balance_effect(payment_transaction)

            bill.amount_paid = bill.amount_due
            bill.status = "paid"
            bill.paid_date = timezone.localdate()
            bill.payment_transaction = payment_transaction
            bill.save(update_fields=[
                "amount_paid",
                "status",
                "paid_date",
                "payment_transaction",
            ])

            reply = lazy_reply(
                f"Done. Paid bill `{bill.name}` for ₱{amount_to_pay:,.2f}."
            )

        elif intent == "transfer":
            from_account = Account.objects.get(
                id=preview["from_account_id"],
                user=request.user,
            )
            to_account = Account.objects.get(
                id=preview["to_account_id"],
                user=request.user,
            )

            transfer_obj = Transfer.objects.create(
                user=request.user,
                from_account=from_account,
                to_account=to_account,
                amount=Decimal(preview["amount"]),
                transfer_date=timezone.localdate(),
                notes="Added via finance assistant",
            )

            apply_transfer_balance_effect(transfer_obj)

            reply = (
                f"Done. Transferred ₱{transfer_obj.amount:,.2f} "
                f"from {from_account.name} to {to_account.name}."
            )

        elif intent == "money_lent":
            account = Account.objects.get(
                id=preview["account_id"],
                user=request.user,
                is_active=True,
            )

            money_lent = create_money_lent(
                user=request.user,
                borrower_name=preview["borrower_name"],
                amount=Decimal(preview["amount"]),
                account=account,
                description=preview.get("description") or "Added via finance assistant",
            )

            reply = lazy_reply(
                f"Done. `{money_lent.borrower_name}` now owes you "
                f"₱{money_lent.current_balance:,.2f}. I deducted it from {account.name}."
            )

        elif intent == "money_lent_payment":
            receivable = MoneyLent.objects.get(
                id=preview["money_lent_id"],
                user=request.user,
            )

            account = Account.objects.get(
                id=preview["account_id"],
                user=request.user,
                is_active=True,
            )

            payment = add_money_lent_payment(
                money_lent=receivable,
                amount=Decimal(preview["amount"]),
                account=account,
                notes="Added via finance assistant",
            )

            receivable.refresh_from_db()

            reply = lazy_reply(
                f"Payment recorded. `{receivable.borrower_name}` paid "
                f"₱{payment.amount:,.2f}. Remaining balance: "
                f"₱{receivable.current_balance:,.2f}."
            )

        else:
            return JsonResponse({
                "ok": False,
                "reply": "Unknown pending action.",
            })

    except Exception as error:
        return JsonResponse({
            "ok": False,
            "reply": str(error),
        })

    request.session.pop("finance_assistant_preview", None)

    return JsonResponse({
        "ok": True,
        "reply": reply,
    })


@login_required
@require_POST
def finance_assistant_choose_view(request):
    preview = request.session.get("finance_assistant_preview")

    if not preview:
        return JsonResponse({
            "ok": False,
            "reply": "There is no pending action.",
        })

    choice_type = request.POST.get("choice_type")
    choice_id = request.POST.get("choice_id")

    if choice_type != "account":
        return JsonResponse({
            "ok": False,
            "reply": "Unsupported choice.",
        })

    account = get_object_or_404(
        Account,
        id=choice_id,
        user=request.user,
        is_active=True,
    )

    intent = preview.get("intent")

    if intent == "expense":
        category = None

        if preview.get("category_id"):
            category = Category.objects.filter(
                id=preview["category_id"],
                user=request.user,
            ).first()

        if not category:
            return JsonResponse({
                "ok": False,
                "reply": "Please create an expense category first.",
            })

        preview["account_id"] = account.id
        preview["account_name"] = account.name
        preview["needs_account"] = False
        preview["reply"] = (
            f"Add expense `{preview['title']}` for ₱{Decimal(preview['amount']):,.2f} "
            f"from {account.name} under {category.name}?"
        )

    elif intent == "pay_bill":
        bill = get_object_or_404(
            Bill.objects.select_related("category"),
            id=preview["bill_id"],
            user=request.user,
        )

        if not bill.category_id:
            return JsonResponse({
                "ok": False,
                "reply": f"I found `{bill.name}`, but it has no category assigned. Please edit the bill first.",
            })

        preview["account_id"] = account.id
        preview["account_name"] = account.name
        preview["category_id"] = bill.category_id
        preview["category_name"] = bill.category.name
        preview["needs_account"] = False
        preview["reply"] = (
            f"Pay bill `{bill.name}` for ₱{Decimal(preview['amount']):,.2f} "
            f"from {account.name}?"
        )

    elif intent == "money_lent":
        preview["account_id"] = account.id
        preview["account_name"] = account.name
        preview["needs_account"] = False
        preview["reply"] = (
            f"Add receivable: `{preview['borrower_name']}` borrowed "
            f"₱{Decimal(preview['amount']):,.2f} from {account.name}?"
        )

    elif intent == "money_lent_payment":
        preview["account_id"] = account.id
        preview["account_name"] = account.name
        preview["needs_account"] = False
        preview["reply"] = (
            f"Record payment from `{preview['borrower_name']}` for "
            f"₱{Decimal(preview['amount']):,.2f} into {account.name}?"
        )

    else:
        return JsonResponse({
            "ok": False,
            "reply": "This pending action does not support account choices.",
        })

    request.session["finance_assistant_preview"] = preview

    return JsonResponse({
        "ok": True,
        "needs_confirmation": True,
        "reply": lazy_reply(preview["reply"]),
    })