Workflow: managing study states
===============================

Why Transitions
---------------

`Transitions <https://github.com/pytransitions/transitions>`__ is an
object-oriented state machine implemented in Python.

It’s both very powerful and very simple. It’s definition is a python
dictionary so it can be easily serialized into JSON and stored in a
database or configured via YAML. It has callback functionality for state
transitions. It can create diagrams of the workflow using pygraphiz. It
also ties into django model classes very easily.

How
---

The workflow is defined in ``studies/workflow.py`` in a dictionary
called ``transitions``. Here is a
`gist <https://gist.github.com/cwisecarver/7335d99f04fa412a1004c72e2b979e34>`__
that explains how the pieces fit together.

Make a diagram
--------------

To make a workflow diagram in png format start a shell plus instance
with ``python manage.py shell_plus`` and execute the following:

.. code:: python

   # get a study you'd like to diagram
   s = Study.objects.first()
   # draw the whole graph ... in which case the study you choose doesn't matter
   s.machine.get_graph().draw('fancy_workflow_diagram.png', prog='dot')
   # ... or just the region of interest (contextual to the study you chose)
   # (previous state, active state and all reachable states)
   s.machine.get_graph(show_roi=True).draw('roi_diagram.png', prog='dot')

Logging
-------

There is a ``_finalize_state_change`` method on the ``Study`` model. It
fires after every workflow transition. It saves the model with its
updated ``state`` field and also creates a ``StudyLog`` instance making
record of the transition. This callback would be the optimal place to
add functionality that needs to happen after every workflow transition.
