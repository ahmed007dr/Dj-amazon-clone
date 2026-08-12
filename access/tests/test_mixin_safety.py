"""
حارس بنيوي على `PolicyAwareQuerySetMixin`.

⚠️  خلفية هذا الملف — عيب حقيقي وقع أثناء بناء الكتالوج:

        class ProductListAPI(PublicCatalogMixin, ListAPIView):
            def get_queryset(self):          # ← تجاوز صامت
                return Product.objects.all()

    الـ view يعمل، والاختبارات الوظيفية تمر، والصفحة تُعرض —
    **وفلترة السياسات معطّلة تمامًا**. المنتجات المقيّدة تظهر
    للجميع بلا خطأ ولا تحذير.

    الحل بنيوي: `get_queryset` في الـ mixin نهائي عمليًا، والفلاتر
    تُكتب في `get_base_queryset`. وهذا الملف يمنع الانزلاق ثانيةً.
"""

import inspect

import pytest

from access.services import PolicyAwareQuerySetMixin


def _policy_aware_views():
    """كل views المشروع التي ترث الـ mixin."""
    from django.urls import get_resolver

    views = []

    def walk(patterns):
        for pattern in patterns:
            if hasattr(pattern, "url_patterns"):
                walk(pattern.url_patterns)
                continue

            callback = getattr(pattern, "callback", None)
            view_class = getattr(callback, "cls", None) or getattr(callback, "view_class", None)
            if view_class and issubclass(view_class, PolicyAwareQuerySetMixin):
                views.append(view_class)

    walk(get_resolver().url_patterns)
    return views


class TestMixinContract:
    def test_mixin_exposes_both_hooks(self):
        assert hasattr(PolicyAwareQuerySetMixin, "get_base_queryset")
        assert hasattr(PolicyAwareQuerySetMixin, "get_access_user")

    def test_filter_is_applied_in_get_queryset(self):
        source = inspect.getsource(PolicyAwareQuerySetMixin.get_queryset)
        assert "accessible_filter" in source
        assert "get_base_queryset" in source

    @pytest.mark.django_db
    def test_no_view_overrides_get_queryset(self):
        """
        ⚠️  **الحارس الأساسي.**

        أي view يرث الـ mixin ويعرّف `get_queryset` بنفسه يكسر
        الفلترة بصمت. الفلاتر مكانها `get_base_queryset`.
        """
        offenders = []

        for view_class in _policy_aware_views():
            for klass in view_class.__mro__:
                if klass is PolicyAwareQuerySetMixin:
                    break
                if "get_queryset" in klass.__dict__:
                    offenders.append(f"{view_class.__name__} (في {klass.__name__})")
                    break

        assert not offenders, (
            "views تتجاوز get_queryset فتعطّل فلترة السياسات بصمت — "
            f"انقل الفلاتر إلى get_base_queryset: {offenders}"
        )

    @pytest.mark.django_db
    def test_every_policy_aware_view_declares_policy_field(self):
        for view_class in _policy_aware_views():
            assert getattr(view_class, "policy_field", None), view_class.__name__
