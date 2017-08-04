#! /bin/bash

pip install -r requirements/dev.txt

psql -U postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'lookit'" | grep -q 1 || psql -U postgres -c "CREATE DATABASE lookit"

python manage.py migrate
