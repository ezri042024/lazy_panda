from decimal import Decimal

from django.db.models import Sum
from rest_framework import serializers
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


class AccountSerializer(serializers.ModelSerializer):
    available_credit = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = [
            "id",
            "name",
            "account_type",
            "institution_name",
            "account_number_last4",
            "opening_balance",
            "current_balance",
            "credit_limit",
            "available_credit",
            "billing_day",
            "due_day",
            "currency",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "available_credit", "created_at"]

    def get_available_credit(self, obj):
        if obj.account_type != "credit_card":
            return None

        used_credit = abs(obj.current_balance) if obj.current_balance < 0 else 0
        return obj.credit_limit - used_credit


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "category_type",
            "icon",
            "color",
            "is_default",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "is_default", "created_at"]


class MerchantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Merchant
        fields = [
            "id",
            "name",
            "default_category",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class TransactionSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    merchant_name = serializers.CharField(source="merchant.name", read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id",
            "account",
            "account_name",
            "category",
            "category_name",
            "merchant",
            "merchant_name",
            "transaction_type",
            "title",
            "amount",
            "transaction_date",
            "notes",
            "reference_no",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user if request else None

        account = attrs.get("account")
        category = attrs.get("category")
        merchant = attrs.get("merchant")

        if account and account.user != user:
            raise serializers.ValidationError({
                "account": "Invalid account."
            })

        if category and category.user != user:
            raise serializers.ValidationError({
                "category": "Invalid category."
            })

        if merchant and merchant.user != user:
            raise serializers.ValidationError({
                "merchant": "Invalid merchant."
            })

        amount = attrs.get("amount")
        if amount is not None and amount <= 0:
            raise serializers.ValidationError({
                "amount": "Amount must be greater than zero."
            })

        return attrs


class TransferSerializer(serializers.ModelSerializer):
    from_account_name = serializers.CharField(source="from_account.name", read_only=True)
    to_account_name = serializers.CharField(source="to_account.name", read_only=True)

    class Meta:
        model = Transfer
        fields = [
            "id",
            "from_account",
            "from_account_name",
            "to_account",
            "to_account_name",
            "amount",
            "transfer_date",
            "notes",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user if request else None

        from_account = attrs.get("from_account")
        to_account = attrs.get("to_account")
        amount = attrs.get("amount")

        # For PATCH requests, use existing instance values if field is not included
        if self.instance:
            from_account = from_account or self.instance.from_account
            to_account = to_account or self.instance.to_account
            amount = amount or self.instance.amount

        if from_account and from_account.user != user:
            raise serializers.ValidationError({
                "from_account": "Invalid source account."
            })

        if to_account and to_account.user != user:
            raise serializers.ValidationError({
                "to_account": "Invalid destination account."
            })

        if from_account and to_account and from_account == to_account:
            raise serializers.ValidationError({
                "to_account": "Cannot transfer to the same account."
            })

        if amount is not None and amount <= 0:
            raise serializers.ValidationError({
                "amount": "Amount must be greater than zero."
            })

        return attrs


class BudgetSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    spent_amount = serializers.SerializerMethodField()
    remaining_amount = serializers.SerializerMethodField()
    progress_percent = serializers.SerializerMethodField()
    is_over_budget = serializers.SerializerMethodField()

    class Meta:
        model = Budget
        fields = [
            "id",
            "user",
            "category",
            "category_name",
            "amount_limit",
            "month",
            "year",
            "spent_amount",
            "remaining_amount",
            "progress_percent",
            "is_over_budget",
            "created_at",
        ]
        read_only_fields = [
            "user",
            "category_name",
            "spent_amount",
            "remaining_amount",
            "progress_percent",
            "is_over_budget",
            "created_at",
        ]

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user if request else None

        category = attrs.get("category")
        amount_limit = attrs.get("amount_limit")
        month = attrs.get("month")
        year = attrs.get("year")

        if self.instance:
            category = category or self.instance.category
            amount_limit = amount_limit if amount_limit is not None else self.instance.amount_limit
            month = month if month is not None else self.instance.month
            year = year if year is not None else self.instance.year

        if category and category.user != user:
            raise serializers.ValidationError({
                "category": "Invalid category."
            })

        if category and category.category_type != "expense":
            raise serializers.ValidationError({
                "category": "Budget category must be an expense category."
            })

        if amount_limit is not None and amount_limit <= 0:
            raise serializers.ValidationError({
                "amount_limit": "Budget amount must be greater than zero."
            })

        if month is not None and not 1 <= month <= 12:
            raise serializers.ValidationError({
                "month": "Month must be between 1 and 12."
            })

        if year is not None and year < 2000:
            raise serializers.ValidationError({
                "year": "Year must be valid."
            })

        duplicate_qs = Budget.objects.filter(
            user=user,
            category=category,
            month=month,
            year=year,
        )

        if self.instance:
            duplicate_qs = duplicate_qs.exclude(pk=self.instance.pk)

        if duplicate_qs.exists():
            raise serializers.ValidationError({
                "non_field_errors": "A budget already exists for this category, month, and year."
            })

        return attrs

    def get_spent_amount(self, obj):
        total = Transaction.objects.filter(
            user=obj.user,
            category=obj.category,
            transaction_type="expense",
            transaction_date__month=obj.month,
            transaction_date__year=obj.year,
        ).aggregate(total=Sum("amount"))["total"]

        return total or Decimal("0.00")

    def get_remaining_amount(self, obj):
        spent = self.get_spent_amount(obj)
        return obj.amount_limit - spent

    def get_progress_percent(self, obj):
        if obj.amount_limit <= 0:
            return 0

        spent = self.get_spent_amount(obj)
        progress = (spent / obj.amount_limit) * 100

        return round(progress, 2)

    def get_is_over_budget(self, obj):
        spent = self.get_spent_amount(obj)
        return spent > obj.amount_limit


class BillSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    payment_transaction_id = serializers.IntegerField(
        source="payment_transaction.id",
        read_only=True,
    )

    class Meta:
        model = Bill
        fields = [
            "id",
            "account",
            "account_name",
            "category",
            "category_name",
            "name",
            "amount_due",
            "amount_paid",
            "due_date",
            "paid_date",
            "status",
            "notes",
            "created_at",
            "payment_transaction",
            "payment_transaction_id",
        ]
        read_only_fields = [
            "user",
            "account_name",
            "category_name",
            "payment_transaction",
            "payment_transaction_id",
            "created_at",
        ]

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user if request else None

        account = attrs.get("account")
        category = attrs.get("category")
        amount_due = attrs.get("amount_due")
        amount_paid = attrs.get("amount_paid")
        status = attrs.get("status")
        paid_date = attrs.get("paid_date")

        if self.instance:
            account = account if account is not None else self.instance.account
            category = category if category is not None else self.instance.category
            amount_due = amount_due if amount_due is not None else self.instance.amount_due
            amount_paid = amount_paid if amount_paid is not None else self.instance.amount_paid
            status = status if status is not None else self.instance.status
            paid_date = paid_date if paid_date is not None else self.instance.paid_date

        if account and account.user != user:
            raise serializers.ValidationError({
                "account": "Invalid account."
            })

        if category and category.user != user:
            raise serializers.ValidationError({
                "category": "Invalid category."
            })

        if category and category.category_type not in ["expense", "debt"]:
            raise serializers.ValidationError({
                "category": "Bill category must be an expense or debt category."
            })

        if amount_due is not None and amount_due <= 0:
            raise serializers.ValidationError({
                "amount_due": "Amount due must be greater than zero."
            })

        if amount_paid is not None and amount_paid < 0:
            raise serializers.ValidationError({
                "amount_paid": "Amount paid cannot be negative."
            })

        if amount_due is not None and amount_paid is not None and amount_paid > amount_due:
            raise serializers.ValidationError({
                "amount_paid": "Amount paid cannot be greater than amount due."
            })

        if status == "paid":
            if amount_paid != amount_due:
                raise serializers.ValidationError({
                    "amount_paid": "Paid bills must have amount paid equal to amount due."
                })

        if status in ["paid", "partial"] and not paid_date:
            raise serializers.ValidationError({
                "paid_date": "Paid date is required for paid or partially paid bills."
            })

        if status == "unpaid" and amount_paid and amount_paid > 0:
            raise serializers.ValidationError({
                "status": "A bill with payment cannot have unpaid status."
            })

        return attrs


class DebtSerializer(serializers.ModelSerializer):
    class Meta:
        model = Debt
        fields = [
            "id",
            "name",
            "lender",
            "original_amount",
            "current_balance",
            "interest_rate",
            "minimum_payment",
            "due_day",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class DebtPaymentSerializer(serializers.ModelSerializer):
    debt_name = serializers.CharField(source="debt.name", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)

    class Meta:
        model = DebtPayment
        fields = [
            "id",
            "debt",
            "debt_name",
            "account",
            "account_name",
            "amount",
            "principal_amount",
            "interest_amount",
            "payment_date",
            "notes",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user if request else None

        debt = attrs.get("debt")
        account = attrs.get("account")
        amount = attrs.get("amount")
        principal_amount = attrs.get("principal_amount")
        interest_amount = attrs.get("interest_amount")

        if self.instance:
            debt = debt if debt is not None else self.instance.debt
            account = account if account is not None else self.instance.account
            amount = amount if amount is not None else self.instance.amount
            principal_amount = (
                principal_amount
                if principal_amount is not None
                else self.instance.principal_amount
            )
            interest_amount = (
                interest_amount
                if interest_amount is not None
                else self.instance.interest_amount
            )

        if debt and debt.user != user:
            raise serializers.ValidationError({
                "debt": "Invalid debt."
            })

        if account and account.user != user:
            raise serializers.ValidationError({
                "account": "Invalid account."
            })

        if amount is not None and amount <= 0:
            raise serializers.ValidationError({
                "amount": "Amount must be greater than zero."
            })

        if principal_amount is not None and principal_amount < 0:
            raise serializers.ValidationError({
                "principal_amount": "Principal amount cannot be negative."
            })

        if interest_amount is not None and interest_amount < 0:
            raise serializers.ValidationError({
                "interest_amount": "Interest amount cannot be negative."
            })

        if amount is not None and principal_amount is not None and interest_amount is not None:
            if principal_amount + interest_amount != amount:
                raise serializers.ValidationError({
                    "amount": "Principal amount plus interest amount must equal total amount."
                })

        if debt and principal_amount is not None:
            if principal_amount > debt.current_balance:
                raise serializers.ValidationError({
                    "principal_amount": "Principal amount cannot be greater than the current debt balance."
                })

        return attrs


class SavingsGoalSerializer(serializers.ModelSerializer):
    progress_percent = serializers.SerializerMethodField()

    class Meta:
        model = SavingsGoal
        fields = [
            "id",
            "name",
            "target_amount",
            "current_amount",
            "progress_percent",
            "target_date",
            "is_completed",
            "created_at",
        ]
        read_only_fields = ["id", "progress_percent", "created_at"]

    def get_progress_percent(self, obj):
        if obj.target_amount <= 0:
            return 0
        return round((obj.current_amount / obj.target_amount) * 100, 2)


class GoalContributionSerializer(serializers.ModelSerializer):
    goal_name = serializers.CharField(source="goal.name", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)

    class Meta:
        model = GoalContribution
        fields = [
            "id",
            "goal",
            "goal_name",
            "account",
            "account_name",
            "amount",
            "contribution_date",
            "notes",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user if request else None

        goal = attrs.get("goal")
        account = attrs.get("account")
        amount = attrs.get("amount")

        if self.instance:
            goal = goal if goal is not None else self.instance.goal
            account = account if account is not None else self.instance.account
            amount = amount if amount is not None else self.instance.amount

        if goal and goal.user != user:
            raise serializers.ValidationError({
                "goal": "Invalid savings goal."
            })

        if account and account.user != user:
            raise serializers.ValidationError({
                "account": "Invalid account."
            })

        if amount is not None and amount <= 0:
            raise serializers.ValidationError({
                "amount": "Amount must be greater than zero."
            })

        if goal and amount is not None:
            remaining_amount = goal.target_amount - goal.current_amount

            if self.instance:
                remaining_amount += self.instance.amount

            if amount > remaining_amount:
                raise serializers.ValidationError({
                    "amount": "Contribution cannot exceed the remaining target amount."
                })

        return attrs


class ReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Receipt
        fields = [
            "id",
            "transaction",
            "file",
            "extracted_text",
            "uploaded_at",
        ]
        read_only_fields = ["id", "extracted_text", "uploaded_at"]

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user if request else None

        transaction = attrs.get("transaction")
        file = attrs.get("file")

        if self.instance:
            transaction = transaction if transaction is not None else self.instance.transaction
            file = file if file is not None else self.instance.file

        if transaction and transaction.user != user:
            raise serializers.ValidationError({
                "transaction": "Invalid transaction."
            })

        if file:
            max_size = 5 * 1024 * 1024  # 5MB

            if file.size > max_size:
                raise serializers.ValidationError({
                    "file": "Receipt file must not exceed 5MB."
                })

            allowed_content_types = [
                "image/jpeg",
                "image/png",
                "image/webp",
                "application/pdf",
            ]

            content_type = getattr(file, "content_type", None)

            if content_type and content_type not in allowed_content_types:
                raise serializers.ValidationError({
                    "file": "Only JPG, PNG, WEBP, and PDF files are allowed."
                })

        return attrs


class RecurringBillSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = RecurringBill
        fields = [
            "id",
            "user",
            "account",
            "account_name",
            "category",
            "category_name",
            "name",
            "amount_due",
            "frequency",
            "due_day",
            "start_date",
            "end_date",
            "auto_generate",
            "is_active",
            "notes",
            "created_at",
        ]
        read_only_fields = [
            "user",
            "account_name",
            "category_name",
            "created_at",
        ]

    def validate_due_day(self, value):
        if value < 1 or value > 31:
            raise serializers.ValidationError("Due day must be between 1 and 31.")
        return value

    def validate_amount_due(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount due must be greater than zero.")
        return value