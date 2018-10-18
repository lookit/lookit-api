Building your Experiment
========================

Prerequisites
-------------

Researchers specify the protocol for a Lookit study by providing a JSON
(JavaScript Object Notation) object on the Experimenter interface, which
is interpreted according to a JSON Schema (http://json-schema.org/)
designed for Lookit studies. A `JSON
schema <http://json-schema.org/examples.html>`__ describes a class of
JSON objects, indicating what type of data to expect and require.

If you are unfamiliar with the JSON format, you may want to spend a
couple minutes reading the introduction here: http://www.json.org/.

No programming is required to design a study: JSON is a simple,
human-readable text format for describing data (see
http://www.json.org/). A JSON object is an unordered set of key – value
pairs, written as follows: \* The object itself is enclosed in curly
braces. \* Keys are unique strings enclosed in double quotes. \* A key
and value are separated by a colon. \* Key-value pairs are separated by
commas.

A JSON value can be any of the following: a string (enclosed in double
quotes), a number, a JSON object (as described above), an array (an
ordered list of JSON values, separated by commas and enclosed by square
brackets), true, false, or null. There are no requirements for specific
formatting of a JSON document (any whitespace not part of a string is
ignored). Here is an example JSON object to illustrate these principles:

.. code:: json

   {
       "name": "Jane",
       "age": 43,
       "favoritefoods": [
           "eggplant",
           "apple",
           "lima beans"
       ],
       "allergies": {
           "peanut": "mild",
           "shellfish": "severe"
       }
   }

The keys are the strings ``name``, ``age``, ``favoritefoods``, and
``allergies``. Favorite foods are stored as an array, or ordered list;
allergies are stored as a JSON object mapping food names to severity of
reaction. The same object could also be written as follows, in a
different order and with none of the formatting:
\`\ ``{"age": 43, "allergies": {"peanut": "mild", "shellfish": "severe"}, "name": "Jane", "favoritefoods": ["eggplant", "apple", lima beans"]}``

A helpful resource to check your JSON Schema for simple errors like
missing or extra commas, unmatched braces, etc. is
`jsonlint <http://jsonlint.com/>`__.

Experiment structure
--------------------

To define what actually happens in your study, go to “Build Experiment”
at the bottom of the detail page. In this “experiment editor” view, you
define the structure of an experiment using a JSON document.

Studies on Lookit are broken into a set of fundamental units called
**frames**, which can also be thought of as “pages” of the study. A
single experimental trial (e.g. looking time measurement) would
generally be one frame, as are the video consent procedure (shown in
Figure 5.3) and exit survey. The JSON Schema used to parse Lookit
studies requires a JSON object with two keys: ``frames`` and
``sequence``. The ``frames`` value defines the frames used in this
study: it must be a JSON object mapping frame nicknames (any unique
strings chosen by the researcher) to frame objects (defined next). The
``sequence`` value must be an ordered list of the frames to use in this
study; values in this list must be frame nicknames from the “frames”
value. Here is the JSON for a very minimal Lookit study:

.. code:: json

   {
       "frames": {
           "my-consent-frame": {
               "kind": "exp-video-consent",
               "prompt": "I agree to participate",
               "blocks": [
                   {
                       "title": "About the study",
                       "text": "This isn’t a real study."
                   }
               ]
           },
           "my-exit-survey": {
               "kind": "exp-lookit-exit-survey",
               "debriefing": {
                    "title": "Thank you!",
                    "text": "You participated."
               }
           }
       },
       "sequence": [
           "my-consent-frame",
           "my-exit-survey"
       ]
   }

This JSON specifies a Lookit study with two frames, consent and an exit
survey. Note that the frame nicknames ``my-consent-frame`` and
``my-exit-survey`` that are defined in ``frames`` are also used in the
``sequence``. Frames may be specified but not used in ``sequence``.
Here’s the object associated with the ``my-exit-survey`` frame:

.. code:: json

   {
               "kind": "exp-lookit-exit-survey",
               "debriefing": {
                    "title": "Thank you!",
                    "text": "You participated."
               }
    }

Within each frame object, a ``kind`` must be specified. This determines
the frame type that will be used. Additional data may be included in the
frame object to customize the behavior of the frame, for instance to
specify instruction text or the stimuli to use for a test trial. The
keys that may (or must) be included in a frame object are determined by
the frame type; each frame definition includes a JSON Schema describing
the expected data to be passed. Multiple frames of the same kind may be
included in a study – for instance, test trials using different stimuli.

The separation of frame definitions and sequence allows researchers to
easily and flexibly edit and test study protocols – for instance, the
order of frames may be altered or a particular frame removed for testing
purposes without altering any frame definitions.

A Lookit study schema
---------------------

A typical Lookit study might contain the following frame types:

1.  exp-video-config
2.  exp-video-consent
3.  exp-lookit-text
4.  exp-lookit-preview-explanation
5.  exp-video-preview
6.  exp-lookit-mood-questionnaire
7.  exp-video-config-quality
8.  exp-lookit-instructions
9.  [Study-specific frames, e.g. exp-lookit-geometry-alternation,
    exp-lookit-story-page, exp-lookit-preferential-looking,
    exp-lookit-dialogue-page; generally, a sequence of these frames
    would be put together with a randomizer]
10. exp-lookit-exit-survey

For now, before any fullscreen frames, a frame that extends
exp-frame-base-unsafe (like exp-lookit-instructions) needs to be used so
that the transition to fullscreen works smoothly. A more flexible way to
achieve this behavior is in the works!

Randomizer frames
-----------------

Generally, you’ll want to show slightly different versions of the study
to different participants: perhaps you have a few different conditions,
and/or need to counterbalance the order of trials or left/right position
of stimuli. To do this, you’ll use a special frame called a
**randomizer** to select an appropriate sequence of frames for a
particular trial. A randomizer frame is automatically expanded to a list
of frames, so that for instance you can specify your 12 looking-time
trials all at once.

For complete documentation of available randomizers, see
https://lookit.github.io/exp-addons/modules/randomizers.html.

To use a randomizer frame, set the frame ``"kind"`` to ``"choice"`` and
``"sampler"`` to the appropriate type of randomizer. We will focus here
on the most commonly-used and general randomizer type, called
`random-parameter-set <https://lookit.github.io/exp-addons/classes/randomParameterSet.html>`__.

To select this randomizer, you need to define a frame that has the
appropriate ``"kind"`` and ``"sampler"``:

::

   {
       ...
       "frames": {
           ...
           "test-trials": {
               "sampler": "random-parameter-set",
               "kind": "choice",
               ...
           }
       }
   }

In addition, there are three special properties you need to define to
use ``random-parameter-set``: ``frameList``, ``commonFrameProperties``,
and ``parameterSets``.

**``frameList``** is just what it sounds like: a list of all the frames
that should be generated by this randomizer. Each frame is a JSON object
just like you would use in the overall schema, with two differences:

-  You can define default properties, to share across all of the frames
   generated by this randomizer, in the JSON object
   ``commonFrameProperties`` instead, as a convenience.

You can use placeholder strings for any of the properties in the frame;
they will be replaced based on the values in the selected
``parameterSet``.

**``parameterSets``** is a list of mappings from placeholder strings to
actual values. When a participant starts your study, one of these sets
will be randomly selected, and any parameter values in the ``frameList``
(including ``commonFrameProperties``) that match any of the keys in this
parameter set will be replaced.

Let’s walk through an example of using this randomizer. Suppose we start
with the following JSON document describing a study that includes
instructions, an experimental manipulation asking participants to think
about how delicious broccoli is, and an exit survey:

.. code:: json

   {
       "frames": {
          "instructions": {
              "id": "text-1",
              "blocks": [
                  {
                      "text": "Some introductory text about this study."
                  },
                  {
                      "text": "Here's what's going to happen! You're going to think about how tasty broccoli is."
                  }
              ],
              "showPreviousButton": false,
              "kind": "exp-lookit-text"
          },
          "manipulation": {
              "id": "text-2",
              "blocks": [
                  {
                      "text": "Think about how delicious broccoli is."
                  },
                  {
                      "text": "It is so tasty!"
                  }
              ],
              "showPreviousButton": true,
              "kind": "exp-lookit-text"
          },
          "exit-survey": {
               "debriefing": {
                   "text": "Thank you for participating in this study! ",
                   "title": "Thank you!"
               },
               "id": "exit-survey",
               "kind": "exp-lookit-exit-survey"
           }
       },
       "sequence": [
           "instructions",
           "manipulation",
           "exit-survey"
       ]
   }

But what we really want to do is have some kids think about how tasty
broccoli is, and others think about how yucky it is! We can use a
``random-parameter-set`` frame to replace both text frames:

.. code:: json

   {
       "frames": {
           "instruct-and-manip": {
               "sampler": "random-parameter-set",
               "kind": "choice",
               "id": "instruct-and-manip",
               "frameList": [
                   {
                      "blocks": [
                          {
                              "text": "Some introductory text about this study."
                          },
                          {
                              "text": "INTROTEXT"
                          }
                      ],
                      "showPreviousButton": false
                   },
                   {
                      "blocks": [
                          {
                              "text": "MANIP-TEXT-1"
                          },
                          {
                              "text": "MANIP-TEXT-2"
                          }
                      ],
                      "showPreviousButton": true
                  }
               ],
               "commonFrameProperties": {
                   "kind": "exp-lookit-text"
               },
               "parameterSets": [
                   {
                       "INTROTEXT": "Here's what's going to happen! You're going to think about how tasty broccoli is.",
                       "MANIP-TEXT-1": "Think about how delicious broccoli is.",
                       "MANIP-TEXT-2": "It is so tasty!"
                   },
                   {
                       "INTROTEXT": "Here's what's going to happen! You're going to think about how disgusting broccoli is.",
                       "MANIP-TEXT-1": "Think about how disgusting broccoli is.",
                       "MANIP-TEXT-2": "It is so yucky!"
                   }
               ]
           },
          "exit-survey": {
               "debriefing": {
                   "text": "Thank you for participating in this study! ",
                   "title": "Thank you!"
               },
               "id": "exit-survey",
               "kind": "exp-lookit-exit-survey"
           }
       },
       "sequence": [
           "instruct-and-manip",
           "exit-survey"
       ]
   }

Notice that since both of the frames in the ``frameList`` were of the
same kind, we could define the kind in ``commonFrameProperties``. We no
longer define ``id`` values for the frames, as they will be
automatically identified as ``instruct-and-manip-1`` and
``instruct-and-manip-2``.

When the “instruct-and-manip” randomizer is evaluated, the Lookit
experiment player will start with the frameList and add the key-value
pairs in commonFrameProperties to each frame (not overwriting existing
pairs):

.. code:: javascript

   [
       {
           "kind": "exp-lookit-text",
           "blocks": [
               {
                   "text": "Some introductory text about this study."
               },
               {
                   "text": "INTROTEXT"
               }
           ],
           "showPreviousButton": false
       },
       {
           "kind": "exp-lookit-text",
           "blocks": [
               {
                   "text": "MANIP-TEXT-1"
               },
               {
                   "text": "MANIP-TEXT-2"
               }
           ],
           "showPreviousButton": true
       }
   ]

Next, one of the two objects in ``parameterSets`` is selected randomly.
(By default, parameter sets are weighted equally, but
``parameterSetWeights`` can be provided as an optional key in the
``random-parameter-set`` frame. If provided, ``parameterSetWeights``
should be an array of relative weights for the parameter sets,
corresponding to the order they are listed. For instance, if we wanted
75% of participants to think about how tasty broccoli is, we could set
``parameterSetWeights`` to [3, 1]. This allows uneven condition
assignment where needed to optimize power, as well as allowing
researchers to stop testing conditions that already have enough
participants as data collection proceeds.)

Suppose that in this case the second parameter set is selected:

.. code:: json

    {
    "INTROTEXT": "Here's what's going to happen! You're going to think about how disgusting broccoli is.",
    "MANIP-TEXT-1": "Think about how disgusting broccoli is.",
    "MANIP-TEXT-2": "It is so yucky!"
    }

Now we return to the list of frames, and wherever any value matches one
of the keys in the ``parameterSet`` (even if that value is nested in
another object), it is replaced by the corresponding value from the
``parameterSet``, yielding the following final list of frames:

::

   [
       {
           "kind": "exp-lookit-text",
           "blocks": [
               {
                   "text": "Some introductory text about this study."
               },
               {
                   "text": "Here's what's going to happen! You're going to think about how disgusting broccoli is."
               }
           ],
           "showPreviousButton": false
       },
       {
           "kind": "exp-lookit-text",
           "blocks": [
               {
                   "text": "Think about how disgusting broccoli is."
               },
               {
                   "text": "It is so yucky!"
               }
           ],
           "showPreviousButton": true
       }
   ]

Nested randomizers
~~~~~~~~~~~~~~~~~~

In more complex experimental designs, the frames created by a randomizer
may themselves be randomizers! This nesting allows more modular
specification: for instance, a study might have ten test trials, each of
which consists of three phases. The “outer” randomizer could then
generate a frameList of ten randomizer frames, each of which would be
resolved in turn into three frames. Below is a simplified example with
only two test trials, each of which has three phases:

Here’s an example. Notice that ``"kind": "choice"``,
``"sampler": "random-parameter-set"``, ``"frameList": ...``, and
``commonFrameProperties`` are ``commonFrameProperties`` of the outer
frame ``nested-trials``. That means that every “frame” we’ll create as
part of ``nested-trials`` will itself be a random-parameter-set
generated list with the same frame sequence, although we’ll be
substituting in different parameter values. (This doesn’t have to be the
case - we could show different types of frames in the list - but in the
simplest case where you’re using randomParameterSet just to group
similar repeated frame sequences, this is probably what you’d do.) The
only thing that differs across the two (outer-level) **trials** is the
``parameterSet`` used, and we list only one parameter set for each
trial, to describe (deterministically) how the outer-level
``parameterSet`` values should be applied to each particular frame.

.. code:: json

   {
         "sampler": "random-parameter-set",
         "frameList": [
           {
             "parameterSets": [
                {
                  "NTRIAL": 1,
              "PHASE1STIM": "T1P1",
              "PHASE2STIM": "T1P2",
              "PHASE3STIM": "T1P3"
                }
             ]
           },
           {
             "parameterSets": [
                {
                  "NTRIAL": 2,
              "PHASE1STIM": "T2P1",
              "PHASE2STIM": "T2P2",
              "PHASE3STIM": "T2P3"
                }
             ]
           }
         ],
         "parameterSets": [
           {
               "T1P1": "mouse",
               "T1P2": "rat",
               "T1P3": "chipmunk",
               "T2P1": "horse",
               "T2P2": "goat",
               "T2P3": "cow"
           },
           {
               "T1P1": "guppy",
               "T1P2": "tadpole",
               "T1P3": "goldfish",
               "T2P1": "whale",
               "T2P2": "manatee",
               "T2P3": "shark"
           }

         ],
         "commonFrameProperties": {
            "sampler": "random-parameter-set",
            "frameList": [
                   {
                       "nPhase": 1,
                   "animal": "PHASE1STIM"
                   },
                   {
                       "nPhase": 2,
                   "animal": "PHASE2STIM"
                   },
                   {
                       "nPhase": 3,
                   "animal": "PHASE3STIM"
                   }
            ],
            "commonFrameProperties": {
              "nTrial": "NTRIAL",
              "kind": "question-about-animals-frame"
            }
         }
   }

To evaluate this experiment frame, the Lookit experiment player starts
with the list of frames in the outer ``frameList``, adding the key:value
pairs in the outer ``commonFrameProperties`` to each frame, which yields
the following list of frames:

::

   [
           {
           "parameterSets": [
                   {
                       "NTRIAL": 1,
                   "PHASE1STIM": "T1P1",
                   "PHASE2STIM": "T1P2",
                   "PHASE3STIM": "T1P3"
                }
             ],
           "sampler": "random-parameter-set",
           "frameList": [
               {
                   "nPhase": 1,
               "animal": "PHASE1STIM"
               },
               {
                   "nPhase": 2,
               "animal": "PHASE2STIM"
               },
               {
                   "nPhase": 3,
               "animal": "PHASE3STIM"
               }
           ],
           "commonFrameProperties": {
               "nTrial": "NTRIAL",
               "kind": "question-about-animals-frame"
           }
           },
           {
               "parameterSets": [
                   {
                       "NTRIAL": 2,
                   "PHASE1STIM": "T2P1",
                   "PHASE2STIM": "T2P2",
                   "PHASE3STIM": "T2P3"
                   }
               ],
           "sampler": "random-parameter-set",
           "frameList": [
               {
                   "nPhase": 1,
               "animal": "PHASE1STIM"
               },
               {
                   "nPhase": 2,
               "animal": "PHASE2STIM"
               },
               {
                   "nPhase": 3,
               "animal": "PHASE3STIM"
               }
           ],
           "commonFrameProperties": {
               "nTrial": "NTRIAL",
               "kind": "question-about-animals-frame"
           }
       }
   ]

One of the two (outer) ``parameterSets`` is then selected randomly;
suppose the second one (aquatic instead of land animals) is selected.
Now any substitutions are made based on the keys in this parameterSet.
The first frame in the sequence is now:

.. code:: json

       {
           "parameterSets": [
                   {
                       "NTRIAL": 1,
                   "PHASE1STIM": "guppy",
                   "PHASE2STIM": "tadpole",
                   "PHASE3STIM": "goldfish"
                }
             ],
           "sampler": "random-parameter-set",
           "frameList": [
               {
                   "nPhase": 1,
               "animal": "PHASE1STIM"
               },
               {
                   "nPhase": 2,
               "animal": "PHASE2STIM"
               },
               {
                   "nPhase": 3,
               "animal": "PHASE3STIM"
               }
           ],
           "commonFrameProperties": {
               "nTrial": "NTRIAL",
               "kind": "question-about-animals-frame"
           }
       }

Next, each frame is expanded since it is in turn another randomizer (due
to ``"sampler": "random-parameter-set"``). The frame above, representing
Trial 1, will be turned into three frames. First, again, we start with
the ``frameList``, and merge the ``commonFrameProperties`` into each
frame:

::

    [
       {
           "nPhase": 1,
           "animal": "PHASE1STIM",
           "nTrial": "NTRIAL",
               "kind": "question-about-animals-frame"
       },
       {
           "nPhase": 2,
           "animal": "PHASE2STIM",
           "nTrial": "NTRIAL",
               "kind": "question-about-animals-frame"
       },
       {
           "nPhase": 3,
           "animal": "PHASE3STIM",
           "nTrial": "NTRIAL",
               "kind": "question-about-animals-frame"
       }
   ]

Finally, a parameter set is selected from ``parameterSets``. Only one
parameter set is defined for this trial, which is deliberate; it simply
selects the correct stimuli for this trial. Substituting in the values
from the parameter set yields the following list of frames:

::

   [
       {
           "nPhase": 1,
           "animal": "guppy",
           "nTrial": 1,
               "kind": "question-about-animals-frame"
       },
       {
           "nPhase": 2,
           "animal": "tadpole",
           "nTrial": 1,
               "kind": "question-about-animals-frame"
       },
       {
           "nPhase": 3,
           "animal": "goldfish",
           "nTrial": 1,
               "kind": "question-about-animals-frame"
       }
   ]

The ``random-parameter-set`` randomizer is expected to be general enough
to capture most experimental designs that researchers put on Lookit, but
additional more specific randomizers will also be designed to provide
simpler syntax for common use cases.

Finding and using specific frames
---------------------------------

For the most current documentation of individual frames available to
use, please see https://lookit.github.io/exp-addons/modules/frames.html
and https://lookit.github.io/exp-addons/modules/randomizers.html.

For each frame, you will find an **example** of using it in a JSON
schema; documentation of the **properties** which can be defined in the
schema; and, under Methods / serializeContent, a description of the
**data** this frame records. Any frame-specific **events** that are
recorded and may be included in the eventTimings object sent with the
data are also described.
