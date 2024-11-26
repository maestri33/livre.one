include custom.mk

setup-env:
	@[ ! -f ./.env ] && cp ./.env.example ./.env || echo "Arquivo .env já existe."
	@[ ! -f ./frontend/.env ] && cp ./frontend/.env.example ./frontend/.env || echo "Arquivo .env do frontend já existe."

start: ## Iniciar os contêineres Docker
	@echo "Iniciando os contêineres Docker"
	@docker compose up

stop: ## Parar os contêineres
	@docker compose down

restart: stop start ## Reiniciar os contêineres

start-bg:  ## Rodar os contêineres em segundo plano
	@docker compose up -d

build: ## Construir os contêineres
	@docker compose build

ssh: ## Acessar o contêiner web em execução via SSH
	docker compose exec web bash

bash: ## Obter um shell Bash no contêiner web
	docker compose run --rm --no-deps web bash

manage: ## Executar qualquer comando manage.py. Ex.: `make manage ARGS='createsuperuser'`
	@docker compose run --rm web python manage.py ${ARGS}

migrations: ## Criar migrações do banco de dados no contêiner
	@docker compose run --rm web python manage.py makemigrations

migrate: ## Aplicar migrações do banco de dados no contêiner
	@docker compose run --rm web python manage.py migrate

translations:
	@docker compose run --rm --no-deps web python manage.py makemessages --all --ignore node_modules --ignore venv --ignore .venv
	@docker compose run --rm --no-deps web python manage.py makemessages -d djangojs --all --ignore node_modules --ignore venv --ignore .venv
	@docker compose run --rm --no-deps web python manage.py compilemessages --ignore venv --ignore .venv

shell: ## Obter um shell do Django
	@docker compose run --rm web python manage.py shell

dbshell: ## Acessar o shell do banco de dados
	@docker compose exec db psql -U postgres core

test: ## Executar os testes do Django
	@docker compose run --rm web python manage.py test ${ARGS}

init: setup-env start-bg migrations migrate bootstrap_content  ## Inicialização rápida: iniciar contêineres e aplicar migrações

pip_compile_cmd = uv pip compile --no-emit-package setuptools --no-strip-extras
pip-compile: ## Compilar os arquivos requirements.in para requirements.txt
	@docker compose run --rm --no-deps web $(pip_compile_cmd) requirements/requirements.in -o requirements/requirements.txt
	@docker compose run --rm --no-deps web $(pip_compile_cmd) requirements/dev-requirements.in -o requirements/dev-requirements.txt
	@docker compose run --rm --no-deps web $(pip_compile_cmd) requirements/prod-requirements.in -o requirements/prod-requirements.txt

requirements: pip-compile build stop start-bg  ## Recompilar os requisitos e reiniciar os contêineres

ruff-format: ## Executar o formatador Ruff no código
	@docker compose run --rm --no-deps web ruff format .

ruff-lint:  ## Executar o linter Ruff no código
	@docker compose run --rm --no-deps web ruff check --fix  .

format: ruff-format ruff-lint ## Formatar e aplicar lint no código usando Ruff

npm-install: ## Executar npm install no contêiner
	@docker compose run --rm --no-deps web npm install $(filter-out $@,$(MAKECMDGOALS))

npm-uninstall: ## Executar npm uninstall no contêiner
	@docker compose run --rm --no-deps web npm uninstall $(filter-out $@,$(MAKECMDGOALS))

npm-build: ## Executar npm build no contêiner (para assets de produção)
	@docker compose run --rm --no-deps web npm run build

npm-dev: ## Executar npm dev no contêiner
	@docker compose run --rm --no-deps web npm run dev

npm-watch: ## Executar npm watch no contêiner (recomendado para desenvolvimento)
	@docker compose run --rm --no-deps web npm run dev-watch

npm-type-check: ## Executar o verificador de tipos no código TypeScript do frontend
	@docker compose run --rm --no-deps web npm run type-check

build-api-client:  ## Atualizar o código do cliente da API em JavaScript
	@docker run --rm --network host -v $(shell pwd)/api-client:/local openapitools/openapi-generator-cli:v7.9.0 generate \
	-i http://localhost:8000/api/schema/ \
	-g typescript-fetch \
	-o /local/

bootstrap_content:  ## Inicializar o conteúdo Wagtail com exemplos de páginas e posts
	@docker compose run --rm web python manage.py bootstrap_content

upgrade: requirements migrations migrate npm-install npm-dev

.PHONY: help
.DEFAULT_GOAL := help

help:
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

# Padrão para alvos indefinidos - previne mensagens de erro ao rodar comandos como make npm-install <pacote>
%:
	@:
