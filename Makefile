serve:
	docker compose pull && docker compose up --build

clean:
	docker rm -f lookit-api-web lookit-api-db lookit-api-broker lookit-api-worker
	docker image rm lookit-api_worker lookit-api_web

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

test:
	docker compose run --rm web poetry run ./manage.py test --failfast
