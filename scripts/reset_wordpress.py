"""Explicit legacy WordPress reset; never remove Django or import-source data."""
import json
import subprocess
from local_settings import ROOT

compose = ["docker", "compose", "--env-file", str(ROOT / ".env.app")]
config = json.loads(subprocess.check_output([*compose, "config", "--format", "json"], cwd=ROOT))
subprocess.run([*compose, "rm", "--stop", "--force", "db", "wordpress", "phpmyadmin", "wpcli"], cwd=ROOT, check=True)
volumes = [config["volumes"][name]["name"] for name in ("db_data", "wp_files")]
for volume in volumes:
    if subprocess.run(["docker", "volume", "inspect", volume], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        subprocess.run(["docker", "volume", "rm", volume], check=True)
print("Legacy WordPress data reset. Run make up to restore it from db/dump.sql.")
