"""Load development credentials for host-side commands without shell expansion."""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]

def configuration():
    return dict(
        line.split("=", 1) for line in (ROOT / ".env.app").read_text().splitlines()
        if line and not line.startswith("#")
    )

def service_environment(service, *, testing=False):
    config = configuration()
    environment = os.environ.copy()
    environment.update({
        "SECRET_KEY": config[f"{service.upper()}_DJANGO_SECRET_KEY"],
        "DEBUG": config["APP_DEBUG"],
        "ALLOWED_HOSTS": config["APP_ALLOWED_HOSTS"],
        "DB_HOST": "127.0.0.1", "DB_PORT": config["POSTGRES_PORT"],
        "DB_NAME": f"{service}_db", "DB_USER": f"{service}_app",
        "DB_PASSWORD": config[f"{service.upper()}_DB_PASSWORD"],
        "TEST_DB_NAME": f"test_{service}_db",
        "SOURCE_DB_HOST": "127.0.0.1", "SOURCE_DB_PORT": config["SOURCE_PORT"],
        "SOURCE_DB_NAME": "wp", "SOURCE_DB_USER": "import_reader",
        "SOURCE_DB_PASSWORD": config["SOURCE_DB_PASSWORD"],
        "INTROSPECTION_CLIENT_ID": config["INTROSPECTION_CLIENT_ID"],
        "INTROSPECTION_CLIENT_SECRET": config["INTROSPECTION_CLIENT_SECRET"],
        "AUTH_INTROSPECTION_URL": f"http://127.0.0.1:{config['AUTH_PORT']}/api/tokens/introspect/",
        "AUTH_TIMEOUT_SECONDS": "3",
        "FRONTEND_DIST": str(ROOT / "frontend" / "dist"),
        "VITE_DEV_SERVER_URL": config["VITE_DEV_SERVER_URL"],
    })
    if service == "auth":
        environment["AUTH_IMPORT_PASSWORD"] = config["AUTH_IMPORT_PASSWORD"]
    else:
        environment.pop("AUTH_IMPORT_PASSWORD", None)
    if testing:
        environment.update(DB_USER="postgres", DB_PASSWORD=config["POSTGRES_ADMIN_PASSWORD"])
    return environment
