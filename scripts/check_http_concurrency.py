"""Read-only check that incomplete connections do not stall the local services."""
from contextlib import ExitStack
from http.client import HTTPConnection
import socket
import time

from local_settings import configuration


def request(port, path, expected_status):
    connection = HTTPConnection("127.0.0.1", port, timeout=3)
    started = time.monotonic()
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        response.read()
        if response.status != expected_status:
            raise RuntimeError(f"{path}: expected {expected_status}, got {response.status}")
        return time.monotonic() - started
    finally:
        connection.close()


def check_endpoint(service, port, path, expected_status):
    request(port, path, expected_status)
    for mode in ("idle", "incomplete headers"):
        with ExitStack() as connections:
            for _ in range(2):
                connection = connections.enter_context(
                    socket.create_connection(("127.0.0.1", port), timeout=3)
                )
                if mode == "incomplete headers":
                    connection.sendall(
                        f"GET {path} HTTP/1.1\r\nHost: localhost\r\n".encode("ascii")
                    )
            # Give the server time to accept the sockets before sending real requests.
            time.sleep(0.2)
            elapsed = [request(port, path, expected_status) for _ in range(3)]
            print(f"{service}: {mode}; 3 requests passed, slowest {max(elapsed):.3f}s")


def main():
    config = configuration()
    check_endpoint("main", int(config["MAIN_PORT"]), "/api/brands/", 200)
    # Login is POST-only; a GET exercises HTTP handling without creating tokens.
    check_endpoint("auth", int(config["AUTH_PORT"]), "/api/login/", 405)


if __name__ == "__main__":
    main()
