from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard_view, name="finance_web_dashboard"),
    path("login/", views.web_login_view, name="finance_web_login"),
    path("register/", views.web_register_view, name="finance_web_register"),
    path("logout/", views.web_logout_view, name="finance_web_logout"),

    path("transactions/", views.transactions_view, name="finance_web_transactions"),
    path("transactions/add/", views.transaction_create_view, name="finance_web_transaction_create"),
    path("transactions/<int:pk>/edit/", views.transaction_edit_view, name="finance_web_transaction_edit"),
    path(
        "transactions/<int:pk>/delete/",
        views.transaction_delete_view,
        name="finance_web_transaction_delete",
    ),

    path("accounts/", views.accounts_view, name="finance_web_accounts"),
    path("accounts/add/", views.account_create_view, name="finance_web_account_create"),
    path("accounts/<int:pk>/edit/", views.account_edit_view, name="finance_web_account_edit"),

    path("bills/", views.bills_view, name="finance_web_bills"),
    path("bills/add/", views.bill_create_view, name="finance_web_bill_create"),
    path("bills/<int:pk>/edit/", views.bill_edit_view, name="finance_web_bill_edit"),
    path("bills/<int:pk>/mark-paid/", views.bill_mark_paid_view, name="finance_web_bill_mark_paid"),
    path(
        "bills/<int:pk>/unmark-paid/",
        views.bill_unmark_paid_view,
        name="finance_web_bill_unmark_paid",
    ),

    path("recurring-bills/", views.recurring_bills_view, name="finance_web_recurring_bills"),
    path("recurring-bills/add/", views.recurring_bill_create_view, name="finance_web_recurring_bill_create"),
    path("recurring-bills/<int:pk>/edit/", views.recurring_bill_edit_view, name="finance_web_recurring_bill_edit"),
    path("recurring-bills/generate/", views.recurring_bills_generate_view, name="finance_web_recurring_bills_generate"),

    path("transfers/", views.transfers_view, name="finance_web_transfers"),
    path("transfers/add/", views.transfer_create_view, name="finance_web_transfer_create"),
    path("transfers/<int:pk>/edit/", views.transfer_edit_view, name="finance_web_transfer_edit"),
    path(
        "transfers/<int:pk>/delete/",
        views.transfer_delete_view,
        name="finance_web_transfer_delete",
    ),

    path("debts/", views.debts_view, name="finance_web_debts"),
    path("debts/add/", views.debt_create_view, name="finance_web_debt_create"),
    path("debts/<int:pk>/edit/", views.debt_edit_view, name="finance_web_debt_edit"),

    path("debt-payments/add/", views.debt_payment_create_view, name="finance_web_debt_payment_create"),
    path("debt-payments/<int:pk>/edit/", views.debt_payment_edit_view, name="finance_web_debt_payment_edit"),
    path("debt-payments/<int:pk>/delete/", views.debt_payment_delete_view, name="finance_web_debt_payment_delete"),

    path("goals/", views.goals_view, name="finance_web_goals"),
    path("goals/add/", views.goal_create_view, name="finance_web_goal_create"),
    path("goals/<int:pk>/edit/", views.goal_edit_view, name="finance_web_goal_edit"),

    path(
        "goal-contributions/add/",
        views.goal_contribution_create_view,
        name="finance_web_goal_contribution_create",
    ),
    path(
        "goal-contributions/<int:pk>/edit/",
        views.goal_contribution_edit_view,
        name="finance_web_goal_contribution_edit",
    ),
    path(
        "goal-contributions/<int:pk>/delete/",
        views.goal_contribution_delete_view,
        name="finance_web_goal_contribution_delete",
    ),

    path("categories/", views.categories_view, name="finance_web_categories"),
    path("categories/add/", views.category_create_view, name="finance_web_category_create"),
    path("categories/<int:pk>/edit/", views.category_edit_view, name="finance_web_category_edit"),

    path("budgets/", views.budgets_view, name="finance_web_budgets"),
    path("budgets/add/", views.budget_create_view, name="finance_web_budget_create"),
    path("budgets/<int:pk>/edit/", views.budget_edit_view, name="finance_web_budget_edit"),
    path("budgets/<int:pk>/delete/", views.budget_delete_view, name="finance_web_budget_delete"),

    path("reports/", views.reports_view, name="finance_web_reports"),
]