"""Start a loopback-only pgAdmin viewer with separate read-only DB accounts."""
import json
import os
import secrets
import subprocess

from local_settings import ROOT, configuration

COMPOSE = ["docker", "compose", "--env-file", str(ROOT / ".env.app")]

def run(*arguments, **options):
    return subprocess.run([*COMPOSE, *arguments], cwd=ROOT, check=True, **options)

def main():
    private = ROOT / ".pgadmin"
    private.mkdir(mode=0o700, exist_ok=True)
    credentials = private / "readers.json"
    if credentials.exists():
        passwords = json.loads(credentials.read_text())
    else:
        passwords = {service: secrets.token_urlsafe(32) for service in ("main", "auth")}
        with os.fdopen(os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as output:
            json.dump(passwords, output)

    run("up", "-d", "--wait", "postgres")
    for service in ("main", "auth"):
        # Names are fixed application identifiers. psql safely quotes the secret
        # from the environment; it never appears in command-line arguments.
        environment = os.environ.copy()
        environment["READER_PASSWORD"] = passwords[service]
        sql = f"""
\\getenv reader_password READER_PASSWORD
BEGIN;
SELECT 'CREATE ROLE {service}_reader'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{service}_reader')
\\gexec
ALTER ROLE {service}_reader WITH LOGIN PASSWORD :'reader_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
ALTER ROLE {service}_reader SET default_transaction_read_only = on;
GRANT CONNECT ON DATABASE {service}_db TO {service}_reader;
GRANT USAGE ON SCHEMA public TO {service}_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO {service}_reader;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO {service}_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE {service}_app IN SCHEMA public
    GRANT SELECT ON TABLES TO {service}_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE {service}_app IN SCHEMA public
    GRANT SELECT ON SEQUENCES TO {service}_reader;
COMMIT;
"""
        run("exec", "-T", "-e", "READER_PASSWORD", "postgres",
            "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", f"{service}_db",
            input=sql, text=True, env=environment, stdout=subprocess.DEVNULL)

    run("up", "-d", "pgadmin")
    passfile = "".join(
        f"postgres:5432:{service}_db:{service}_reader:{passwords[service]}\n"
        for service in ("main", "auth")
    )
    # PostgreSQL requires private permissions on a password file. Keep this
    # copy in pgAdmin's volume, owned by its standard unprivileged user.
    run("exec", "-T", "--user", "0", "pgadmin", "sh", "-c",
        "umask 077; cat > /var/lib/pgadmin/pgpass; chown 5050:0 /var/lib/pgadmin/pgpass",
        input=passfile, text=True)
    port = os.environ.get("PGADMIN_PORT", configuration().get("PGADMIN_PORT", "5050"))
    print(f"pgAdmin reader: http://127.0.0.1:{port} (startup may take a few seconds)")

if __name__ == "__main__":
    main()
