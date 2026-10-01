from datetime import date

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password

from apps.accounts.models import BankAccount, Profile
from apps.accounts.phone import normalize_phone
from apps.billpay import catalog
from apps.groups.models import Interval, Purpose

from .banks import BANK_NAMES, BANKS

User = get_user_model()


class LoginForm(forms.Form):
    identifier = forms.CharField(label="Email or phone number", widget=forms.TextInput(attrs={"autocomplete": "username", "autofocus": True}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.user = None

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        self.user = authenticate(self.request, username=cleaned["identifier"], password=cleaned["password"])
        if self.user is None:
            raise forms.ValidationError("That email/phone and password don't match. Check them and try again.")
        return cleaned


class RegisterForm(forms.Form):
    full_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"autocomplete": "name", "autofocus": True}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    phone_number = forms.CharField(
        max_length=20, required=False, label="Phone number (optional)",
        help_text="Lets friends invite you by phone, and lets you sign in with it.",
        widget=forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel", "placeholder": "0803 000 0000"}),
    )
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}), help_text="At least 8 characters.")

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_phone_number(self):
        phone = normalize_phone(self.cleaned_data.get("phone_number", ""))
        if phone and Profile.objects.filter(phone_number=phone).exists():
            raise forms.ValidationError("This phone number is already registered.")
        return phone or None

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password


class GroupForm(forms.Form):
    """Create/edit a group. Member rows are read separately from POST (repeatable inputs)."""

    name = forms.CharField(max_length=120, label="Group name", widget=forms.TextInput(attrs={"placeholder": "e.g. Flat 4B rent"}))
    description = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Note for members (optional)")
    purpose = forms.ChoiceField(choices=Purpose.choices)
    target_amount = forms.DecimalField(max_digits=14, decimal_places=2, min_value=1, label="Target amount (₦)")
    due_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    is_recurring = forms.BooleanField(required=False, label="Repeat this group")
    recurrence_interval = forms.ChoiceField(choices=[("", "—")] + Interval.choices, required=False, label="Repeats")
    allow_partial_payout = forms.BooleanField(required=False, label="Allow me to pay out before the target is reached")
    payout_type = forms.ChoiceField(choices=[("bank_transfer", "Bank transfer"), ("bill_payment", "Pay a bill")], widget=forms.RadioSelect)

    bill_service_id = forms.ChoiceField(choices=[("", "Choose your electricity company")] + catalog.choices("electricity"), required=False, label="Electricity company")
    bill_variation = forms.ChoiceField(choices=[("prepaid", "Prepaid"), ("postpaid", "Postpaid")], required=False, label="Meter type")
    bill_customer_id = forms.CharField(max_length=40, required=False, label="Meter number")

    recipient_bank_code = forms.ChoiceField(choices=[("", "Choose a bank")] + BANKS, required=False, label="Bank")
    recipient_account_number = forms.CharField(max_length=10, required=False, label="Account number", widget=forms.TextInput(attrs={"inputmode": "numeric", "maxlength": 10}))
    recipient_account_name = forms.CharField(max_length=150, required=False, label="Account name")

    def __init__(self, *args, editing=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.editing = editing
        if editing:
            # Money-bearing structure is locked once created; only these can change.
            self.fields["recipient_account_number"].help_text = "Leave blank to keep the saved account."
            self.fields["payout_type"].disabled = True
            self.fields["payout_type"].required = False

    def clean_due_date(self):
        value = self.cleaned_data["due_date"]
        if not self.editing and value < date.today():
            raise forms.ValidationError("The due date can't be in the past.")
        return value

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        if data.get("is_recurring") and not data.get("recurrence_interval"):
            self.add_error("recurrence_interval", "Choose how often this repeats.")
        payout_type = self.editing.payout_type if self.editing else data.get("payout_type")
        if payout_type == "bill_payment":
            if not data.get("bill_service_id"):
                self.add_error("bill_service_id", "Choose the electricity company.")
            if not (data.get("bill_customer_id") or "").isdigit():
                self.add_error("bill_customer_id", "Enter the meter number (digits only).")
        else:
            if not data.get("recipient_bank_code"):
                self.add_error("recipient_bank_code", "Choose the recipient's bank.")
            number = data.get("recipient_account_number", "")
            if not (self.editing and not number):
                if not (number.isdigit() and len(number) == 10):
                    self.add_error("recipient_account_number", "Account numbers are 10 digits.")
            if not data.get("recipient_account_name"):
                self.add_error("recipient_account_name", "Enter the name on the account.")
        return data

    def service_fields(self):
        """Cleaned data shaped for services.create_group / update_group."""
        d = self.cleaned_data
        fields = {
            "name": d["name"], "description": d.get("description", ""), "purpose": d["purpose"],
            "target_amount": d["target_amount"], "due_date": d["due_date"],
            "is_recurring": d.get("is_recurring", False),
            "recurrence_interval": d.get("recurrence_interval") or None,
            "allow_partial_payout": d.get("allow_partial_payout", False),
        }
        if not d.get("is_recurring"):
            fields["recurrence_interval"] = None
        payout_type = self.editing.payout_type if self.editing else d["payout_type"]
        if not self.editing:
            fields["payout_type"] = payout_type
        if payout_type == "bill_payment":
            fields.update(bill_service_id=d["bill_service_id"], bill_customer_id=d["bill_customer_id"],
                          bill_variation=d.get("bill_variation") or "prepaid")
        else:
            fields.update(recipient_bank_code=d["recipient_bank_code"],
                          recipient_bank_name=BANK_NAMES.get(d["recipient_bank_code"], ""),
                          recipient_account_name=d["recipient_account_name"])
            if d.get("recipient_account_number"):
                fields["recipient_account_number"] = d["recipient_account_number"]
        return fields


class ContactForm(forms.Form):
    name = forms.CharField(max_length=120, widget=forms.TextInput(attrs={"autocomplete": "name"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "email"}), help_text="So we can reply to you.")
    topic = forms.ChoiceField(choices=[], label="What is it about?")
    reference = forms.CharField(max_length=60, required=False, label="Group name or payment reference (optional)")
    message = forms.CharField(max_length=4000, widget=forms.Textarea(attrs={"rows": 6}), help_text="Tell us what happened, in your own words. Never send your password or a full card number.")
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}), label="Leave this empty")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import ContactMessage

        self.fields["topic"].choices = ContactMessage.Topic.choices

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("Spam detected.")  # a hidden field only bots fill in
        return ""


class InviteForm(forms.Form):
    identifier = forms.CharField(label="Email or phone number")
    contribution_share = forms.DecimalField(max_digits=14, decimal_places=2, min_value=1, required=False, label="Custom share (₦)")


class ProfileForm(forms.Form):
    full_name = forms.CharField(max_length=150)
    phone_number = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={"inputmode": "tel"}))

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_phone_number(self):
        phone = normalize_phone(self.cleaned_data.get("phone_number", ""))
        if phone and Profile.objects.filter(phone_number=phone).exclude(user=self.user).exists():
            raise forms.ValidationError("This phone number belongs to another account.")
        return phone or None


class BankAccountForm(forms.ModelForm):
    bank_code = forms.ChoiceField(choices=[("", "Choose a bank")] + BANKS, label="Bank")
    account_number = forms.CharField(max_length=10, min_length=10, widget=forms.TextInput(attrs={"inputmode": "numeric"}))

    class Meta:
        model = BankAccount
        fields = ("bank_code", "account_number", "account_name")

    def clean_account_number(self):
        value = self.cleaned_data["account_number"]
        if not value.isdigit():
            raise forms.ValidationError("Account numbers are 10 digits.")
        return value

    def save(self, user):
        account = BankAccount.objects.filter(user=user).first() or BankAccount(user=user)
        account.bank_code = self.cleaned_data["bank_code"]
        account.bank_name = BANK_NAMES.get(account.bank_code, "")
        account.account_number = self.cleaned_data["account_number"]
        account.account_name = self.cleaned_data["account_name"]
        account.save()
        return account
