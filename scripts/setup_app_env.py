"""Create local development secrets once; never print or overwrite them."""
from pathlib import Path
import os
import secrets

root = Path(__file__).resolve().parents[1]
target = root / ".env.app"
content = "\n".join(
    f"{line.split('=', 1)[0]}={secrets.token_urlsafe(32)}"
    if "=CHANGE_ME_" in line else line
    for line in (root / ".env.app.example").read_text().splitlines()
) + "\n"
try:
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    print("Keeping existing .env.app.")
else:
    with os.fdopen(descriptor, "w") as output:
        output.write(content)
    print("Created .env.app with private local development credentials.")
