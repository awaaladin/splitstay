from django.db import connection
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import BankAccount
from apps.accounts.phone import normalize_phone
from apps.testing import make_user


class AuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_then_login_with_email_and_phone(self):
        res = self.client.post("/api/v1/auth/register/", {
            "email": "ada@example.com", "password": "Str0ng-pass!", "full_name": "Ada Obi",
            "phone_number": "0803 123 4567",
        }, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertIn("access", res.data)
        for identifier in ("ada@example.com", "ADA@example.com", "08031234567", "+2348031234567"):
            login = self.client.post("/api/v1/auth/token/", {"identifier": identifier, "password": "Str0ng-pass!"}, format="json")
            self.assertEqual(login.status_code, 200, identifier)
        bad = self.client.post("/api/v1/auth/token/", {"identifier": "ada@example.com", "password": "nope"}, format="json")
        self.assertEqual(bad.status_code, 400)

    def test_access_token_authenticates_api_calls(self):
        make_user("Tolu", email="tolu@example.com", password="Str0ng-pass!")
        token = self.client.post("/api/v1/auth/token/", {"identifier": "tolu@example.com", "password": "Str0ng-pass!"}, format="json").data["access"]
        self.assertEqual(self.client.get("/api/v1/groups/").status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(self.client.get("/api/v1/groups/").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/auth/me/").data["email"], "tolu@example.com")

    def test_duplicate_phone_rejected(self):
        make_user("A", phone="+2348031234567")
        res = self.client.post("/api/v1/auth/register/", {
            "email": "b@example.com", "password": "Str0ng-pass!", "full_name": "B", "phone_number": "08031234567",
        }, format="json")
        self.assertEqual(res.status_code, 400)

    def test_phone_normalisation(self):
        self.assertEqual(normalize_phone("0803 123 4567"), "+2348031234567")
        self.assertEqual(normalize_phone("2348031234567"), "+2348031234567")
        self.assertEqual(normalize_phone("8031234567"), "+2348031234567")


class BankAccountEncryptionTests(TestCase):
    def test_account_number_is_encrypted_at_rest(self):
        user = make_user("Bank User", password="Str0ng-pass!")
        account = BankAccount(user=user, bank_code="058", bank_name="GTBank", account_name="Bank User",
                              account_number="0123456789")
        account.save()
        with connection.cursor() as cursor:
            cursor.execute("SELECT account_number FROM accounts_bankaccount WHERE id = %s", [account.pk])
            raw = cursor.fetchone()[0]
        self.assertNotIn("0123456789", raw)
        account.refresh_from_db()
        self.assertEqual(account.account_number, "0123456789")
        self.assertEqual(account.masked_number, "******6789")

    def test_api_never_returns_full_account_number(self):
        user = make_user("Bank User", password="Str0ng-pass!")
        client = APIClient()
        client.force_authenticate(user)
        res = client.put("/api/v1/auth/me/bank-account/", {
            "bank_code": "058", "bank_name": "GTBank", "account_name": "Bank User", "account_number": "0123456789",
        }, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("0123456789", str(res.data))
        self.assertEqual(res.data["masked_number"], "******6789")
