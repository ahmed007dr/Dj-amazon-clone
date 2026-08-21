"""
Passenger entry point — cPanel «Setup Python App».

    Application root         /home/medboxne/med-box
    Application startup file passenger_wsgi.py
    Application Entry point  application

⚠️  **Restarting is a file touch, not a service command.**

        touch /home/medboxne/med-box/tmp/restart.txt

    Shared hosting gives no `systemctl`, and Passenger keeps the old process
    alive until that file's mtime changes. Uploading new code without it leaves
    the previous code answering every request — which is the whole of "I
    deployed and nothing changed" on cPanel. The `tmp/` directory must exist.

⚠️  And this file replaces `gunicorn`, it does not run beside it.

    Passenger imports `application` from here and drives it in-process. There is
    no port to bind and no process to supervise; `config/wsgi.py` stays as it is
    for any host that speaks plain WSGI.
"""

import os
import sys
from pathlib import Path

#: The application root — the directory this file sits in.
BASE_DIR = Path(__file__).resolve().parent

# ⚠️  Passenger's working directory is not guaranteed to be the application root,
#     and `config` is imported by name. Without this line the boot fails with
#     `ModuleNotFoundError: No module named 'config'` — a message that points at
#     the project rather than at the path, so it is debugged in the wrong place.
#
#     `settings/base.py` reads `.env` and `.env.public` through an absolute
#     `BASE_DIR`, so the configuration itself is already immune to the working
#     directory. This covers the import, which is not.
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# ⚠️  **Assignment, not `setdefault`** — unlike `config/wsgi.py`.
#
#     cPanel's interface has an environment-variable panel, and a value set
#     there outranks a default. `setdefault` would let one stray
#     `DJANGO_SETTINGS_MODULE=config.settings.dev` boot the development
#     configuration on the public domain: the debug toolbar exposing settings
#     and SQL to every visitor, and `devtools` installed — which carries
#     `seed_dev`, a command that creates accounts with a published password.
#
#     There is no legitimate reason for this process to run any other settings
#     module, so it is not left as a preference.
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
