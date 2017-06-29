#! /bin/bash

pip install -r requirements/defaults.txt
pip install -r requirements/dev.txt

psql -U postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'lookit'" | grep -q 1 || psql -U postgres -c "CREATE DATABASE lookit"

/Users/henriqueharman/.virtualenvs/lookit/bin/python3.6 manage.py migrate
