"""The content service's HTTP adapter for the shared verification function."""
import base64
import json
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from review_auth import AuthUnavailable, parse_introspection


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = build_opener(_NoRedirect)


def introspection_lookup(token):
    if not settings.INTROSPECTION_CLIENT_SECRET:
        raise AuthUnavailable("Introspection service credential is not configured.")
    credential = base64.b64encode(
        f"{settings.INTROSPECTION_CLIENT_ID}:{settings.INTROSPECTION_CLIENT_SECRET}".encode()
    ).decode("ascii")
    request = Request(
        settings.AUTH_INTROSPECTION_URL,
        data=json.dumps({"token": token}).encode(), method="POST",
        headers={"Authorization": f"Basic {credential}", "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with _opener.open(request, timeout=settings.AUTH_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise AuthUnavailable("Auth could not validate the token.")
            body = response.read(65537)
            if len(body) > 65536:
                raise AuthUnavailable("Unusable introspection response.")
            return parse_introspection(json.loads(body))
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise AuthUnavailable("Auth could not validate the token.") from exc
