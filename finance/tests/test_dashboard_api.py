from decimal import Decimal
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from finance.models import (
    Account,
    Category,
    Transaction,
    Bill,
    Debt,
    SavingsGoal,
)


User = get_user_model()


class FinanceDashboardAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="dashboard_user",
            email="dashboard@example.com",
            password="StrongPass123!",
        )

        self.other_user = User.objects.create_user(
            username="other_user",
            email="other@example.com",
            password="StrongPass123!",
        )

        self.client.force_authenticate(user=self.user)

        self.cash_account = Account.objects.create(
            user=self.user,
            name="Cash Wallet",
            account_type="cash",
            institution_name="Cash",
            opening_balance=Decimal("1000.00"),
            current_balance=Decimal("1000.00"),
            currency="PHP",
        )

        self.bank_account = Account.objects.create(
            user=self.user,
            name="BDO Savings",
            account_type="bank",
            institution_name="BDO",
            opening_balance=Decimal("10000.00"),
            current_balance=Decimal("10000.00"),
            currency="PHP",
        )

        self.credit_card_account = Account.objects.create(
            user=self.user,
            name="UnionBank Credit Card",
            account_type="credit_card",
            institution_name="UnionBank",
            opening_balance=Decimal("0.00"),
            current_balance=Decimal("-3000.00"),
            credit_limit=Decimal("50000.00"),
            currency="PHP",
        )

        # This account should not be included because it belongs to another user.
        Account.objects.create(
            user=self.other_user,
            name="Other User Bank",
            account_type="bank",
            institution_name="Other Bank",
            opening_balance=Decimal("999999.00"),
            current_balance=Decimal("999999.00"),
            currency="PHP",
        )

        self.salary_category = Category.objects.create(
            user=self.user,
            name="Salary",
            category_type="income",
        )

        self.food_category = Category.objects.create(
            user=self.user,
            name="Food",
            category_type="expense",
        )

        self.transport_category = Category.objects.create(
            user=self.user,
            name="Transportation",
            category_type="expense",
        )

        other_category = Category.objects.create(
            user=self.other_user,
            name="Other Food",
            category_type="expense",
        )

        # Current month transactions
        Transaction.objects.create(
            user=self.user,
            account=self.bank_account,
            category=self.salary_category,
            transaction_type="income",
            title="Salary",
            amount=Decimal("25000.00"),
            transaction_date=date(2026, 4, 10),
        )

        Transaction.objects.create(
            user=self.user,
            account=self.cash_account,
            category=self.food_category,
            transaction_type="expense",
            title="Groceries",
            amount=Decimal("1500.00"),
            transaction_date=date(2026, 4, 12),
        )

        Transaction.objects.create(
            user=self.user,
            account=self.cash_account,
            category=self.food_category,
            transaction_type="expense",
            title="Lunch",
            amount=Decimal("250.00"),
            transaction_date=date(2026, 4, 13),
        )

        Transaction.objects.create(
            user=self.user,
            account=self.cash_account,
            category=self.transport_category,
            transaction_type="expense",
            title="Gas",
            amount=Decimal("1000.00"),
            transaction_date=date(2026, 4, 14),
        )

        # Different month; should not be included in April 2026 totals.
        Transaction.objects.create(
            user=self.user,
            account=self.cash_account,
            category=self.food_category,
            transaction_type="expense",
            title="March Food",
            amount=Decimal("999.00"),
            transaction_date=date(2026, 3, 20),
        )

        # Other user's transaction; should not be included.
        other_account = Account.objects.create(
            user=self.other_user,
            name="Other Cash",
            account_type="cash",
            opening_balance=Decimal("1000.00"),
            current_balance=Decimal("1000.00"),
        )

        Transaction.objects.create(
            user=self.other_user,
            account=other_account,
            category=other_category,
            transaction_type="expense",
            title="Other Expense",
            amount=Decimal("9999.00"),
            transaction_date=date(2026, 4, 15),
        )

        today = timezone.localdate()

        self.due_soon_bill = Bill.objects.create(
            user=self.user,
            account=self.bank_account,
            category=self.food_category,
            name="Due Soon Bill",
            amount_due=Decimal("1200.00"),
            amount_paid=Decimal("0.00"),
            due_date=today + timedelta(days=3),
            status="unpaid",
        )

        self.overdue_bill = Bill.objects.create(
            user=self.user,
            account=self.bank_account,
            category=self.food_category,
            name="Overdue Bill",
            amount_due=Decimal("800.00"),
            amount_paid=Decimal("0.00"),
            due_date=today - timedelta(days=3),
            status="unpaid",
        )

        self.paid_bill = Bill.objects.create(
            user=self.user,
            account=self.bank_account,
            category=self.food_category,
            name="Paid Bill",
            amount_due=Decimal("500.00"),
            amount_paid=Decimal("500.00"),
            due_date=today,
            paid_date=today,
            status="paid",
        )

        Bill.objects.create(
            user=self.other_user,
            name="Other User Bill",
            amount_due=Decimal("9999.00"),
            amount_paid=Decimal("0.00"),
            due_date=today,
            status="unpaid",
        )

        self.debt = Debt.objects.create(
            user=self.user,
            name="Credit Card Debt",
            lender="UnionBank",
            original_amount=Decimal("10000.00"),
            current_balance=Decimal("7000.00"),
            is_active=True,
        )

        Debt.objects.create(
            user=self.other_user,
            name="Other Debt",
            original_amount=Decimal("99999.00"),
            current_balance=Decimal("99999.00"),
            is_active=True,
        )

        self.goal = SavingsGoal.objects.create(
            user=self.user,
            name="Emergency Fund",
            target_amount=Decimal("50000.00"),
            current_amount=Decimal("10000.00"),
            target_date=date(2026, 12, 31),
            is_completed=False,
        )

        SavingsGoal.objects.create(
            user=self.other_user,
            name="Other Goal",
            target_amount=Decimal("999999.00"),
            current_amount=Decimal("999999.00"),
            is_completed=False,
        )

    def test_dashboard_returns_correct_summary_totals(self):
        url = reverse("finance-dashboard-list")

        response = self.client.get(url, {"month": 4, "year": 2026})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        summary = response.data["summary"]

        self.assertEqual(Decimal(str(summary["total_assets"])), Decimal("11000.00"))
        self.assertEqual(Decimal(str(summary["total_liabilities"])), Decimal("-3000.00"))
        self.assertEqual(Decimal(str(summary["net_worth"])), Decimal("8000.00"))

        self.assertEqual(Decimal(str(summary["total_income"])), Decimal("25000.00"))
        self.assertEqual(Decimal(str(summary["total_expense"])), Decimal("2750.00"))
        self.assertEqual(Decimal(str(summary["net_cashflow"])), Decimal("22250.00"))

        # unpaid_bills_total currently sums amount_due, not remaining balance.
        self.assertEqual(Decimal(str(summary["unpaid_bills_total"])), Decimal("2000.00"))

        self.assertEqual(Decimal(str(summary["total_debt_balance"])), Decimal("7000.00"))
        self.assertEqual(Decimal(str(summary["total_goal_saved"])), Decimal("10000.00"))
        self.assertEqual(Decimal(str(summary["total_goal_target"])), Decimal("50000.00"))

    def test_dashboard_returns_accounts_for_authenticated_user_only(self):
        url = reverse("finance-dashboard-list")

        response = self.client.get(url, {"month": 4, "year": 2026})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        account_names = [account["name"] for account in response.data["accounts"]]

        self.assertIn("Cash Wallet", account_names)
        self.assertIn("BDO Savings", account_names)
        self.assertIn("UnionBank Credit Card", account_names)

        self.assertNotIn("Other User Bank", account_names)
        self.assertNotIn("Other Cash", account_names)

    def test_dashboard_expense_by_category_is_correct(self):
        url = reverse("finance-dashboard-list")

        response = self.client.get(url, {"month": 4, "year": 2026})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        category_totals = {
            item["category__name"]: Decimal(str(item["total"]))
            for item in response.data["expense_by_category"]
        }

        self.assertEqual(category_totals["Food"], Decimal("1750.00"))
        self.assertEqual(category_totals["Transportation"], Decimal("1000.00"))

        self.assertNotIn("Other Food", category_totals)

    def test_dashboard_income_by_category_is_correct(self):
        url = reverse("finance-dashboard-list")

        response = self.client.get(url, {"month": 4, "year": 2026})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        category_totals = {
            item["category__name"]: Decimal(str(item["total"]))
            for item in response.data["income_by_category"]
        }

        self.assertEqual(category_totals["Salary"], Decimal("25000.00"))

    def test_dashboard_recent_transactions_are_limited_to_selected_month(self):
        url = reverse("finance-dashboard-list")

        response = self.client.get(url, {"month": 4, "year": 2026})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        titles = [
            item["title"]
            for item in response.data["recent_transactions"]
        ]

        self.assertIn("Salary", titles)
        self.assertIn("Groceries", titles)
        self.assertIn("Lunch", titles)
        self.assertIn("Gas", titles)

        self.assertNotIn("March Food", titles)
        self.assertNotIn("Other Expense", titles)

    def test_dashboard_due_soon_and_overdue_bills(self):
        url = reverse("finance-dashboard-list")

        response = self.client.get(url, {"month": 4, "year": 2026})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        due_soon_names = [
            item["name"]
            for item in response.data["due_soon_bills"]
        ]

        overdue_names = [
            item["name"]
            for item in response.data["overdue_bills"]
        ]

        self.assertIn("Due Soon Bill", due_soon_names)
        self.assertNotIn("Paid Bill", due_soon_names)
        self.assertNotIn("Other User Bill", due_soon_names)

        self.assertIn("Overdue Bill", overdue_names)
        self.assertNotIn("Paid Bill", overdue_names)
        self.assertNotIn("Other User Bill", overdue_names)

    def test_dashboard_goal_progress_is_correct(self):
        url = reverse("finance-dashboard-list")

        response = self.client.get(url, {"month": 4, "year": 2026})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        goals = response.data["goal_progress"]

        self.assertEqual(len(goals), 1)
        self.assertEqual(goals[0]["name"], "Emergency Fund")
        self.assertEqual(Decimal(str(goals[0]["target_amount"])), Decimal("50000.00"))
        self.assertEqual(Decimal(str(goals[0]["current_amount"])), Decimal("10000.00"))
        self.assertEqual(Decimal(str(goals[0]["progress_percent"])), Decimal("20.00"))

    def test_dashboard_requires_authentication(self):
        self.client.force_authenticate(user=None)

        url = reverse("finance-dashboard-list")

        response = self.client.get(url, {"month": 4, "year": 2026})

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)