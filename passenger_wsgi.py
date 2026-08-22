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
#     `settings/base.py` reads its secrets file through an absolute `BASE_DIR`,
#     so the configuration itself is already immune to the working directory.
#     This covers the import, which is not.
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config import environment  # noqa: E402

# ⚠️  **This file exists only on the production server, so the switch must say so.**
#
#     `config/environment.py` is committed, and its committed value is
#     `IS_PRODUCTION = False` — the right default for the machine the code is
#     written on and the wrong one for the machine it is served from. Uploading
#     without flipping it would boot `config.settings.dev` on the public domain:
#     `DEBUG` on, the debug toolbar exposing settings and SQL to every visitor,
#     and `devtools` installed — which carries `seed_dev`, a command that
#     creates accounts with a published password.
#
#     Failing to start is the cheap outcome. Serving that is not, and nothing
#     about it looks wrong from the outside until someone opens a stack trace.
if not environment.IS_PRODUCTION:
    raise RuntimeError(
        "passenger_wsgi.py refuses to boot with IS_PRODUCTION = False.\n"
        "This entry point runs on the production server only.\n"
        "Set IS_PRODUCTION = True in config/environment.py and touch tmp/restart.txt."
    )

# ⚠️  **Assignment, not `setdefault`** — unlike `config/wsgi.py`.
#
#     cPanel's interface has an environment-variable panel, and a value set
#     there outranks a default. `setdefault` would let one stray
#     `DJANGO_SETTINGS_MODULE=config.settings.dev` defeat the guard above.
#     There is no legitimate reason for this process to run any other settings
#     module, so it is not left as a preference.
os.environ["DJANGO_SETTINGS_MODULE"] = environment.SETTINGS_MODULE

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
