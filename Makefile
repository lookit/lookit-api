serve: uv
	docker compose up --pull always --build

clean: 
	docker rm -f lookit-api-web lookit-api-db lookit-api-broker lookit-api-worker
	docker image rm lookit-api_worker lookit-api_web

clean-translations:
	find ./locale -name *.mo -exec rm {} \; 

migrate: uv
	docker compose run --rm web uv run ./manage.py migrate

superuser: uv
	docker compose run --rm web uv run ./manage.py createsuperuser

site: migrate
	docker compose run --rm web uv run python -c \
		"import os; \
		import django; \
		os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings'); \
		django.setup(); \
		from django.contrib.sites.models import Site; \
		Site.objects.create(domain='localhost', name='Lookit')"

dbpipe:
	docker compose exec -T db psql -U postgres -d lookit

dbshell:
	docker compose exec -it db psql -U postgres -d lookit

broker-perms:
	docker compose exec -it broker /bin/sh -c \
		"rabbitmqctl add_user lookit-admin admin; \
		rabbitmqctl set_user_tags lookit-admin administrator; \
		rabbitmqctl set_permissions -p / lookit-admin '.*' '.*' '.*'; \
		rabbitmq-plugins enable rabbitmq_management; \
		rabbitmqadmin declare queue  --vhost=/ name=email; \
		rabbitmqadmin declare queue  --vhost=/ name=builds; \
		rabbitmqadmin declare queue  --vhost=/ name=cleanup;"
	docker compose restart worker beat

local-certs:
	mkdir -p certs 
	mkcert -install
	cd certs && mkcert local_lookit.mit.edu

media:
	gsutil -m cp -r "gs://lookit-staging/media" ./project

media-prod:
	gsutil -m cp -r "gs://lookit-production/media" ./project

test: uv
	docker compose run --rm -e ENVIRONMENT= web uv run ./manage.py test --failfast --verbosity 2

collectstatic: uv
	docker compose run --rm web uv run ./manage.py collectstatic --clear --noinput

uv:
	uv self update
	uv sync --no-managed-python --no-python-downloads

hooks:
	uv run pre-commit install --install-hooks

lint: 
	uv run pre-commit run --all-files

css: uv
	uv run ./manage.py custom_bootstrap5

makemigrations: uv
	uv run ./manage.py makemigrations

makemessages: uv 
	uv run ./manage.py makemessages --all

compilemessages: uv
	uv run ./manage.py compilemessages
