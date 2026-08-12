"""
باكند المصادقة — بالبريد أو الهاتف.

يصلح ثلاث مشكلات في الأصل:
  1. لم يفحص `is_active` ⟵ الموقوفون كانوا يدخلون
  2. `get(email=...)` على حقل غير فريد ⟵ MultipleObjectsReturned
  3. لم يقاوم هجمات التوقيت ⟵ يكشف البريد المسجل من غيره
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
            # تجزئة وهمية بنفس التكلفة — تمنع تمييز البريد المسجل
            # عن غيره بقياس زمن الاستجابة
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            return None

        if not user.check_password(password):
            return None

        # يفحص is_active — ويُوسَّع أدناه ليشمل حالة الحساب
        if not self.user_can_authenticate(user):
            return None

        return user

    def user_can_authenticate(self, user):
        """
        يوسّع فحص Django ليشمل `AccountStatus`.

        الحساب الموقوف أو المحظور لا يدخل حتى لو كان `is_active=True`.
        """
        return getattr(user, "can_authenticate", False)


#: الاسم القديم — للتوافق حتى تحديث الإعدادات
EmailOrUsernameLogin = EmailOrPhoneBackend
