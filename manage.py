#!/usr/bin/env python
import os
import sys
from pathlib import Path


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "creditrade.settings")
    env_local = Path(__file__).resolve().parent / ".env.local"
    env_default = Path(__file__).resolve().parent / ".env"
    try:
        from dotenv import load_dotenv

        if env_local.exists():
            load_dotenv(env_local)
        elif env_default.exists():
            load_dotenv(env_default)
    except ImportError:
        pass

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "No se pudo importar Django. Instala las dependencias con: "
            "pip install -r requirements.txt"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
