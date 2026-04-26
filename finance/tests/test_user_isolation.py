from decimal import Decimal
from datetime import date

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from finance.models import (
    Account,
    Category,
    Transaction,
    Transfer,
    Budget,
    Bill,
    Debt,
    SavingsGoal,
)


User = get_user_model()


class FinanceUserIsolationTests(APITestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(
            username="user_a",
            email="a@example.com",
            password="StrongPass123!",
        )
        self.user_b = User.objects.create_user(
            username="user_b",
            email="b@example.com",
            password="StrongPass123!",
        )

        self.account_a = Account.objects.create(
            user=self.user_a,
            name="User A Cash",
            account_type="cash",
            institution_name="Cash",
            opening_balance=Decimal("1000.00"),
            current_balance=Decimal("1000.00"),
        )

        self.account_b = Account.objects.create(
            user=self.user_b,
            name="User B Cash",
            account_type="cash",
            institution_name="Cash",
            opening_balance=Decimal("5000.00"),
            current_balance=Decimal("5000.00"),
        )

        self.expense_category_a = Category.objects.create(
            user=self.user_a,
            name="Food",
            category_type="expense",
        )

        self.expense_category_b = Category.objects.create(
            user=self.user_b,
            name="Food",
            category_type="expense",
        )

        self.income_category_b = Category.objects.create(
            user=self.user_b,
            name="Salary",
            category_type="income",
        )

        self.transaction_b = Transaction.objects.create(
            user=self.user_b,
            account=self.account_b,
            category=self.expense_category_b,
            transaction_type="expense",
            title="User B Expense",
            amount=Decimal("100.00"),
            transaction_date=date(2026, 4, 25),
        )

        self.bill_b = Bill.objects.create(
            user=self.user_b,
            account=self.account_b,
            category=self.expense_category_b,
            name="User B Bill",
            amount_due=Decimal("1000.00"),
            amount_paid=Decimal("0.00"),
            due_date=date(2026, 4, 30),
            status="unpaid",
        )

        self.debt_b = Debt.objects.create(
            user=self.user_b,
            name="User B Debt",
            lender="Bank B",
            original_amount=Decimal("10000.00"),
            current_balance=Decimal("10000.00"),
        )

        self.goal_b = SavingsGoal.objects.create(
            user=self.user_b,
            name="User B Goal",
            target_amount=Decimal("10000.00"),
            current_amount=Decimal("1000.00"),
        )

        self.client.force_authenticate(user=self.user_a)

    def test_user_cannot_list_another_users_transactions(self):
        url = reverse("finance-transaction-list")

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_user_cannot_retrieve_another_users_transaction(self):
        url = reverse("finance-transaction-detail", args=[self.transaction_b.id])

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_cannot_create_transaction_using_another_users_account(self):
        url = reverse("finance-transaction-list")

        payload = {
            "account": self.account_b.id,
            "category": self.expense_category_a.id,
            "transaction_type": "expense",
            "title": "Invalid Expense",
            "amount": "100.00",
            "transaction_date": "2026-04-25",
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("account", response.data)

        self.account_b.refresh_from_db()
        self.assertEqual(self.account_b.current_balance, Decimal("5000.00"))

    def test_user_cannot_create_transaction_using_another_users_category(self):
        url = reverse("finance-transaction-list")

        payload = {
            "account": self.account_a.id,
            "category": self.expense_category_b.id,
            "transaction_type": "expense",
            "title": "Invalid Category Expense",
            "amount": "100.00",
            "transaction_date": "2026-04-25",
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("category", response.data)

        self.account_a.refresh_from_db()
        self.assertEqual(self.account_a.current_balance, Decimal("1000.00"))

    def test_user_cannot_create_transfer_using_another_users_from_account(self):
        url = reverse("finance-transfer-list")

        payload = {
            "from_account": self.account_b.id,
            "to_account": self.account_a.id,
            "amount": "100.00",
            "transfer_date": "2026-04-25",
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("from_account", response.data)

        self.account_b.refresh_from_db()
        self.account_a.refresh_from_db()

        self.assertEqual(self.account_b.current_balance, Decimal("5000.00"))
        self.assertEqual(self.account_a.current_balance, Decimal("1000.00"))

    def test_user_cannot_create_transfer_using_another_users_to_account(self):
        url = reverse("finance-transfer-list")

        payload = {
            "from_account": self.account_a.id,
            "to_account": self.account_b.id,
            "amount": "100.00",
            "transfer_date": "2026-04-25",
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("to_account", response.data)

        self.account_b.refresh_from_db()
        self.account_a.refresh_from_db()

        self.assertEqual(self.account_b.current_balance, Decimal("5000.00"))
        self.assertEqual(self.account_a.current_balance, Decimal("1000.00"))

    def test_user_cannot_create_budget_using_another_users_category(self):
        url = reverse("finance-budget-list")

        payload = {
            "category": self.expense_category_b.id,
            "amount_limit": "3000.00",
            "month": 4,
            "year": 2026,
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("category", response.data)

        self.assertFalse(
            Budget.objects.filter(
                user=self.user_a,
                category=self.expense_category_b,
            ).exists()
        )

    def test_user_cannot_mark_another_users_bill_as_paid(self):
        url = reverse("finance-bill-mark-paid", args=[self.bill_b.id])

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.bill_b.refresh_from_db()
        self.account_b.refresh_from_db()

        self.assertEqual(self.bill_b.status, "unpaid")
        self.assertEqual(self.account_b.current_balance, Decimal("5000.00"))

    def test_user_cannot_create_debt_payment_for_another_users_debt(self):
        url = reverse("finance-debt-payment-list")

        payload = {
            "debt": self.debt_b.id,
            "account": self.account_a.id,
            "amount": "1000.00",
            "principal_amount": "900.00",
            "interest_amount": "100.00",
            "payment_date": "2026-04-25",
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("debt", response.data)

        self.debt_b.refresh_from_db()
        self.account_a.refresh_from_db()

        self.assertEqual(self.debt_b.current_balance, Decimal("10000.00"))
        self.assertEqual(self.account_a.current_balance, Decimal("1000.00"))

    def test_user_cannot_create_goal_contribution_for_another_users_goal(self):
        url = reverse("finance-goal-contribution-list")

        payload = {
            "goal": self.goal_b.id,
            "account": self.account_a.id,
            "amount": "500.00",
            "contribution_date": "2026-04-25",
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("goal", response.data)

        self.goal_b.refresh_from_db()
        self.account_a.refresh_from_db()

        self.assertEqual(self.goal_b.current_amount, Decimal("1000.00"))
        self.assertEqual(self.account_a.current_balance, Decimal("1000.00"))