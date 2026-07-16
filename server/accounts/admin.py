from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class AccountUserAdmin(UserAdmin):
    model = User
    ordering = ("email",)
    list_display = ("email", "gamer_tag", "school", "is_staff", "is_active")
    search_fields = ("email", "gamer_tag", "school")
    fieldsets = (
        (None, {"fields": ("email", "password")} ),
        ("Profile", {"fields": ("gamer_tag", "school")} ),
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
        ("Important dates", {"fields": ("last_login", "date_joined")} ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )
