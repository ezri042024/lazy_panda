from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError


class Account(models.Model):
    ACCOUNT_TYPES = [
        ("cash", "Cash"),
        ("bank", "Bank"),
        ("ewallet", "E-Wallet"),
        ("credit_card", "Credit Card"),
        ("investment", "Investment"),
        ("loan", "Loan"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="finance_accounts",
    )

    name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=30, choices=ACCOUNT_TYPES)

    institution_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Example: BDO, BPI, GCash, Maya, UnionBank"
    )

    account_number_last4 = models.CharField(
        max_length=4,
        blank=True,
        help_text="Optional last 4 digits only"
    )

    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    current_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    credit_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Only used for credit cards"
    )

    billing_day = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Credit card billing statement day"
    )

    due_day = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Credit card payment due day"
    )

    currency = models.CharField(max_length=10, default="PHP")
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["account_type", "institution_name", "name"]
        unique_together = ("user", "name")

    def __str__(self):
        return self.name


class Category(models.Model):
    CATEGORY_TYPES = [
        ("income", "Income"),
        ("expense", "Expense"),
        ("transfer", "Transfer"),
        ("saving", "Saving"),
        ("debt", "Debt"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="finance_categories",
    )
    name = models.CharField(max_length=100)
    category_type = models.CharField(max_length=20, choices=CATEGORY_TYPES)
    icon = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=20, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category_type", "name"]
        unique_together = ("user", "name", "category_type")
        verbose_name_plural = "Categories"

    def __str__(self):
        return f"{self.name} - {self.category_type}"


class Merchant(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="finance_merchants",
    )
    name = models.CharField(max_length=150)
    default_category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_merchants",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("user", "name")

    def __str__(self):
        return self.name


class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ("income", "Income"),
        ("expense", "Expense"),
        ("adjustment", "Adjustment"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="finance_transactions",
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )

    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    title = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_date = models.DateField()

    notes = models.TextField(blank=True)
    reference_no = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-transaction_date", "-created_at"]

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Amount must be greater than zero.")

    def __str__(self):
        return f"{self.title} - {self.amount}"


class Transfer(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="finance_transfers",
    )
    from_account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="transfers_out",
    )
    to_account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="transfers_in",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transfer_date = models.DateField()
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-transfer_date", "-created_at"]

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Amount must be greater than zero.")

        if self.from_account_id == self.to_account_id:
            raise ValidationError("Cannot transfer to the same account.")

    def __str__(self):
        return f"{self.from_account} to {self.to_account} - {self.amount}"


class Budget(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="finance_budgets",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="budgets",
    )
    amount_limit = models.DecimalField(max_digits=12, decimal_places=2)
    month = models.PositiveSmallIntegerField()
    year = models.PositiveIntegerField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-year", "-month", "category"]
        unique_together = ("user", "category", "month", "year")

    def __str__(self):
        return f"{self.category} - {self.month}/{self.year}"


class RecurringBill(models.Model):
    FREQUENCY_CHOICES = [
        ("monthly", "Monthly"),
        ("weekly", "Weekly"),
        ("yearly", "Yearly"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="finance_recurring_bills",
    )

    account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recurring_bills",
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recurring_bills",
    )

    name = models.CharField(max_length=150)
    amount_due = models.DecimalField(max_digits=12, decimal_places=2)

    frequency = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        default="monthly",
    )

    due_day = models.PositiveSmallIntegerField(
        help_text="For monthly bills, example: 15 means every 15th day."
    )

    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    auto_generate = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_day", "name"]

    def clean(self):
        if self.amount_due <= 0:
            raise ValidationError("Amount due must be greater than zero.")

        if self.due_day < 1 or self.due_day > 31:
            raise ValidationError("Due day must be between 1 and 31.")

    def __str__(self):
        return self.name


class Bill(models.Model):
    STATUS_CHOICES = [
        ("unpaid", "Unpaid"),
        ("paid", "Paid"),
        ("overdue", "Overdue"),
        ("partial", "Partially Paid"),
        ("cancelled", "Cancelled"),
    ]

    recurring_bill = models.ForeignKey(
        RecurringBill,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_bills",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="finance_bills",
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bills",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bills",
    )

    payment_transaction = models.ForeignKey(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="paid_bills",
    )

    name = models.CharField(max_length=150)
    amount_due = models.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    due_date = models.DateField()
    paid_date = models.DateField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="unpaid")
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "recurring_bill", "due_date"],
                name="unique_recurring_bill_due_date",
            )
        ]

    def __str__(self):
        return self.name


class Debt(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="finance_debts",
    )
    name = models.CharField(max_length=150)
    lender = models.CharField(max_length=150, blank=True)

    original_amount = models.DecimalField(max_digits=12, decimal_places=2)
    current_balance = models.DecimalField(max_digits=12, decimal_places=2)

    interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Annual interest rate percentage",
    )
    minimum_payment = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    due_day = models.PositiveSmallIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class DebtPayment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="finance_debt_payments",
    )
    debt = models.ForeignKey(
        Debt,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="debt_payments",
    )

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    principal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    interest_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    payment_date = models.DateField()
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-payment_date", "-created_at"]

    def __str__(self):
        return f"{self.debt} - {self.amount}"


class SavingsGoal(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="finance_savings_goals",
    )
    name = models.CharField(max_length=150)
    target_amount = models.DecimalField(max_digits=12, decimal_places=2)
    current_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    target_date = models.DateField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["is_completed", "target_date", "name"]

    def __str__(self):
        return self.name


class GoalContribution(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="finance_goal_contributions",
    )
    goal = models.ForeignKey(
        SavingsGoal,
        on_delete=models.CASCADE,
        related_name="contributions",
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="goal_contributions",
    )

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    contribution_date = models.DateField()

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-contribution_date", "-created_at"]

    def __str__(self):
        return f"{self.goal} - {self.amount}"


class Receipt(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="finance_receipts",
    )
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name="receipts",
    )
    file = models.FileField(upload_to="finance/receipts/")
    extracted_text = models.TextField(blank=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Receipt for {self.transaction}"


