SHELL := /bin/bash
COMPOSE := docker compose
WPCLI := $(COMPOSE) run --rm wpcli

.PHONY: help up down restart logs reset wp bootstrap dump status app-env app-build app-up app-migrate app-import app-setup app-logs app-down test

help:
	@echo "Targets:"
	@echo "  up              Start db + wordpress + phpmyadmin"
	@echo "  down            Stop containers (preserve data)"
	@echo "  reset           Remove only legacy WordPress containers and data volumes"
	@echo "  logs            Tail wordpress + db logs"
	@echo "  wp ARGS=\"...\" Run wp-cli inside the stack (e.g. make wp ARGS=\"plugin list\")"
	@echo "  bootstrap       One-shot: install WP core + plugins + seed all content"
	@echo "  dump            Export current DB to db/dump.sql"
	@echo "  status          Show running services"
	@echo "  app-setup       Build, migrate, import, and start both Django services"
	@echo "  app-up          Start both Django services with existing data"
	@echo "  app-import      Rerun the create-only import from the committed dump"
	@echo "  app-build       Rebuild application images after code changes"
	@echo "  test            Run Python and frontend checks in containers"

up: app-env
	$(COMPOSE) up -d db wordpress phpmyadmin

down:
	$(COMPOSE) down

reset: app-env
	python3 scripts/reset_wordpress.py

logs:
	$(COMPOSE) logs -f wordpress db

wp: app-env
	$(WPCLI) $(ARGS)

bootstrap: app-env
	$(COMPOSE) run --rm --entrypoint bash wpcli /scripts/seed.sh

dump:
	@mkdir -p db
	$(COMPOSE) exec db sh -c 'mariadb-dump -u root -p"$$MYSQL_ROOT_PASSWORD" --default-character-set=utf8mb4 --add-drop-table --skip-extended-insert "$$MYSQL_DATABASE"' > db/dump.sql
	@echo "Wrote db/dump.sql ($$(wc -l < db/dump.sql) lines)"

status:
	$(COMPOSE) ps

app-env:
	python3 scripts/setup_app_env.py

app-build: app-env
	$(COMPOSE) build auth main

app-migrate: app-env
	$(COMPOSE) up -d --wait postgres
	$(COMPOSE) run --rm auth python manage.py migrate --noinput
	$(COMPOSE) run --rm main python manage.py migrate --noinput

app-import: app-env
	python3 scripts/import_wordpress.py

app-up: app-env
	$(COMPOSE) up -d auth main

app-setup: app-build app-migrate app-import app-up

app-logs:
	$(COMPOSE) logs -f auth main

app-down:
	$(COMPOSE) stop auth main postgres import-source frontend

test: app-env
	python3 scripts/test_stack.py
