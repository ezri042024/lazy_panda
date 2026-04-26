from django.db.models import Sum
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import viewsets, permissions, status, serializers
from datetime import timedelta

from .models import (
    Account,
    Category,
    Merchant,
    Transaction,
    Transfer,
    Budget,
    Bill,
    Debt,
    DebtPayment,
    SavingsGoal,
    GoalContribution,
    Receipt, RecurringBill,
)
from .serializers import (
    AccountSerializer,
    CategorySerializer,
    MerchantSerializer,
    TransactionSerializer,
    TransferSerializer,
    BudgetSerializer,
    BillSerializer,
    DebtSerializer,
    DebtPaymentSerializer,
    SavingsGoalSerializer,
    GoalContributionSerializer,
    ReceiptSerializer, RecurringBillSerializer,
)
from .services import decrease_account_balance, increase_account_balance, increase_debt_balance, decrease_debt_balance, \
    decrease_goal_amount, increase_goal_amount, generate_recurring_bills_for_user


class DRFValidationError:
    pass


def raise_drf_validation_error(error):
    if hasattr(error, "message_dict"):
        raise serializers.ValidationError(error.message_dict)

    if hasattr(error, "messages"):
        raise serializers.ValidationError({
            "detail": error.messages
        })

    raise serializers.ValidationError({
        "detail": str(error)
    })


class UserOwnedViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class AccountViewSet(UserOwnedViewSet):
    serializer_class = AccountSerializer

    def get_queryset(self):
        return Account.objects.filter(user=self.request.user)


class CategoryViewSet(UserOwnedViewSet):
    serializer_class = CategorySerializer

    def get_queryset(self):
        queryset = Category.objects.filter(user=self.request.user)

        category_type = self.request.query_params.get("type")
        if category_type:
            queryset = queryset.filter(category_type=category_type)

        return queryset


class MerchantViewSet(UserOwnedViewSet):
    serializer_class = MerchantSerializer

    def get_queryset(self):
        return Merchant.objects.filter(user=self.request.user)


class TransactionViewSet(UserOwnedViewSet):
    serializer_class = TransactionSerializer

    def get_queryset(self):
        queryset = Transaction.objects.filter(user=self.request.user)

        transaction_type = self.request.query_params.get("type")
        account_id = self.request.query_params.get("account")
        category_id = self.request.query_params.get("category")
        month = self.request.query_params.get("month")
        year = self.request.query_params.get("year")

        if transaction_type:
            queryset = queryset.filter(transaction_type=transaction_type)

        if account_id:
            queryset = queryset.filter(account_id=account_id)

        if category_id:
            queryset = queryset.filter(category_id=category_id)

        if month:
            queryset = queryset.filter(transaction_date__month=month)

        if year:
            queryset = queryset.filter(transaction_date__year=year)

        return queryset.order_by("-transaction_date", "-id")

    def get_balance_effect(self, transaction_type, amount):
        """
        Returns how much the transaction should affect the account balance.

        income      = add to balance
        expense     = subtract from balance
        adjustment  = add to balance for now
        """
        if transaction_type == "income":
            return amount

        if transaction_type == "expense":
            return -amount

        if transaction_type == "adjustment":
            return amount

        return 0

    def apply_balance_effect(self, account, transaction_type, amount):
        try:
            if transaction_type == "income":
                increase_account_balance(account.id, amount)
            elif transaction_type == "expense":
                if account.account_type in ["credit_card", "loan"]:
                    increase_account_balance(account.id, amount)
                else:
                    decrease_account_balance(account.id, amount)
            elif transaction_type == "adjustment":
                increase_account_balance(account.id, amount)
        except DjangoValidationError as error:
            raise_drf_validation_error(error)

    def reverse_balance_effect(self, account, transaction_type, amount):
        try:
            if transaction_type == "income":
                decrease_account_balance(account.id, amount)
            elif transaction_type == "expense":
                if account.account_type in ["credit_card", "loan"]:
                    decrease_account_balance(account.id, amount)
                else:
                    increase_account_balance(account.id, amount)
            elif transaction_type == "adjustment":
                decrease_account_balance(account.id, amount)
        except DjangoValidationError as error:
            raise_drf_validation_error(error)

    def ensure_not_bill_payment_transaction(self, transaction_obj):
        if transaction_obj.paid_bills.exists():
            raise serializers.ValidationError({
                "detail": (
                    "This transaction was created from a paid bill. "
                    "Use Unmark Paid on the bill to reverse it."
                )
            })

    @transaction.atomic
    def perform_create(self, serializer):
        transaction_obj = serializer.save(user=self.request.user)

        self.apply_balance_effect(
            account=transaction_obj.account,
            transaction_type=transaction_obj.transaction_type,
            amount=transaction_obj.amount,
        )

    @transaction.atomic
    def perform_update(self, serializer):
        old_transaction = self.get_object()
        self.ensure_not_bill_payment_transaction(old_transaction)

        old_account = old_transaction.account
        old_transaction_type = old_transaction.transaction_type
        old_amount = old_transaction.amount

        # Reverse the old transaction effect first
        self.reverse_balance_effect(
            account=old_account,
            transaction_type=old_transaction_type,
            amount=old_amount,
        )

        try:
            # Save the updated transaction
            updated_transaction = serializer.save()

            # Apply the new transaction effect
            self.apply_balance_effect(
                account=updated_transaction.account,
                transaction_type=updated_transaction.transaction_type,
                amount=updated_transaction.amount,
            )

        except Exception:
            # If new transaction cannot be applied, restore old effect.
            self.apply_balance_effect(
                account=old_account,
                transaction_type=old_transaction_type,
                amount=old_amount,
            )
            raise

    @transaction.atomic
    def perform_destroy(self, instance):
        self.ensure_not_bill_payment_transaction(instance)

        self.reverse_balance_effect(
            account=instance.account,
            transaction_type=instance.transaction_type,
            amount=instance.amount,
        )

        instance.delete()


class TransferViewSet(UserOwnedViewSet):
    serializer_class = TransferSerializer

    def get_queryset(self):
        queryset = Transfer.objects.filter(user=self.request.user)

        from_account_id = self.request.query_params.get("from_account")
        to_account_id = self.request.query_params.get("to_account")
        month = self.request.query_params.get("month")
        year = self.request.query_params.get("year")

        if from_account_id:
            queryset = queryset.filter(from_account_id=from_account_id)

        if to_account_id:
            queryset = queryset.filter(to_account_id=to_account_id)

        if month:
            queryset = queryset.filter(transfer_date__month=month)

        if year:
            queryset = queryset.filter(transfer_date__year=year)

        return queryset

    def apply_transfer_effect(self, transfer_obj):
        try:
            decrease_account_balance(
                transfer_obj.from_account_id,
                transfer_obj.amount,
            )

            if transfer_obj.to_account.account_type in ["credit_card", "loan"]:
                decrease_account_balance(
                    transfer_obj.to_account_id,
                    transfer_obj.amount,
                )
            else:
                increase_account_balance(
                    transfer_obj.to_account_id,
                    transfer_obj.amount,
                )

        except DjangoValidationError as error:
            raise_drf_validation_error(error)

    def reverse_transfer_effect(self, transfer_obj):
        try:
            increase_account_balance(
                transfer_obj.from_account_id,
                transfer_obj.amount,
            )

            if transfer_obj.to_account.account_type in ["credit_card", "loan"]:
                increase_account_balance(
                    transfer_obj.to_account_id,
                    transfer_obj.amount,
                )
            else:
                decrease_account_balance(
                    transfer_obj.to_account_id,
                    transfer_obj.amount,
                )

        except DjangoValidationError as error:
            raise_drf_validation_error(error)

    @transaction.atomic
    def perform_create(self, serializer):
        transfer_obj = serializer.save(user=self.request.user)
        self.apply_transfer_effect(transfer_obj)

    @transaction.atomic
    def perform_update(self, serializer):
        old_transfer = self.get_object()

        old_from_account_id = old_transfer.from_account_id
        old_to_account_id = old_transfer.to_account_id
        old_amount = old_transfer.amount

        class OldTransferSnapshot:
            pass

        snapshot = OldTransferSnapshot()
        snapshot.from_account_id = old_from_account_id
        snapshot.to_account_id = old_to_account_id
        snapshot.amount = old_amount
        snapshot.to_account = old_transfer.to_account

        # Reverse old transfer first
        self.reverse_transfer_effect(snapshot)

        try:
            updated_transfer = serializer.save()
            self.apply_transfer_effect(updated_transfer)
        except Exception:
            # Restore old transfer if new transfer fails
            self.apply_transfer_effect(snapshot)
            raise

    @transaction.atomic
    def perform_destroy(self, instance):
        self.reverse_transfer_effect(instance)
        instance.delete()


class BudgetViewSet(UserOwnedViewSet):
    serializer_class = BudgetSerializer

    def get_queryset(self):
        queryset = Budget.objects.filter(user=self.request.user)

        month = self.request.query_params.get("month")
        year = self.request.query_params.get("year")

        if month:
            queryset = queryset.filter(month=month)

        if year:
            queryset = queryset.filter(year=year)

        return queryset


class BillViewSet(UserOwnedViewSet):
    serializer_class = BillSerializer

    def get_queryset(self):
        queryset = Bill.objects.filter(user=self.request.user)

        status_filter = self.request.query_params.get("status")
        month = self.request.query_params.get("month")
        year = self.request.query_params.get("year")

        if status_filter:
            queryset = queryset.filter(status=status_filter)

        if month:
            queryset = queryset.filter(due_date__month=month)

        if year:
            queryset = queryset.filter(due_date__year=year)

        return queryset

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def mark_paid(self, request, pk=None):
        bill = self.get_object()

        if bill.status == "paid":
            serializer = self.get_serializer(bill)
            return Response(serializer.data)

        if bill.payment_transaction_id:
            return Response(
                {"detail": "This bill already has a payment transaction."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not bill.account_id:
            return Response(
                {"detail": "Please assign an account before marking this bill as paid."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not bill.category_id:
            return Response(
                {"detail": "Please assign a category before marking this bill as paid."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        amount_to_pay = bill.amount_due - bill.amount_paid

        if amount_to_pay <= 0:
            return Response(
                {"detail": "This bill has no remaining amount to pay."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        paid_date = timezone.localdate()

        payment_transaction = Transaction.objects.create(
            user=request.user,
            account=bill.account,
            category=bill.category,
            transaction_type="expense",
            title=bill.name,
            amount=amount_to_pay,
            transaction_date=paid_date,
            notes=f"Payment for bill #{bill.id}: {bill.name}",
        )

        try:
            TransactionViewSet().apply_balance_effect(
                account=payment_transaction.account,
                transaction_type=payment_transaction.transaction_type,
                amount=payment_transaction.amount,
            )
        except DjangoValidationError as error:
            payment_transaction.delete()
            raise_drf_validation_error(error)

        bill.amount_paid = bill.amount_due
        bill.status = "paid"
        bill.paid_date = paid_date
        bill.payment_transaction = payment_transaction
        bill.save(
            update_fields=[
                "amount_paid",
                "status",
                "paid_date",
                "payment_transaction",
            ]
        )

        serializer = self.get_serializer(bill)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="unmark-paid")
    @transaction.atomic
    def unmark_paid(self, request, pk=None):
        bill = self.get_object()

        if bill.status != "paid":
            return Response(
                {"detail": "Only paid bills can be unmarked."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not bill.payment_transaction_id:
            return Response(
                {
                    "detail": (
                        "This bill has no linked payment transaction to reverse. "
                        "Please adjust it manually."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment_transaction = bill.payment_transaction

        previous_amount_paid = bill.amount_due - payment_transaction.amount

        if previous_amount_paid < 0:
            previous_amount_paid = 0

        try:
            TransactionViewSet().reverse_balance_effect(
                account=payment_transaction.account,
                transaction_type=payment_transaction.transaction_type,
                amount=payment_transaction.amount,
            )
        except DjangoValidationError as error:
            raise_drf_validation_error(error)

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

        serializer = self.get_serializer(bill)
        return Response(serializer.data)


class DebtViewSet(UserOwnedViewSet):
    serializer_class = DebtSerializer

    def get_queryset(self):
        return Debt.objects.filter(user=self.request.user)


class DebtPaymentViewSet(UserOwnedViewSet):
    serializer_class = DebtPaymentSerializer

    def get_queryset(self):
        queryset = DebtPayment.objects.filter(user=self.request.user)

        debt_id = self.request.query_params.get("debt")
        account_id = self.request.query_params.get("account")
        month = self.request.query_params.get("month")
        year = self.request.query_params.get("year")

        if debt_id:
            queryset = queryset.filter(debt_id=debt_id)

        if account_id:
            queryset = queryset.filter(account_id=account_id)

        if month:
            queryset = queryset.filter(payment_date__month=month)

        if year:
            queryset = queryset.filter(payment_date__year=year)

        return queryset

    @transaction.atomic
    def perform_create(self, serializer):
        payment = serializer.save(user=self.request.user)

        try:
            if payment.account_id:
                decrease_account_balance(payment.account_id, payment.amount)
        except DjangoValidationError as error:
            raise_drf_validation_error(error)

        decrease_debt_balance(payment.debt_id, payment.principal_amount)

    @transaction.atomic
    def perform_update(self, serializer):
        old_payment = self.get_object()

        old_account_id = old_payment.account_id
        old_debt_id = old_payment.debt_id
        old_amount = old_payment.amount
        old_principal = old_payment.principal_amount

        updated_payment = serializer.save()

        # Reverse old effect
        if old_account_id:
            increase_account_balance(old_account_id, old_amount)

        increase_debt_balance(old_debt_id, old_principal)

        # Apply new effect
        try:
            if updated_payment.account_id:
                decrease_account_balance(updated_payment.account_id, updated_payment.amount)
        except DjangoValidationError as error:
            raise_drf_validation_error(error)

        decrease_debt_balance(updated_payment.debt_id, updated_payment.principal_amount)

    @transaction.atomic
    def perform_destroy(self, instance):
        if instance.account_id:
            increase_account_balance(instance.account_id, instance.amount)

        increase_debt_balance(instance.debt_id, instance.principal_amount)

        instance.delete()


class SavingsGoalViewSet(UserOwnedViewSet):
    serializer_class = SavingsGoalSerializer

    def get_queryset(self):
        return SavingsGoal.objects.filter(user=self.request.user)


class GoalContributionViewSet(UserOwnedViewSet):
    serializer_class = GoalContributionSerializer

    def get_queryset(self):
        queryset = GoalContribution.objects.filter(user=self.request.user)

        goal_id = self.request.query_params.get("goal")
        account_id = self.request.query_params.get("account")
        month = self.request.query_params.get("month")
        year = self.request.query_params.get("year")

        if goal_id:
            queryset = queryset.filter(goal_id=goal_id)

        if account_id:
            queryset = queryset.filter(account_id=account_id)

        if month:
            queryset = queryset.filter(contribution_date__month=month)

        if year:
            queryset = queryset.filter(contribution_date__year=year)

        return queryset

    @transaction.atomic
    def perform_create(self, serializer):
        contribution = serializer.save(user=self.request.user)

        try:
            if contribution.account_id:
                decrease_account_balance(contribution.account_id, contribution.amount)
        except DjangoValidationError as error:
            raise_drf_validation_error(error)

        increase_goal_amount(contribution.goal_id, contribution.amount)

    @transaction.atomic
    def perform_update(self, serializer):
        old_contribution = self.get_object()

        old_account_id = old_contribution.account_id
        old_goal_id = old_contribution.goal_id
        old_amount = old_contribution.amount

        updated_contribution = serializer.save()

        # Reverse old effect
        if old_account_id:
            increase_account_balance(old_account_id, old_amount)

        decrease_goal_amount(old_goal_id, old_amount)

        # Apply new effect
        try:
            if updated_contribution.account_id:
                decrease_account_balance(updated_contribution.account_id, updated_contribution.amount)
        except DjangoValidationError as error:
            raise_drf_validation_error(error)

        increase_goal_amount(updated_contribution.goal_id, updated_contribution.amount)

    @transaction.atomic
    def perform_destroy(self, instance):
        if instance.account_id:
            increase_account_balance(instance.account_id, instance.amount)

        decrease_goal_amount(instance.goal_id, instance.amount)

        instance.delete()


class ReceiptViewSet(UserOwnedViewSet):
    serializer_class = ReceiptSerializer

    def get_queryset(self):
        return Receipt.objects.filter(user=self.request.user)


class FinanceDashboardViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        today = timezone.localdate()
        month = int(request.query_params.get("month", today.month))
        year = int(request.query_params.get("year", today.year))

        accounts = Account.objects.filter(
            user=request.user,
            is_active=True,
        )

        transactions = Transaction.objects.filter(
            user=request.user,
            transaction_date__month=month,
            transaction_date__year=year,
        )

        budgets = Budget.objects.filter(
            user=request.user,
            month=month,
            year=year,
        ).select_related("category")

        total_budget_limit = budgets.aggregate(
            total=Sum("amount_limit")
        )["total"] or 0

        budget_summary_items = []
        total_budget_spent = 0
        over_budget_count = 0

        for budget in budgets:
            spent = Transaction.objects.filter(
                user=request.user,
                category=budget.category,
                transaction_type="expense",
                transaction_date__month=month,
                transaction_date__year=year,
            ).aggregate(total=Sum("amount"))["total"] or 0

            remaining = budget.amount_limit - spent
            progress_percent = round((spent / budget.amount_limit) * 100, 2) if budget.amount_limit > 0 else 0
            is_over_budget = spent > budget.amount_limit

            if is_over_budget:
                over_budget_count += 1

            total_budget_spent += spent

            budget_summary_items.append({
                "id": budget.id,
                "category_id": budget.category_id,
                "category_name": budget.category.name,
                "amount_limit": budget.amount_limit,
                "spent_amount": spent,
                "remaining_amount": remaining,
                "progress_percent": progress_percent,
                "is_over_budget": is_over_budget,
            })

        total_budget_remaining = total_budget_limit - total_budget_spent
        budget_usage_percent = round((total_budget_spent / total_budget_limit) * 100,
                                     2) if total_budget_limit > 0 else 0

        bills = Bill.objects.filter(user=request.user)

        debts = Debt.objects.filter(
            user=request.user,
            is_active=True,
        )

        goals = SavingsGoal.objects.filter(
            user=request.user,
            is_completed=False,
        )

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

        total_income = transactions.filter(
            transaction_type="income"
        ).aggregate(total=Sum("amount"))["total"] or 0

        total_expense = transactions.filter(
            transaction_type="expense"
        ).aggregate(total=Sum("amount"))["total"] or 0

        net_cashflow = total_income - total_expense

        unpaid_bills_total = bills.filter(
            status__in=["unpaid", "partial", "overdue"],
        ).aggregate(total=Sum("amount_due"))["total"] or 0

        due_soon_bills = bills.filter(
            status__in=["unpaid", "partial"],
            due_date__gte=today,
            due_date__lte=today + timedelta(days=7),
        ).order_by("due_date")[:5]

        overdue_bills = bills.filter(
            status__in=["unpaid", "partial", "overdue"],
            due_date__lt=today,
        ).order_by("due_date")[:5]

        total_debt_balance = debts.aggregate(
            total=Sum("current_balance")
        )["total"] or 0

        total_goal_target = goals.aggregate(
            total=Sum("target_amount")
        )["total"] or 0

        total_goal_saved = goals.aggregate(
            total=Sum("current_amount")
        )["total"] or 0

        recent_transactions = transactions.order_by(
            "-transaction_date",
            "-created_at",
        )[:10]

        expense_by_category = (
            transactions
            .filter(transaction_type="expense", category__isnull=False)
            .values("category__id", "category__name")
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )

        income_by_category = (
            transactions
            .filter(transaction_type="income", category__isnull=False)
            .values("category__id", "category__name")
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )

        accounts_summary = accounts.values(
            "id",
            "name",
            "account_type",
            "institution_name",
            "current_balance",
            "currency",
        ).order_by("account_type", "name")

        goal_progress = []
        for goal in goals:
            if goal.target_amount > 0:
                progress = round((goal.current_amount / goal.target_amount) * 100, 2)
            else:
                progress = 0

            goal_progress.append({
                "id": goal.id,
                "name": goal.name,
                "target_amount": goal.target_amount,
                "current_amount": goal.current_amount,
                "progress_percent": progress,
                "target_date": goal.target_date,
            })

        return Response({
            "period": {
                "month": month,
                "year": year,
            },
            "summary": {
                "total_assets": total_assets,
                "total_liabilities": total_liabilities,
                "net_worth": total_assets - total_liabilities,
                "total_income": total_income,
                "total_expense": total_expense,
                "net_cashflow": net_cashflow,
                "unpaid_bills_total": unpaid_bills_total,
                "total_debt_balance": total_debt_balance,
                "total_goal_saved": total_goal_saved,
                "total_goal_target": total_goal_target,
                "total_budget_limit": total_budget_limit,
                "total_budget_spent": total_budget_spent,
                "total_budget_remaining": total_budget_remaining,
                "budget_usage_percent": budget_usage_percent,
                "over_budget_count": over_budget_count,
            },
            "accounts": list(accounts_summary),
            "expense_by_category": list(expense_by_category),
            "income_by_category": list(income_by_category),
            "recent_transactions": TransactionSerializer(
                recent_transactions,
                many=True,
                context={"request": request},
            ).data,
            "due_soon_bills": BillSerializer(
                due_soon_bills,
                many=True,
                context={"request": request},
            ).data,
            "overdue_bills": BillSerializer(
                overdue_bills,
                many=True,
                context={"request": request},
            ).data,
            "goal_progress": goal_progress,
        })


class FinanceSetupStatusViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        accounts = Account.objects.filter(user=request.user, is_active=True)
        categories = Category.objects.filter(user=request.user, is_active=True)

        has_accounts = accounts.exists()
        has_income_categories = categories.filter(category_type="income").exists()
        has_expense_categories = categories.filter(category_type="expense").exists()
        has_default_cash_account = accounts.filter(
            account_type="cash",
            name="Cash Wallet",
        ).exists()

        can_add_transaction = (
            has_accounts
            and has_income_categories
            and has_expense_categories
        )

        if not has_accounts:
            recommended_next_step = "create_account"
        elif not has_income_categories or not has_expense_categories:
            recommended_next_step = "create_categories"
        else:
            recommended_next_step = "ready"

        return Response({
            "has_accounts": has_accounts,
            "has_income_categories": has_income_categories,
            "has_expense_categories": has_expense_categories,
            "has_default_cash_account": has_default_cash_account,
            "can_add_transaction": can_add_transaction,
            "recommended_next_step": recommended_next_step,
        })


class RecurringBillViewSet(UserOwnedViewSet):
    serializer_class = RecurringBillSerializer

    def get_queryset(self):
        queryset = RecurringBill.objects.filter(user=self.request.user)

        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        return queryset

    @action(detail=False, methods=["post"])
    @transaction.atomic
    def generate(self, request):
        today = timezone.localdate()

        month = int(request.data.get("month", today.month))
        year = int(request.data.get("year", today.year))

        created_bills, skipped_count = generate_recurring_bills_for_user(
            user=request.user,
            year=year,
            month=month,
        )

        serializer = BillSerializer(
            created_bills,
            many=True,
            context={"request": request},
        )

        return Response({
            "created_count": len(created_bills),
            "skipped_count": skipped_count,
            "created_bills": serializer.data,
        })