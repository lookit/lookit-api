Custom randomizer frames
========================

Experimenter supports a special kind of frame called ‘choice’ that
defers determining what sequence of frames a participant will see until
the page loads. This allows for dynamic ordering of frame sequence in
particular to support randomization of experimental conditions. The goal
of this page is to walk through an example of implementing a custom
‘randomizer’.

Overview of ‘choice’ structure
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Generally the structure for a ‘choice’ type frame takes the form:

.. code:: json

   {
       "kind": "choice",
       "sampler": "random",
       "options": [
           "video1",
           "video2"
       ]
   }

Where: - **sampler** indicates which ‘randomizer’ to use. This must
correspond with the values defined in
``lib/exp-player/addon/randomizers/index.js`` - **options**: an array of
options to sample from. These should correspond with values from the
``frames`` object defined in the experiment structure (for more on this,
see `the experiments docs <experiments.html>`__)

Making your own
~~~~~~~~~~~~~~~

There is some template code included to help you get started. From
within the ``ember-lookit-frameplayer/lib/exp-player`` directory, run:

.. code:: bash

   ember generate randomizer <name>

which will create a new file: ``addon/randomizers/<name>.js``. Let’s
walk through an example called ‘next. The ’next’ randomizer simply picks
the next frame in a series. (based on previous times that someone
participated in an experiment)

.. code:: bash

   $ ember generate randomizer next
   ...
   installing randomizer
     create addon/randomizers/next.js

Which looks like:

.. code:: javascript

   /*
    NOTE: you will need to manually add an entry for this file in addon/randomizers/index.js, e.g.:
   import
   import Next from './next';
   ...
   {
       ...
       next: Next
   }
    */
   var randomizer = function(/*frame, pastSessions, resolveFrame*/) {
       // return [resolvedFrames, conditions]
   };
   export default randomizer;

The most important thing to note is that this module exports a single
function. This function takes three arguments: - ``frame``: the JSON
entry for the ‘choice’ frame in context - ``pastSessions``: an array of
this participants past sessions of taking this experiment. See `the
experiments docs <experiments.html>`__ for more explanation of this data
structure - ``resolveFrame``: a copy of the ExperimentParser’s
\_resolveFrame method with the ``this`` context of the related
ExperimentParser bound into the function.

Additionally, this function should return a two-item array containing: -
a list of resolved frames - the conditions used to determine that
resolved list

Let’s walk through the implementation:

.. code:: javascript

   var randomizer = function(frame, pastSessions, resolveFrame) {
       pastSessions = pastSessions.filter(function(session) {
           return session.get('conditions');
       });
       pastSessions.sort(function(a, b) {
           return a.get('createdOn') > b.get('createdOn') ? -1: 1;
       });
       // ...etc
   };

First we make sure to filter the ``pastSessions`` to only the one with
reported conditions, and make sure the sessions are sorted from most
recent to least recent.

::

       ...
       var option = null;
       if(pastSessions.length) {
           var lastChoice = (pastSessions[0].get(`conditions.${frame.id}`) || frame.options[0]);
           var offset = frame.options.indexOf(lastChoice) + 1;
           option = frame.options.concat(frame.options).slice(offset)[0];
       }
       else {
           option = frame.options[0];
       }

Next we look at the conditions for this frame from the last session
(``pastSessions[0].get(``\ conditions.${frame.id}\ ``)``). If that value
is unspecified, we fall back to the first option in ``frame.options``.
We calculate the index of that item in the available ``frame.options``,
and increment that index by one.

This example allows the conditions to “wrap around”, such that the
“next” option after the last one in the series circles back to the
first. To handle this we append the ``options`` array to itself, and
slice into the resulting array to grab the “next” item.

If there are not past sessions, then we just grab the first item from
``options``.

::

       var [frames,] = resolveFrame(option);
       return [frames, option];
   };

   export default randomizer;

Finally, we need to resolved the selected sequence using the
``resolveFrame`` argument. This function always returns a two-item array
containing: - an array of resolved frames - the conditions used to
generate that array

In this case we can ignore the second part of the return value, and only
care about the returned ``frames`` array.

The ``export default randomizer`` tells the module importer that this
file exports a single item (``export default``), which in this case is
the randomizer function (**note**: the name of this function is not
important).

Finally, lets make sure to add an entry to the index.js file in the same
directory:

.. code:: javascript

   import next from './next';

   export default {
       ...,
       next: next
   };

This allows consuming code to easily import all of the randomizers at
once and to index into the ``randomizers`` object dynamically, e.g.
(from the ``ExperimentParser``):

.. code:: javascript

   import randomizers from 'exp-player/randomizers/index';
   // ...
   return randomizers[randomizer](
       frame,
       this.pastSessions,
       this._resolveFrame.bind(this)
   );
