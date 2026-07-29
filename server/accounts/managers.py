from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext_lazy as m


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(m("An email address is required."))
        if not extra_fields.get("first_name"):
            raise ValueError(m("First name is required."))
        if not extra_fields.get("last_name"):
            raise ValueError(m("Last name is required."))
        is_staff = extra_fields.get("is_staff", False)
        student_id = extra_fields.get("student_id", "")
        if is_staff and not student_id:
            raise ValueError(m("Staff users require a student ID."))
        if not is_staff and student_id:
            raise ValueError(m("Only staff users may have a student ID."))

        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.clean()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("student_id", "system")
        if extra_fields["is_staff"] is not True:
            raise ValueError("A superuser must have is_staff=True.")
        if extra_fields["is_superuser"] is not True:
            raise ValueError("A superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)
