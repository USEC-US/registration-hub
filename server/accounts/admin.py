from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class AccountUserAdmin(UserAdmin):
    model = User
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "school", "student_id", "is_staff", "is_active")
    search_fields = ("email", "first_name", "last_name", "school", "student_id")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Personal info",
            {"fields": ("first_name", "last_name", "school")},
        ),
        (
            "Staff reference",
            {
                "fields": ("student_id",),
                "description": "Internal tracking only — not exposed to participants.",
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "first_name", "last_name", "password1", "password2"),
            },
        ),
    )
