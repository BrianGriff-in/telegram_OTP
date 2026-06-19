from django.contrib import admin

from .models import OTP, Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "telegram_chat_id", "telegram_username", "telegram_linked")
    search_fields = ("user__username", "telegram_username")


@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "expires_at", "is_used", "attempts")
    list_filter = ("is_used",)
    readonly_fields = ("code_hash",)
