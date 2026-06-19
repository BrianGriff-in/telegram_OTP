import json
import logging

from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import LoginForm, OTPForm, SignupForm
from .models import OTP, Profile
from . import telegram

logger = logging.getLogger(__name__)

PENDING_USER_SESSION_KEY = "otp_pending_user_id"


# ----------------------------- Signup / Login --------------------------------

def signup_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data["username"],
                email=form.cleaned_data.get("email", ""),
                password=form.cleaned_data["password"],
            )
            Profile.objects.create(user=user)
            auth_login(request, user)
            messages.success(request, "Account created. Now link your Telegram to enable OTP login.")
            return redirect("link_telegram")
    else:
        form = SignupForm()

    return render(request, "core/signup.html", {"form": form})


def login_view(request):
    """Step 1 of login: verify username/password, then send an OTP via Telegram."""
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]
            password = form.cleaned_data["password"]

            user = User.objects.filter(username__iexact=username).first()

            # Deliberately vague error: don't reveal whether the username exists.
            generic_error = "Invalid username or password."

            if user is None or not user.check_password(password):
                messages.error(request, generic_error)
            elif not hasattr(user, "profile") or not user.profile.telegram_linked:
                messages.error(
                    request,
                    "Your account isn't linked to Telegram yet, so we can't send you a code. "
                    "Please contact support.",
                )
            else:
                otp, raw_code = OTP.issue(user)
                result = telegram.send_otp(user.profile.telegram_chat_id, raw_code)
                if not result.get("ok"):
                    messages.error(
                        request,
                        "We couldn't send your code via Telegram. Please try again shortly.",
                    )
                else:
                    request.session[PENDING_USER_SESSION_KEY] = user.id
                    return redirect("verify_otp")
    else:
        form = LoginForm()

    return render(request, "core/login.html", {"form": form})


def verify_otp_view(request):
    """Step 2 of login: user enters the code that was sent to Telegram."""
    user_id = request.session.get(PENDING_USER_SESSION_KEY)
    if not user_id:
        return redirect("login")

    user = User.objects.filter(id=user_id).first()
    if not user:
        request.session.pop(PENDING_USER_SESSION_KEY, None)
        return redirect("login")

    if request.method == "POST":
        form = OTPForm(request.POST)
        if form.is_valid():
            otp = OTP.latest_valid_for(user)
            if otp is None:
                messages.error(request, "Your code has expired. Please log in again to get a new one.")
                request.session.pop(PENDING_USER_SESSION_KEY, None)
                return redirect("login")

            if otp.verify(form.cleaned_data["code"]):
                request.session.pop(PENDING_USER_SESSION_KEY, None)
                auth_login(request, user)
                messages.success(request, "Logged in successfully.")
                return redirect("dashboard")
            else:
                remaining = max(otp.MAX_ATTEMPTS - otp.attempts, 0)
                if remaining == 0:
                    messages.error(request, "Too many incorrect attempts. Please log in again.")
                    request.session.pop(PENDING_USER_SESSION_KEY, None)
                    return redirect("login")
                messages.error(request, f"Incorrect code. {remaining} attempt(s) remaining.")
    else:
        form = OTPForm()

    return render(request, "core/verify_otp.html", {"form": form})


@require_POST
def resend_otp_view(request):
    user_id = request.session.get(PENDING_USER_SESSION_KEY)
    if not user_id:
        return redirect("login")
    user = User.objects.filter(id=user_id).first()
    if not user or not hasattr(user, "profile") or not user.profile.telegram_linked:
        return redirect("login")

    otp, raw_code = OTP.issue(user)
    telegram.send_otp(user.profile.telegram_chat_id, raw_code)
    messages.info(request, "A new code has been sent to your Telegram.")
    return redirect("verify_otp")


def logout_view(request):
    auth_logout(request)
    return redirect("login")


# ----------------------------- Telegram linking --------------------------------

@login_required
def link_telegram_view(request):
    """Show the user a deep link / QR-style button to open the bot and link their chat."""
    profile = request.user.profile

    if profile.telegram_linked:
        return render(request, "core/link_telegram.html", {"already_linked": True})

    if not profile.link_token_is_valid():
        profile.generate_link_token()

    deep_link = f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={profile.link_token}"

    return render(
        request,
        "core/link_telegram.html",
        {"already_linked": False, "deep_link": deep_link},
    )


@login_required
def link_telegram_status_view(request):
    """Polled by the link page via JS to detect when linking completes."""
    linked = request.user.profile.telegram_linked
    return HttpResponse(json.dumps({"linked": linked}), content_type="application/json")


# ----------------------------- Telegram webhook --------------------------------

@csrf_exempt
@require_POST
def telegram_webhook_view(request, secret):
    """
    Telegram calls this URL for every bot update (e.g. when a user sends /start).
    The `secret` path segment guards against random callers hitting this endpoint.
    """
    if secret != settings.TELEGRAM_WEBHOOK_SECRET:
        return HttpResponseForbidden()

    try:
        update = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return HttpResponse(status=400)

    message = update.get("message")
    if not message:
        return HttpResponse(status=200)  # ignore non-message updates (edits, etc.)

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = message.get("text", "")

    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        token = parts[1].strip() if len(parts) > 1 else ""

        if not token:
            telegram.send_message(
                chat_id,
                "Welcome! Open the 'Link Telegram' link from the website to connect your account.",
            )
            return HttpResponse(status=200)

        profile = Profile.objects.filter(link_token=token).select_related("user").first()

        if profile is None or not profile.link_token_is_valid():
            telegram.send_message(
                chat_id,
                "That link has expired or is invalid. Please generate a new one from the website.",
            )
            return HttpResponse(status=200)

        if Profile.objects.filter(telegram_chat_id=chat_id).exclude(pk=profile.pk).exists():
            telegram.send_message(
                chat_id,
                "This Telegram account is already linked to a different user.",
            )
            return HttpResponse(status=200)

        profile.telegram_chat_id = chat_id
        profile.telegram_username = chat.get("username", "")
        profile.link_token = None
        profile.link_token_created_at = None
        profile.save()

        telegram.send_message(
            chat_id,
            f"✅ Telegram linked to account <b>{profile.user.username}</b>. "
            f"You'll receive your login codes here from now on.",
        )
    else:
        telegram.send_message(chat_id, "Send /start with your link token from the website to connect.")

    return HttpResponse(status=200)


# ----------------------------- Dashboard --------------------------------

@login_required
def dashboard_view(request):
    return render(request, "core/dashboard.html")
