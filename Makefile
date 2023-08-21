serve:
	docker compose up --pull always --build

clean:
	docker rm -f lookit-api-web lookit-api-db lookit-api-broker lookit-api-worker
	docker image rm lookit-api_worker lookit-api_web

clean-translations:
	find ./locale -name *.mo -exec rm {} \; 

migrate:
	docker compose run --rm web poetry run ./manage.py migrate

superuser:
	docker compose run --rm web poetry run ./manage.py createsuperuser

site:
	docker compose run --rm web poetry run python -c \
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
	docker compose restart worker

local-certs:
	mkdir -p certs 
	mkcert -install
	cd certs && mkcert local_lookit.mit.edu

media:
	gsutil -m cp -r "gs://lookit-staging/media" ./project

media-prod:
	gsutil -m cp -r "gs://lookit-production/media" ./project

test:
	docker compose run --rm -e ENVIRONMENT= web poetry run ./manage.py test --failfast 

collectstatic: 
	docker compose run --rm web poetry run ./manage.py collectstatic --clear --noinput

poetry:
	poetry check && poetry install --sync

lint: poetry 
	poetry run pre-commit run --all-files

css: poetry 
	poetry run ./manage.py custom_bootstrap5

compilemessages:
	docker compose run --rm web-international poetry run ./manage.py compilemessages

