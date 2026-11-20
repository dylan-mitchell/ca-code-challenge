"""Content-service settings. Authentication data belongs to the other service."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BASE_DIR.parent.parent
SECRET_KEY = os.environ.get("SECRET_KEY", "local-content-service-development-key")
DEBUG = os.environ.get("DEBUG", "false").lower() in {"1", "true"}
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
INSTALLED_APPS = ["django.contrib.staticfiles", "catalog"]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
}]
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": os.environ.get("DB_NAME", "reviews_main"),
    "USER": os.environ.get("DB_USER", "reviews_main"),
    "PASSWORD": os.environ.get("DB_PASSWORD", ""),
    "HOST": os.environ.get("DB_HOST", "localhost"),
    "PORT": os.environ.get("DB_PORT", "5432"),
    "CONN_MAX_AGE": 0,
}}
if os.environ.get("TEST_DB_NAME"):
    DATABASES["default"]["TEST"] = {"NAME": os.environ["TEST_DB_NAME"]}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = Path(os.environ.get("STATIC_ROOT", str(REPO_DIR / "staticfiles")))
FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST", str(REPO_DIR / "frontend" / "dist")))
STATICFILES_DIRS = [("frontend", FRONTEND_DIST)] if FRONTEND_DIST.exists() else []
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
VITE_DEV_SERVER_URL = os.environ.get("VITE_DEV_SERVER_URL", "")
AUTH_INTROSPECTION_URL = os.environ.get("AUTH_INTROSPECTION_URL", "http://auth:8000/api/tokens/introspect/")
INTROSPECTION_CLIENT_ID = os.environ.get("INTROSPECTION_CLIENT_ID", "main-app")
INTROSPECTION_CLIENT_SECRET = os.environ.get("INTROSPECTION_CLIENT_SECRET", "")
AUTH_TIMEOUT_SECONDS = float(os.environ.get("AUTH_TIMEOUT_SECONDS", "3"))
