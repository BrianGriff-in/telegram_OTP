import hashlib
import random
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class Profile(models.Model):
    """Extends the built-in User with Telegram linkage."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")

    # Telegram chat_id the bot should message. Null until the user links their account.
    telegram_chat_id = models.BigIntegerField(null=True, blank=True, unique=True)
    telegram_username = models.CharField(max_length=64, blank=True)

    # One-time token used in the t.me/<bot>?start=<token> deep link while linking.
    link_token = models.CharField(max_length=64, blank=True, unique=True, null=True)
    link_token_created_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Profile({self.user.username})"

    @property
    def telegram_linked(self):
        return self.telegram_chat_id is not None

    def generate_link_token(self):
        """Create a fresh one-time token for the Telegram deep link, valid 15 minutes."""
        self.link_token = secrets.token_urlsafe(24)
        self.link_token_created_at = timezone.now()
        self.save(update_fields=["link_token", "link_token_created_at"])
        return self.link_token

    def link_token_is_valid(self):
        if not self.link_token or not self.link_token_created_at:
            return False
        return timezone.now() - self.link_token_created_at < timedelta(minutes=15)


class OTP(models.Model):
    """A one-time password issued for a login attempt, delivered via Telegram."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otps")
    code_hash = models.CharField(max_length=64)  # sha256 hex digest, never store raw code
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    attempts = models.PositiveSmallIntegerField(default=0)  # failed verification attempts

    MAX_ATTEMPTS = 5

    class Meta:
        indexes = [models.Index(fields=["user", "is_used", "expires_at"])]

    def __str__(self):
        return f"OTP(user={self.user.username}, used={self.is_used})"

    @staticmethod
    def _hash(raw_code: str) -> str:
        return hashlib.sha256(raw_code.encode()).hexdigest()

    @classmethod
    def issue(cls, user: User) -> tuple["OTP", str]:
        """
        Create a new OTP for the user and return (otp_instance, raw_code).
        The raw_code is only ever available here, at creation time — send it
        immediately and never log or store it in plain form.
        """
        raw_code = f"{random.randint(0, 10 ** settings.OTP_LENGTH - 1):0{settings.OTP_LENGTH}d}"
        otp = cls.objects.create(
            user=user,
            code_hash=cls._hash(raw_code),
            expires_at=timezone.now() + timedelta(minutes=settings.OTP_VALID_MINUTES),
        )
        return otp, raw_code

    def verify(self, raw_code: str) -> bool:
        """Check a submitted code against this OTP. Mutates state (attempts/is_used)."""
        if self.is_used:
            return False
        if timezone.now() > self.expires_at:
            return False
        if self.attempts >= self.MAX_ATTEMPTS:
            return False

        self.attempts += 1
        is_correct = secrets.compare_digest(self.code_hash, self._hash(raw_code))

        if is_correct:
            self.is_used = True

        self.save(update_fields=["attempts", "is_used"])
        return is_correct

    @classmethod
    def latest_valid_for(cls, user: User):
        """Return the most recent, still-usable OTP for a user, if any."""
        return (
            cls.objects.filter(
                user=user, is_used=False, expires_at__gt=timezone.now()
            )
            .order_by("-created_at")
            .first()
        )
