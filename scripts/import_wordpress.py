"""Coordinate two independent transactions using a temporary identity map."""
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "--env-file", str(ROOT / ".env.app")]

def run(*arguments):
    subprocess.run([*COMPOSE, *arguments], cwd=ROOT, check=True)

def main():
    run("--profile", "import", "up", "-d", "--wait", "postgres", "import-source")
    directory = ROOT / ".import-handoff"
    directory.mkdir(mode=0o700, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="run-", dir=directory) as temporary:
        mapping = Path(temporary) / "identities.json"
        container_path = f"/import-handoff/{mapping.parent.name}/{mapping.name}"
        run("run", "--rm", "--no-deps", "auth", "python", "manage.py",
            "import_wordpress_users", "--mapping-output", container_path)
        if not mapping.is_file():
            raise RuntimeError("Auth import did not produce an identity mapping.")
        run("run", "--rm", "--no-deps", "main", "python", "manage.py",
            "import_wordpress_content", "--auth-map", container_path)
    print("Both import phases completed; temporary identity mapping removed.")

if __name__ == "__main__":
    try:
        main()
    except (subprocess.CalledProcessError, RuntimeError) as error:
        print(f"Import stopped: {error}. Completed phases remain committed; rerun safely.")
        raise SystemExit(1) from error
