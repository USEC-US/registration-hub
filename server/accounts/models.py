from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models

from .managers import UserManager


class Institution(models.Model):
    class Source(models.TextChoices):
        CATALOGUE = "CATALOGUE", "Catalogue"
        CUSTOM = "CUSTOM", "Custom"

    class ReviewStatus(models.TextChoices):
        VERIFIED = "VERIFIED", "Verified"
        PENDING = "PENDING", "Pending"
        REJECTED = "REJECTED", "Rejected"

    value = models.CharField(max_length=32, blank=True)
    label = models.CharField(max_length=255)
    normalized_label = models.CharField(max_length=255, db_index=True)
    code = models.CharField(max_length=64, blank=True)
    short_name = models.CharField(max_length=255, blank=True)
    english_name = models.CharField(max_length=255, blank=True)
    type = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    source = models.CharField(max_length=16, choices=Source, default=Source.CUSTOM)
    review_status = models.CharField(
        max_length=16,
        choices=ReviewStatus,
        default=ReviewStatus.PENDING,
    )

    def save(self, *args, **kwargs):
        if not self.normalized_label:
            self.normalized_label = " ".join(self.label.split()).casefold()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.label


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    institution = models.ForeignKey(
        Institution,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="users",
    )
    student_id = models.CharField(max_length=128, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = [
        "first_name",
        "last_name",
    ]

    def clean(self):
        super().clean()
        if self.is_staff and not self.student_id:
            raise ValidationError({"student_id": "Staff users require a student ID."})
        if not self.is_staff and self.student_id:
            raise ValidationError(
                {"student_id": "Only staff users may have a student ID."}
            )

    def __str__(self) -> str:
        return self.email
