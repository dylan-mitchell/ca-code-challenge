"""Run a management command with local development environment settings."""
import argparse
import subprocess
from local_settings import ROOT, service_environment

parser = argparse.ArgumentParser()
parser.add_argument("service", choices=("auth", "main"))
parser.add_argument("--test", action="store_true", help="Use database-creation credentials for tests only")
arguments, command = parser.parse_known_args()
if not command:
    parser.error("Provide a Django management command")
raise SystemExit(subprocess.call(
    [str(ROOT / ".venv/bin/python"), "manage.py", *command],
    cwd=ROOT / "services" / arguments.service,
    env=service_environment(arguments.service, testing=arguments.test),
))
