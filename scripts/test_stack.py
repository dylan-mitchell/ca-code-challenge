"""Run all unit/contract checks with only Docker and Python on the host."""
import os
import subprocess
from local_settings import ROOT, configuration

COMPOSE = ["docker", "compose", "--env-file", str(ROOT / ".env.app")]

def run(*arguments, environment=None):
    subprocess.run([*COMPOSE, *arguments], cwd=ROOT, env=environment, check=True)

run("up", "-d", "--wait", "postgres")
run("build", "auth", "main")
run("run", "--rm", "--no-deps", "-v", f"{ROOT / 'packages/shared_auth'}:/package:ro",
    "auth", "python", "-m", "unittest", "discover", "-s", "/package/tests", "-v")
for service in ("auth", "main"):
    environment = os.environ.copy()
    environment["DB_PASSWORD"] = configuration()["POSTGRES_ADMIN_PASSWORD"]
    run("run", "--rm", "--no-deps", "-e", "DB_USER=postgres", "-e", "DB_PASSWORD",
        "-e", f"TEST_DB_NAME=test_{service}_db", service,
        "python", "manage.py", "test", "--noinput", environment=environment)
    run("run", "--rm", "--no-deps", service,
        "python", "manage.py", "makemigrations", "--check", "--dry-run")
run("run", "--rm", "--no-deps", "frontend", "sh", "-c",
    "npm ci && npm test && npm run build")
