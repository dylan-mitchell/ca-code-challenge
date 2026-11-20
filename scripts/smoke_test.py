"""Exercise running services, then restore the edited brand and remove the test user.

Requires an imported local stack. Temporarily stops auth to verify fail-closed
behavior and public availability. Run while nobody else is editing the demo.
"""
import base64
import json
import secrets
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from local_settings import ROOT, configuration

CONFIG = configuration()
COMPOSE = ["docker", "compose", "--env-file", str(ROOT / ".env.app")]
MAIN = f"http://127.0.0.1:{CONFIG['MAIN_PORT']}"
AUTH = f"http://127.0.0.1:{CONFIG['AUTH_PORT']}"

def compose(*arguments):
    subprocess.run([*COMPOSE, *arguments], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)

def shell(service, code, data):
    output = subprocess.check_output(
        [*COMPOSE, "exec", "-T", service, "python", "manage.py", "shell", "--no-imports", "-c",
         "import json,sys; data=json.load(sys.stdin); " + code],
        cwd=ROOT, input=json.dumps(data).encode(),
    )
    return output.decode().strip()

def request(base, path, method="GET", data=None, token=None, headers=None):
    headers = dict(headers or {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/json"
    call = Request(base + path, method=method, headers=headers,
                   data=json.dumps(data).encode() if data is not None else None)
    try:
        response = urlopen(call, timeout=8)
    except HTTPError as error:
        response = error
    with response:
        body = response.read()
        return response.status, json.loads(body) if "application/json" in response.headers.get("Content-Type", "") else body

def expect(status, result):
    actual, body = result
    assert actual == status, f"Expected HTTP {status}, got {actual}"
    return body

def main():
    username = "smoke_" + uuid4().hex[:16]
    password = secrets.token_urlsafe(32)
    brand = next(item for item in expect(200, request(MAIN, "/api/brands/"))["results"] if item["slug"] == "acme-insurance")
    assert brand["average_rating"] == 3.92 and brand["review_count"] == 12
    original = {"id": brand["id"], "short_description": brand["short_description"],
                "top_review_id": brand["top_review"]["id"] if brand["top_review"] else None}
    path = "/api/brands/acme-insurance/"
    auth_stopped = False
    try:
        shell("auth", "from accounts.models import User; User.objects.create_user(username=data['username'],password=data['password'],role='editor')",
              {"username": username, "password": password})
        token = expect(200, request(AUTH, "/api/login/", "POST", {"username": username, "password": password}))["access_token"]
        expect(400, request(AUTH, "/api/login/", "POST", {"username": username, "password": "incorrect"}))
        expect(401, request(AUTH, "/api/tokens/introspect/", "POST", {"token": token}))
        credential = base64.b64encode(f"{CONFIG['INTROSPECTION_CLIENT_ID']}:{CONFIG['INTROSPECTION_CLIENT_SECRET']}".encode()).decode()
        introspected = expect(200, request(AUTH, "/api/tokens/introspect/", "POST", {"token": token},
                                             headers={"Authorization": f"Basic {credential}"}))
        assert introspected["active"] and introspected["user"]["role"] == "editor"
        review = shell("main", "from catalog.models import Review; print(Review.objects.filter(brand__slug='acme-insurance').first().pk)", {})
        edited = expect(200, request(MAIN, path, "PATCH", {"short_description": "Smoke test description", "top_review_id": review}, token))
        assert edited["top_review"]["id"] == review
        expect(400, request(MAIN, path, "PATCH", {"short_description": "Must not persist", "top_review_id": "9223372036854775807"}, token))
        current = next(item for item in expect(200, request(MAIN, "/api/brands/"))["results"] if item["id"] == brand["id"])
        assert current["short_description"] == "Smoke test description"
        shell("auth", "from accounts.models import User; from accounts.operations import change_role; change_role(User.objects.get(username=data['username']),'reader')", {"username": username})
        expect(403, request(MAIN, path, "PATCH", {"short_description": "Must not persist"}, token))
        shell("auth", "from accounts.models import User; from accounts.operations import change_role; change_role(User.objects.get(username=data['username']),'editor')", {"username": username})
        expect(200, request(MAIN, path, "PATCH", {"top_review_id": None}, token))
        shell("auth", "from accounts.models import User; from accounts.operations import revoke_all_tokens; revoke_all_tokens(User.objects.get(username=data['username']))", {"username": username})
        expect(401, request(MAIN, path, "PATCH", {"short_description": "Must not persist"}, token))
        token = expect(200, request(AUTH, "/api/login/", "POST", {"username": username, "password": password}))["access_token"]
        auth_stopped = True
        compose("stop", "auth")
        expect(503, request(MAIN, path, "PATCH", {"short_description": "Must not persist"}, token))
        for public_path in ("/api/brands/", "/", "/brand/", "/brand/acme-insurance/", "/review/umbrella-policy-was-easy-to-add/"):
            expect(200, request(MAIN, public_path))
        current = next(item for item in expect(200, request(MAIN, "/api/brands/"))["results"] if item["id"] == brand["id"])
        assert current["short_description"] == "Smoke test description" and current["top_review"] is None
        print("PASS: derived averages, login, introspection, editor selection, atomic PATCH, same-token demotion, revocation, auth outage and public pages.")
    finally:
        failures = []
        try:
            shell("main", "from catalog.models import Brand; Brand.objects.filter(pk=data['id']).update(short_description=data['short_description'],top_review_id=data['top_review_id'])", original)
        except Exception as error:
            failures.append(f"Brand restoration failed: {type(error).__name__}")
        try:
            if auth_stopped:
                compose("up", "-d", "auth")
                for _ in range(30):
                    try:
                        request(AUTH, "/api/login/", "POST", {})
                        break
                    except OSError:
                        time.sleep(0.2)
                else:
                    raise RuntimeError("Auth did not become ready")
        except Exception as error:
            failures.append(f"Auth restart failed: {type(error).__name__}")
        try:
            shell("auth", "from accounts.models import User; User.objects.filter(username=data['username']).delete()", {"username": username})
        except Exception as error:
            failures.append(f"Temporary account cleanup failed: {type(error).__name__}")
        if failures:
            raise RuntimeError("; ".join(failures))
        print("Restored the original brand and removed the temporary auth account.")

if __name__ == "__main__":
    main()
