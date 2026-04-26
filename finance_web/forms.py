from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm

from finance.models import Category, Account, Transaction, RecurringBill, Bill, Transfer, Debt, DebtPayment, \
    SavingsGoal, GoalContribution


class WebLoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Username",
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Password",
        })
    )


class WebRegisterForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Password",
        })
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Confirm password",
        })
    )

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name"]
        widgets = {
            "username": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Username",
            }),
            "email": forms.EmailInput(attrs={
                "class": "form-control",
                "placeholder": "Email",
            }),
            "first_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "First name",
            }),
            "last_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Last name",
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError("Passwords do not match.")

        return cleaned_data


class AccountWebForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = [
            "name",
            "account_type",
            "institution_name",
            "account_number_last4",
            "opening_balance",
            "current_balance",
            "credit_limit",
            "billing_day",
            "due_day",
            "currency",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "account_type": forms.Select(attrs={"class": "form-select"}),
            "institution_name": forms.TextInput(attrs={"class": "form-control"}),
            "account_number_last4": forms.TextInput(attrs={"class": "form-control", "maxlength": 4}),
            "opening_balance": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "current_balance": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "credit_limit": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "billing_day": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 31}),
            "due_day": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 31}),
            "currency": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class TransactionWebForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = [
            "account",
            "category",
            "transaction_type",
            "title",
            "amount",
            "transaction_date",
            "notes",
            "reference_no",
        ]
        widgets = {
            "account": forms.Select(attrs={"class": "form-select"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "transaction_type": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "transaction_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "reference_no": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user

        if user:
            self.fields["account"].queryset = Account.objects.filter(
                user=user,
                is_active=True,
            )

            self.fields["category"].queryset = Category.objects.filter(
                user=user,
                is_active=True,
            )

    def clean_amount(self):
        amount = self.cleaned_data["amount"]

        if amount <= 0:
            raise forms.ValidationError("Amount must be greater than zero.")

        return amount

    def clean_account(self):
        account = self.cleaned_data["account"]

        if self.user and account.user_id != self.user.id:
            raise forms.ValidationError("Invalid account.")

        return account

    def clean_category(self):
        category = self.cleaned_data.get("category")

        if category and self.user and category.user_id != self.user.id:
            raise forms.ValidationError("Invalid category.")

        return category


class BillWebForm(forms.ModelForm):
    class Meta:
        model = Bill
        fields = [
            "account",
            "category",
            "name",
            "amount_due",
            "amount_paid",
            "due_date",
            "paid_date",
            "status",
            "notes",
        ]
        widgets = {
            "account": forms.Select(attrs={"class": "form-select"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "amount_due": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "amount_paid": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "due_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "paid_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        if user:
            self.fields["account"].queryset = Account.objects.filter(
                user=user,
                is_active=True,
            )
            self.fields["category"].queryset = Category.objects.filter(
                user=user,
                is_active=True,
                category_type="expense",
            )

    def clean_amount_due(self):
        amount_due = self.cleaned_data["amount_due"]
        if amount_due <= 0:
            raise forms.ValidationError("Amount due must be greater than zero.")
        return amount_due

    def clean_amount_paid(self):
        amount_paid = self.cleaned_data["amount_paid"]
        if amount_paid < 0:
            raise forms.ValidationError("Amount paid cannot be negative.")
        return amount_paid


class RecurringBillWebForm(forms.ModelForm):
    class Meta:
        model = RecurringBill
        fields = [
            "account",
            "category",
            "name",
            "amount_due",
            "frequency",
            "due_day",
            "start_date",
            "end_date",
            "auto_generate",
            "is_active",
            "notes",
        ]
        widgets = {
            "account": forms.Select(attrs={"class": "form-select"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "amount_due": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "frequency": forms.Select(attrs={"class": "form-select"}),
            "due_day": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 31}),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "auto_generate": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        if user:
            self.fields["account"].queryset = Account.objects.filter(
                user=user,
                is_active=True,
            )
            self.fields["category"].queryset = Category.objects.filter(
                user=user,
                is_active=True,
                category_type="expense",
            )

    def clean_amount_due(self):
        amount_due = self.cleaned_data["amount_due"]
        if amount_due <= 0:
            raise forms.ValidationError("Amount due must be greater than zero.")
        return amount_due

    def clean_due_day(self):
        due_day = self.cleaned_data["due_day"]
        if due_day < 1 or due_day > 31:
            raise forms.ValidationError("Due day must be between 1 and 31.")
        return due_day


class TransferWebForm(forms.ModelForm):
    class Meta:
        model = Transfer
        fields = [
            "from_account",
            "to_account",
            "amount",
            "transfer_date",
            "notes",
        ]
        widgets = {
            "from_account": forms.Select(attrs={"class": "form-select"}),
            "to_account": forms.Select(attrs={"class": "form-select"}),
            "amount": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01",
            }),
            "transfer_date": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date",
            }),
            "notes": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user

        if user:
            accounts = Account.objects.filter(
                user=user,
                is_active=True,
            ).order_by("account_type", "name")

            self.fields["from_account"].queryset = accounts
            self.fields["to_account"].queryset = accounts

    def clean_amount(self):
        amount = self.cleaned_data["amount"]

        if amount <= 0:
            raise forms.ValidationError("Amount must be greater than zero.")

        return amount

    def clean(self):
        cleaned_data = super().clean()

        from_account = cleaned_data.get("from_account")
        to_account = cleaned_data.get("to_account")

        if from_account and to_account and from_account.id == to_account.id:
            raise forms.ValidationError("Cannot transfer to the same account.")

        if self.user:
            if from_account and from_account.user_id != self.user.id:
                raise forms.ValidationError("Invalid source account.")

            if to_account and to_account.user_id != self.user.id:
                raise forms.ValidationError("Invalid destination account.")

        return cleaned_data


class DebtWebForm(forms.ModelForm):
    class Meta:
        model = Debt
        fields = [
            "name",
            "lender",
            "original_amount",
            "current_balance",
            "interest_rate",
            "minimum_payment",
            "due_day",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "lender": forms.TextInput(attrs={"class": "form-control"}),
            "original_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "current_balance": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "interest_rate": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "minimum_payment": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "due_day": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 31}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_original_amount(self):
        amount = self.cleaned_data["original_amount"]
        if amount <= 0:
            raise forms.ValidationError("Original amount must be greater than zero.")
        return amount

    def clean_current_balance(self):
        amount = self.cleaned_data["current_balance"]
        if amount < 0:
            raise forms.ValidationError("Current balance cannot be negative.")
        return amount


class DebtPaymentWebForm(forms.ModelForm):
    class Meta:
        model = DebtPayment
        fields = [
            "debt",
            "account",
            "amount",
            "principal_amount",
            "interest_amount",
            "payment_date",
            "notes",
        ]
        widgets = {
            "debt": forms.Select(attrs={"class": "form-select"}),
            "account": forms.Select(attrs={"class": "form-select"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "principal_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "interest_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "payment_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, user=None, debt=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        if user:
            self.fields["debt"].queryset = Debt.objects.filter(
                user=user,
                is_active=True,
            ).order_by("name")

            self.fields["account"].queryset = Account.objects.filter(
                user=user,
                is_active=True,
            ).exclude(
                account_type__in=["credit_card", "loan"]
            ).order_by("account_type", "name")

        if debt:
            self.fields["debt"].initial = debt

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Payment amount must be greater than zero.")
        return amount

    def clean_principal_amount(self):
        amount = self.cleaned_data["principal_amount"]
        if amount < 0:
            raise forms.ValidationError("Principal amount cannot be negative.")
        return amount

    def clean_interest_amount(self):
        amount = self.cleaned_data["interest_amount"]
        if amount < 0:
            raise forms.ValidationError("Interest amount cannot be negative.")
        return amount

    def clean(self):
        cleaned_data = super().clean()

        amount = cleaned_data.get("amount")
        principal = cleaned_data.get("principal_amount")
        interest = cleaned_data.get("interest_amount")
        debt = cleaned_data.get("debt")

        if amount is not None and principal is not None and interest is not None:
            if principal + interest != amount:
                raise forms.ValidationError(
                    "Principal amount plus interest amount must equal total payment amount."
                )

        if debt and principal is not None and principal > debt.current_balance:
            raise forms.ValidationError(
                "Principal payment cannot exceed the current debt balance."
            )

        return cleaned_data


class SavingsGoalWebForm(forms.ModelForm):
    class Meta:
        model = SavingsGoal
        fields = [
            "name",
            "target_amount",
            "current_amount",
            "target_date",
            "is_completed",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "target_amount": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01",
            }),
            "current_amount": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01",
            }),
            "target_date": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date",
            }),
            "is_completed": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
        }

    def clean_target_amount(self):
        amount = self.cleaned_data["target_amount"]

        if amount <= 0:
            raise forms.ValidationError("Target amount must be greater than zero.")

        return amount

    def clean_current_amount(self):
        amount = self.cleaned_data["current_amount"]

        if amount < 0:
            raise forms.ValidationError("Current amount cannot be negative.")

        return amount


class GoalContributionWebForm(forms.ModelForm):
    class Meta:
        model = GoalContribution
        fields = [
            "goal",
            "account",
            "amount",
            "contribution_date",
            "notes",
        ]
        widgets = {
            "goal": forms.Select(attrs={"class": "form-select"}),
            "account": forms.Select(attrs={"class": "form-select"}),
            "amount": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01",
            }),
            "contribution_date": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date",
            }),
            "notes": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
            }),
        }

    def __init__(self, *args, user=None, goal=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user

        if user:
            self.fields["goal"].queryset = SavingsGoal.objects.filter(
                user=user,
            ).order_by("is_completed", "target_date", "name")

            self.fields["account"].queryset = Account.objects.filter(
                user=user,
                is_active=True,
            ).exclude(
                account_type__in=["credit_card", "loan"]
            ).order_by("account_type", "name")

        if goal:
            self.fields["goal"].initial = goal

    def clean_amount(self):
        amount = self.cleaned_data["amount"]

        if amount <= 0:
            raise forms.ValidationError("Contribution amount must be greater than zero.")

        return amount

    def clean(self):
        cleaned_data = super().clean()

        goal = cleaned_data.get("goal")
        amount = cleaned_data.get("amount")

        if self.user:
            account = cleaned_data.get("account")

            if goal and goal.user_id != self.user.id:
                raise forms.ValidationError("Invalid goal.")

            if account and account.user_id != self.user.id:
                raise forms.ValidationError("Invalid account.")

        if goal and amount:
            remaining = goal.target_amount - goal.current_amount

            # This is optional. It prevents over-saving.
            if amount > remaining and not goal.is_completed:
                raise forms.ValidationError(
                    "Contribution exceeds the remaining target amount."
                )

        return cleaned_data


class CategoryWebForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = [
            "name",
            "category_type",
            "icon",
            "color",
            "is_default",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Example: Food, Salary, Utilities",
            }),
            "category_type": forms.Select(attrs={
                "class": "form-select",
            }),
            "icon": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Example: bi-cart, bi-cash, bi-lightning",
            }),
            "color": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Example: #4F8B5B",
            }),
            "is_default": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
            "is_active": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_name(self):
        name = self.cleaned_data["name"].strip()

        if not name:
            raise forms.ValidationError("Category name is required.")

        return name

    def clean(self):
        cleaned_data = super().clean()

        name = cleaned_data.get("name")
        category_type = cleaned_data.get("category_type")

        if self.user and name and category_type:
            queryset = Category.objects.filter(
                user=self.user,
                name__iexact=name,
                category_type=category_type,
            )

            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)

            if queryset.exists():
                raise forms.ValidationError(
                    "You already have a category with this name and type."
                )

        return cleaned_data