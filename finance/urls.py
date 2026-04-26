from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    AccountViewSet,
    CategoryViewSet,
    MerchantViewSet,
    TransactionViewSet,
    TransferViewSet,
    BudgetViewSet,
    BillViewSet,
    DebtViewSet,
    DebtPaymentViewSet,
    SavingsGoalViewSet,
    GoalContributionViewSet,
    ReceiptViewSet,
    FinanceDashboardViewSet, FinanceSetupStatusViewSet, RecurringBillViewSet,
)

router = DefaultRouter()
router.register("accounts", AccountViewSet, basename="finance-account")
router.register("categories", CategoryViewSet, basename="finance-category")
router.register("merchants", MerchantViewSet, basename="finance-merchant")
router.register("transactions", TransactionViewSet, basename="finance-transaction")
router.register("transfers", TransferViewSet, basename="finance-transfer")
router.register("budgets", BudgetViewSet, basename="finance-budget")
router.register("bills", BillViewSet, basename="finance-bill")
router.register("debts", DebtViewSet, basename="finance-debt")
router.register("debt-payments", DebtPaymentViewSet, basename="finance-debt-payment")
router.register("savings-goals", SavingsGoalViewSet, basename="finance-savings-goal")
router.register("goal-contributions", GoalContributionViewSet, basename="finance-goal-contribution")
router.register("receipts", ReceiptViewSet, basename="finance-receipt")
router.register("dashboard", FinanceDashboardViewSet, basename="finance-dashboard")
router.register("setup-status", FinanceSetupStatusViewSet, basename="finance-setup-status")

router.register(
    r"recurring-bills",
    RecurringBillViewSet,
    basename="finance-recurring-bills",
)

urlpatterns = [
    path("", include(router.urls)),
]