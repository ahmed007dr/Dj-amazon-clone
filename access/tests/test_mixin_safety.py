"""
Structural guard on `PolicyAwareQuerySetMixin`.

⚠️  The background to this file — a real defect that occurred while building the catalogue:

        class ProductListAPI(PublicCatalogMixin, ListAPIView):
            def get_queryset(self):          # ← a silent override
                return Product.objects.all()

    The view works, the functional tests pass, the page renders —
    **and policy filtering is entirely disabled**. Restricted products show up
    for everyone with no error and no warning.

    The fix is structural: `get_queryset` in the mixin is effectively final, and
    filters are written in `get_base_queryset`. This file prevents the slip from
    happening again.
"""

import inspect

import pytest

from access.services import PolicyAwareQuerySetMixin


def _policy_aware_views():
    """Every view in the project that inherits the mixin."""
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
        ⚠️  **The primary guard.**

        Any view that inherits the mixin and defines its own `get_queryset`
        breaks the filtering silently. Filters belong in `get_base_queryset`.
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
