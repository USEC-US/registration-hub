from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    school = models.CharField(max_length=128, blank=True)
    student_id = models.CharField(max_length=128, blank=True) # Only useful if it's staff

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = [
        "first_name",
        "last_name",
        "school"
    ]

    def __str__(self) -> str:
        return self.email
