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
    Bill,
    Debt,
    DebtPayment,
    SavingsGoal,
    GoalContribution,
)


User = get_user_model()


class FinanceBalanceLogicTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
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
            opening_balance=Decimal("5000.00"),
            current_balance=Decimal("5000.00"),
            currency="PHP",
        )

        self.ewallet_account = Account.objects.create(
            user=self.user,
            name="GCash",
            account_type="ewallet",
            institution_name="GCash",
            opening_balance=Decimal("500.00"),
            current_balance=Decimal("500.00"),
            currency="PHP",
        )

        self.credit_card_account = Account.objects.create(
            user=self.user,
            name="UnionBank Credit Card",
            account_type="credit_card",
            institution_name="UnionBank",
            opening_balance=Decimal("0.00"),
            current_balance=Decimal("0.00"),
            credit_limit=Decimal("50000.00"),
            currency="PHP",
        )

        self.income_category = Category.objects.create(
            user=self.user,
            name="Salary",
            category_type="income",
        )

        self.expense_category = Category.objects.create(
            user=self.user,
            name="Food",
            category_type="expense",
        )

        self.debt_category = Category.objects.create(
            user=self.user,
            name="Credit Card Payment",
            category_type="debt",
        )

    def refresh_accounts(self):
        self.cash_account.refresh_from_db()
        self.bank_account.refresh_from_db()
        self.ewallet_account.refresh_from_db()
        self.credit_card_account.refresh_from_db()

    def test_expense_decreases_account_balance(self):
        url = reverse("finance-transaction-list")

        payload = {
            "account": self.cash_account.id,
            "category": self.expense_category.id,
            "transaction_type": "expense",
            "title": "Lunch",
            "amount": "150.00",
            "transaction_date": "2026-04-25",
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.cash_account.refresh_from_db()
        self.assertEqual(self.cash_account.current_balance, Decimal("850.00"))

    def test_income_increases_account_balance(self):
        url = reverse("finance-transaction-list")

        payload = {
            "account": self.cash_account.id,
            "category": self.income_category.id,
            "transaction_type": "income",
            "title": "Salary",
            "amount": "2500.00",
            "transaction_date": "2026-04-25",
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.cash_account.refresh_from_db()
        self.assertEqual(self.cash_account.current_balance, Decimal("3500.00"))

    def test_edit_transaction_reverses_old_effect_and_applies_new_effect(self):
        transaction_obj = Transaction.objects.create(
            user=self.user,
            account=self.cash_account,
            category=self.expense_category,
            transaction_type="expense",
            title="Groceries",
            amount=Decimal("200.00"),
            transaction_date=date(2026, 4, 25),
        )

        # Manually simulate original balance effect because direct model create does not call ViewSet logic.
        self.cash_account.current_balance -= Decimal("200.00")
        self.cash_account.save(update_fields=["current_balance"])

        url = reverse("finance-transaction-detail", args=[transaction_obj.id])

        payload = {
            "amount": "350.00",
        }

        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.cash_account.refresh_from_db()

        # Starting 1000 - old 200 + old 200 - new 350 = 650
        self.assertEqual(self.cash_account.current_balance, Decimal("650.00"))

    def test_delete_transaction_reverses_balance_effect(self):
        transaction_obj = Transaction.objects.create(
            user=self.user,
            account=self.cash_account,
            category=self.expense_category,
            transaction_type="expense",
            title="Groceries",
            amount=Decimal("200.00"),
            transaction_date=date(2026, 4, 25),
        )

        self.cash_account.current_balance -= Decimal("200.00")
        self.cash_account.save(update_fields=["current_balance"])

        url = reverse("finance-transaction-detail", args=[transaction_obj.id])

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        self.cash_account.refresh_from_db()
        self.assertEqual(self.cash_account.current_balance, Decimal("1000.00"))

    def test_transfer_subtracts_from_source_and_adds_to_destination(self):
        url = reverse("finance-transfer-list")

        payload = {
            "from_account": self.bank_account.id,
            "to_account": self.ewallet_account.id,
            "amount": "1000.00",
            "transfer_date": "2026-04-25",
            "notes": "Cash in",
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.bank_account.refresh_from_db()
        self.ewallet_account.refresh_from_db()

        self.assertEqual(self.bank_account.current_balance, Decimal("4000.00"))
        self.assertEqual(self.ewallet_account.current_balance, Decimal("1500.00"))

    def test_edit_transfer_reverses_old_and_applies_new(self):
        transfer_obj = Transfer.objects.create(
            user=self.user,
            from_account=self.bank_account,
            to_account=self.ewallet_account,
            amount=Decimal("1000.00"),
            transfer_date=date(2026, 4, 25),
        )

        self.bank_account.current_balance -= Decimal("1000.00")
        self.bank_account.save(update_fields=["current_balance"])

        self.ewallet_account.current_balance += Decimal("1000.00")
        self.ewallet_account.save(update_fields=["current_balance"])

        url = reverse("finance-transfer-detail", args=[transfer_obj.id])

        payload = {
            "amount": "1500.00",
        }

        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.bank_account.refresh_from_db()
        self.ewallet_account.refresh_from_db()

        self.assertEqual(self.bank_account.current_balance, Decimal("3500.00"))
        self.assertEqual(self.ewallet_account.current_balance, Decimal("2000.00"))

    def test_delete_transfer_reverses_transfer_effect(self):
        transfer_obj = Transfer.objects.create(
            user=self.user,
            from_account=self.bank_account,
            to_account=self.ewallet_account,
            amount=Decimal("1000.00"),
            transfer_date=date(2026, 4, 25),
        )

        self.bank_account.current_balance -= Decimal("1000.00")
        self.bank_account.save(update_fields=["current_balance"])

        self.ewallet_account.current_balance += Decimal("1000.00")
        self.ewallet_account.save(update_fields=["current_balance"])

        url = reverse("finance-transfer-detail", args=[transfer_obj.id])

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        self.bank_account.refresh_from_db()
        self.ewallet_account.refresh_from_db()

        self.assertEqual(self.bank_account.current_balance, Decimal("5000.00"))
        self.assertEqual(self.ewallet_account.current_balance, Decimal("500.00"))

    def test_cash_account_cannot_go_negative(self):
        url = reverse("finance-transaction-list")

        payload = {
            "account": self.cash_account.id,
            "category": self.expense_category.id,
            "transaction_type": "expense",
            "title": "Expensive item",
            "amount": "1500.00",
            "transaction_date": "2026-04-25",
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.cash_account.refresh_from_db()
        self.assertEqual(self.cash_account.current_balance, Decimal("1000.00"))

    def test_bank_account_cannot_transfer_more_than_balance(self):
        url = reverse("finance-transfer-list")

        payload = {
            "from_account": self.bank_account.id,
            "to_account": self.ewallet_account.id,
            "amount": "6000.00",
            "transfer_date": "2026-04-25",
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.bank_account.refresh_from_db()
        self.ewallet_account.refresh_from_db()

        self.assertEqual(self.bank_account.current_balance, Decimal("5000.00"))
        self.assertEqual(self.ewallet_account.current_balance, Decimal("500.00"))

    def test_credit_card_can_go_negative(self):
        url = reverse("finance-transaction-list")

        payload = {
            "account": self.credit_card_account.id,
            "category": self.expense_category.id,
            "transaction_type": "expense",
            "title": "Online purchase",
            "amount": "2000.00",
            "transaction_date": "2026-04-25",
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.credit_card_account.refresh_from_db()
        self.assertEqual(self.credit_card_account.current_balance, Decimal("-2000.00"))

    def test_bill_mark_paid_decreases_account_balance(self):
        bill = Bill.objects.create(
            user=self.user,
            account=self.bank_account,
            category=self.expense_category,
            name="Internet Bill",
            amount_due=Decimal("1500.00"),
            amount_paid=Decimal("0.00"),
            due_date=date(2026, 4, 30),
            status="unpaid",
        )

        url = reverse("finance-bill-mark-paid", args=[bill.id])

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.bank_account.refresh_from_db()
        bill.refresh_from_db()

        self.assertEqual(self.bank_account.current_balance, Decimal("3500.00"))
        self.assertEqual(bill.status, "paid")
        self.assertEqual(bill.amount_paid, Decimal("1500.00"))
        self.assertIsNotNone(bill.paid_date)

    def test_bill_mark_paid_cannot_make_asset_account_negative(self):
        bill = Bill.objects.create(
            user=self.user,
            account=self.ewallet_account,
            category=self.expense_category,
            name="Large Bill",
            amount_due=Decimal("1000.00"),
            amount_paid=Decimal("0.00"),
            due_date=date(2026, 4, 30),
            status="unpaid",
        )

        url = reverse("finance-bill-mark-paid", args=[bill.id])

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.ewallet_account.refresh_from_db()
        bill.refresh_from_db()

        self.assertEqual(self.ewallet_account.current_balance, Decimal("500.00"))
        self.assertEqual(bill.status, "unpaid")

    def test_debt_payment_decreases_account_and_debt_balance(self):
        debt = Debt.objects.create(
            user=self.user,
            name="Credit Card Debt",
            lender="UnionBank",
            original_amount=Decimal("10000.00"),
            current_balance=Decimal("10000.00"),
            interest_rate=Decimal("3.00"),
            minimum_payment=Decimal("1000.00"),
        )

        url = reverse("finance-debt-payment-list")

        payload = {
            "debt": debt.id,
            "account": self.bank_account.id,
            "amount": "3000.00",
            "principal_amount": "2500.00",
            "interest_amount": "500.00",
            "payment_date": "2026-04-25",
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.bank_account.refresh_from_db()
        debt.refresh_from_db()

        self.assertEqual(self.bank_account.current_balance, Decimal("2000.00"))
        self.assertEqual(debt.current_balance, Decimal("7500.00"))

    def test_delete_debt_payment_reverses_account_and_debt_balance(self):
        debt = Debt.objects.create(
            user=self.user,
            name="Credit Card Debt",
            lender="UnionBank",
            original_amount=Decimal("10000.00"),
            current_balance=Decimal("7500.00"),
        )

        payment = DebtPayment.objects.create(
            user=self.user,
            debt=debt,
            account=self.bank_account,
            amount=Decimal("3000.00"),
            principal_amount=Decimal("2500.00"),
            interest_amount=Decimal("500.00"),
            payment_date=date(2026, 4, 25),
        )

        self.bank_account.current_balance -= Decimal("3000.00")
        self.bank_account.save(update_fields=["current_balance"])

        url = reverse("finance-debt-payment-detail", args=[payment.id])

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        self.bank_account.refresh_from_db()
        debt.refresh_from_db()

        self.assertEqual(self.bank_account.current_balance, Decimal("5000.00"))
        self.assertEqual(debt.current_balance, Decimal("10000.00"))

    def test_goal_contribution_decreases_account_and_increases_goal(self):
        goal = SavingsGoal.objects.create(
            user=self.user,
            name="Emergency Fund",
            target_amount=Decimal("10000.00"),
            current_amount=Decimal("1000.00"),
            target_date=date(2026, 12, 31),
        )

        url = reverse("finance-goal-contribution-list")

        payload = {
            "goal": goal.id,
            "account": self.bank_account.id,
            "amount": "2000.00",
            "contribution_date": "2026-04-25",
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.bank_account.refresh_from_db()
        goal.refresh_from_db()

        self.assertEqual(self.bank_account.current_balance, Decimal("3000.00"))
        self.assertEqual(goal.current_amount, Decimal("3000.00"))

    def test_delete_goal_contribution_reverses_account_and_goal(self):
        goal = SavingsGoal.objects.create(
            user=self.user,
            name="Emergency Fund",
            target_amount=Decimal("10000.00"),
            current_amount=Decimal("3000.00"),
        )

        contribution = GoalContribution.objects.create(
            user=self.user,
            goal=goal,
            account=self.bank_account,
            amount=Decimal("2000.00"),
            contribution_date=date(2026, 4, 25),
        )

        self.bank_account.current_balance -= Decimal("2000.00")
        self.bank_account.save(update_fields=["current_balance"])

        url = reverse("finance-goal-contribution-detail", args=[contribution.id])

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        self.bank_account.refresh_from_db()
        goal.refresh_from_db()

        self.assertEqual(self.bank_account.current_balance, Decimal("5000.00"))
        self.assertEqual(goal.current_amount, Decimal("1000.00"))