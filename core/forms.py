from django import forms
from django.contrib.auth.models import User


class SignupForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "autofocus": True}),
    )
    email = forms.EmailField(
        required=False, widget=forms.EmailInput(attrs={"class": "form-control"})
    )
    password = forms.CharField(
        min_length=8, widget=forms.PasswordInput(attrs={"class": "form-control"})
    )
    password_confirm = forms.CharField(
        min_length=8, widget=forms.PasswordInput(attrs={"class": "form-control"})
    )

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def clean(self):
        cleaned = super().clean()
        pw, pw2 = cleaned.get("password"), cleaned.get("password_confirm")
        if pw and pw2 and pw != pw2:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned


class LoginForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "autofocus": True}),
    )
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control"}))


class OTPForm(forms.Form):
    code = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "one-time-code",
                "inputmode": "numeric",
                "pattern": "[0-9]*",
                "class": "form-control form-control-lg text-center",
                "style": "letter-spacing: 0.5em; font-size: 1.5rem;",
                "autofocus": True,
            }
        ),
    )

    def clean_code(self):
        code = self.cleaned_data["code"]
        if not code.isdigit():
            raise forms.ValidationError("Code must be numeric.")
        return code
