APP_NAME = TicketsAPI

# Dart Sass that ships with sass-embedded (dev dependency), extra arguments go straight to it
SASS = uv run python -c "import subprocess, sys; from sass_embedded.dart_sass import Release; s = Release.init().get_executable(); sys.exit(subprocess.call([str(s.dart_vm_path), str(s.sass_snapshot_path), *sys.argv[1:]]))"
SASS_ARGS = --style=compressed --no-source-map static/scss/index.scss:static/css/index.css

target:
	@awk -F ':|##' '/^[^\t].+?:.*?##/ { printf "\033[0;36m%-15s\033[0m %s\n", $$1, $$NF }' $(MAKEFILE_LIST)

install:  ## Install everything, including dev tools (SASS, ruff, pyright)
	uv sync --extra dev

git_pull:  ## Pull the latest code from git
	git pull

pm2_start:  ## Create a PM2 instance
	pm2 start uv --name $(APP_NAME) --interpreter none -- run index.py -u

pm2_restart:  ## Restart PM2
	pm2 restart $(APP_NAME)

sass:  ## Compile static/scss into static/css
	@$(SASS) $(SASS_ARGS)

type:  ## Run pyright
	@uv run pyright --pythonversion 3.13

lint:  ## Run ruff
	@uv run ruff check --config pyproject.toml

soft_update: git_pull pm2_restart  ## Pull and reboot PM2
update: git_pull install sass pm2_restart  ## Pull, install, compile SASS and reboot PM2

db_sync:  ## Create/update the database tables from schema.sql (also done on startup)
	uv run python -c "from postgreslite import PostgresLite; from utils.config import load_config; print(PostgresLite(load_config().get('DB_PATH', 'storage.db')).sync_schema('schema.sql'))"

db_dump:  ## Print the current database schema
	uv run python -c "from postgreslite import PostgresLite; from utils.config import load_config; print(PostgresLite(load_config().get('DB_PATH', 'storage.db')).dump_schema())"
