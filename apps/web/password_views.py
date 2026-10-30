"""Forgot-password pages. The email goes out through apps.accounts.password_reset."""
from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render

from apps.accounts import password_reset


class ForgotForm(forms.Form):
    email = forms.EmailField(label="Email address")


class NewPasswordForm(forms.Form):
    password = forms.CharField(label="New password", widget=forms.PasswordInput)
    confirm = forms.CharField(label="Repeat the new password", widget=forms.PasswordInput)

    def clean(self):
        data = super().clean()
        if data.get("password") and data.get("password") != data.get("confirm"):
            self.add_error("confirm", "The two passwords do not match.")
        return data


def forgot_password(request):
    form = ForgotForm(request.POST or None)
    sent = False
    if request.method == "POST" and form.is_valid():
        password_reset.request_reset(form.cleaned_data["email"])
        sent = True  # the same answer whether or not the address has an account
    return render(request, "auth/forgot.html", {"form": form, "sent": sent})


def reset_password(request, uid, token):
    user = password_reset.user_for(uid, token)
    if user is None:
        return render(request, "auth/reset_confirm.html", {"invalid": True}, status=400)
    form = NewPasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            password_reset.confirm_reset(uid, token, form.cleaned_data["password"])
        except ValidationError as exc:
            for message in exc.messages:
                form.add_error("password", message)
        else:
            messages.success(request, "Your password was changed. Sign in with the new one.")
            return redirect("web:login")
    return render(request, "auth/reset_confirm.html", {"form": form})
