"""
The dataset modules.

⚠️  Importing a module here **is** the registration — each one calls
    `registry.register` at module scope. So the import list below is the
    catalogue, and a module missing from it exports nothing while looking
    perfectly correct on disk.
"""

from __future__ import annotations


def load_all() -> None:
    """
    Import every dataset module, once.

    ⚠️  Called from `registry._load`, never at Django start-up. These modules
        import models from a dozen domains; pulling them in while the app
        registry is still populating raises `AppRegistryNotReady` — and it does
        so from whichever module happens to be first, which reads as that
        module's fault.
    """
    from reporting.export.datasets import (  # noqa: F401 — the import is the registration
        catalog,
        customers,
        finance,
        inventory,
        purchasing,
        sales,
    )
