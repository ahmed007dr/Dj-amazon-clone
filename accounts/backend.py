"""
Authentication backend — by email or phone.

It fixes three problems in the original:
  1. it never checked `is_active` ⟵ suspended users could log in
  2. `get(email=...)` on a non-unique field ⟵ MultipleObjectsReturned
  3. it did not resist timing attacks ⟵ revealing which emails are registered
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

UserModel = get_user_model()


class EmailOrPhoneBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = username or kwargs.get(UserModel.USERNAME_FIELD)
        if not identifier or not password:
            return None

        try:
            user = UserModel.objects.get(Q(email__iexact=identifier) | Q(phone=identifier))
        except UserModel.DoesNotExist:
            # A dummy hash of the same cost — stops a registered email being told
            # apart from an unregistered one by measuring response time
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            return None

        if not user.check_password(password):
            return None

        # Checks is_active — and is extended below to cover the account status
        if not self.user_can_authenticate(user):
            return None

        return user

    def user_can_authenticate(self, user):
        """
        Extends Django's check to cover `AccountStatus`.

        A suspended or banned account cannot log in even with `is_active=True`.
        """
        return getattr(user, "can_authenticate", False)


#: The legacy name — kept for compatibility until the settings are updated
EmailOrUsernameLogin = EmailOrPhoneBackend
