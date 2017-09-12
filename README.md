# Lookit-api

This is the codebase for Experimenter and Lookit.  Experimenter is a platform for designing and administering research studies, meant for researchers. The Lookit platform is participant-facing, where users can signup and take part in studies. It is built using Django, PostgreSQL, and Ember.js (see Ember portion of codebase, [ ember-lookit-frameplayer](https://github.com/CenterForOpenScience/ember-lookit-frameplayer)), and is developed by the [Center for Open Science](https://cos.io/).

`master` Build Status: [![Build Status](https://travis-ci.org/CenterForOpenScience/lookit-api.svg?branch=master)](https://travis-ci.org/CenterForOpenScience/lookit-api)

`develop` Build Status: [![Build Status](https://travis-ci.org/CenterForOpenScience/lookit-api.svg?branch=develop)](https://travis-ci.org/CenterForOpenScience/lookit-api)

## Getting Started
### Prerequisites
- Make sure you have python 3.6: `$ python --version`.  If you don't have this, install from https://www.python.org/.
- Make sure you have `pip`. `$ pip --version`
- Create a virtual environment with python 3.6
  - One way to do this:
  - `$  pip install virtualenv`
  - `$ virtualenv -p python3 envname`, *where `envname` is the name of your virtual environment.*
  - `$ source envname/bin/activate` *Activates your virtual environment*
- Install postgres
  - make sure you have brew `$ brew`
  - `$ brew install postgresql`
  - `$ brew services start postgres` *Starts up postgres*
  - `$ createdb lookit` *Creates lookit database*

### Installation
- `$ git clone https://github.com/CenterForOpenScience/lookit-api.git`
- `$ cd lookit-api`
- `$ sh up.sh` *Installs dependencies and run migrations*
- `$ python manage.py createsuperuser` *Creates superuser locally (has all user permissions)*
- `$ python manage.py runserver` *Starts up server*

## Useful features

### Creating feedback
To add feedback to a response via the API, you must have "can_edit_study"
permissions for the associated study.

POST /api/v1/feedback/
```json
{
 "data": {
   "attributes": {
     "comment": "<add your comment here>"
   },
   "relationships": {
     "response": {
       "data": {
         "type": "responses",
         "id": "<response_id>"
       }
     }
   },
   "type": "feedback"
 }
}
```
