.. lookit-api documentation master file, created by
   sphinx-quickstart on Wed Sep  6 09:57:34 2017.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to Lookit's documentation!
==========================================

The `lookit-api codebase <https://github.com/lookit/lookit-api>`_ contains 
what were previously separate Experimenter and Lookit applications. Experimenter is a 
platform for designing and administering research studies, meant for researchers. 
The Lookit platform is participant-facing, where users can signup and take part in studies.
It is built using Django, PostgreSQL, and Ember.js (see Ember portion of codebase, 
`ember-lookit-frameplayer <https://github.com/lookit/ember-lookit-frameplayer>`_), 
and has been developed by the `Center for Open Science <https://cos.io/>`_.

Contents:

.. toctree::
   :maxdepth: 3

   definitions
   experimenter
   experiments
   stimuli
   experimentdata
   local-frame-development
   django-project-installation
   ember-app-installation
   frames
   mixins
   random
   contributing
   api-documentation
   permissions
   workflow
   celery_tasks
