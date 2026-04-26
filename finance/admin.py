from django.contrib import admin
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
    Receipt,
)


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "account_type", "current_balance", "is_active")
    list_filter = ("account_type", "is_active")
    search_fields = ("name", "user__username")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "category_type", "is_default", "is_active")
    list_filter = ("category_type", "is_default", "is_active")
    search_fields = ("name", "user__username")


@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "default_category")
    search_fields = ("name", "user__username")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "user",
        "account",
        "category",
        "transaction_type",
        "amount",
        "transaction_date",
    )
    list_filter = ("transaction_type", "transaction_date", "category")
    search_fields = ("title", "notes", "reference_no", "user__username")
    date_hierarchy = "transaction_date"


@admin.register(Transfer)
class TransferAdmin(admin.ModelAdmin):
    list_display = ("user", "from_account", "to_account", "amount", "transfer_date")
    list_filter = ("transfer_date",)
    date_hierarchy = "transfer_date"


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ("user", "category", "amount_limit", "month", "year")
    list_filter = ("month", "year", "category")


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "amount_due", "amount_paid", "due_date", "status")
    list_filter = ("status", "due_date")
    search_fields = ("name", "user__username")
    date_hierarchy = "due_date"


@admin.register(Debt)
class DebtAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "lender", "original_amount", "current_balance", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "lender", "user__username")


@admin.register(DebtPayment)
class DebtPaymentAdmin(admin.ModelAdmin):
    list_display = ("debt", "user", "amount", "principal_amount", "interest_amount", "payment_date")
    list_filter = ("payment_date",)
    date_hierarchy = "payment_date"


@admin.register(SavingsGoal)
class SavingsGoalAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "target_amount", "current_amount", "target_date", "is_completed")
    list_filter = ("is_completed",)


@admin.register(GoalContribution)
class GoalContributionAdmin(admin.ModelAdmin):
    list_display = ("goal", "user", "amount", "contribution_date")
    list_filter = ("contribution_date",)


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ("transaction", "user", "uploaded_at")