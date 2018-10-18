Experiment data (non-video)
===========================

Accessing experiment data
~~~~~~~~~~~~~~~~~~~~~~~~~

You can see and download collected responses either via the Lookit
experimenter interface or using the API.

A researcher with edit permissions for a particular study can download
session data in JSON or CSV format via the Experimenter interface. A
session record in a Postgres database is created each time a participant
starts the study, and includes a timestamp, account information,
condition assignment, the sequence of frames the participant actually
saw, and frame-specific information for each frame (included in an
‘expData’ structure which is a JSON object with keys corresponding to
frame nicknames as defined in the study definition JSON). Each frame
type may save different data, e.g. form responses; frames that record
webcam video include the video filename(s). The data captured by a
particular frame are listed in the frame documentation at
http://lookit.github.io/exp-addons, under ‘Methods’ >
‘serializeContent’. Additionally, event data is captured for each frame
and included under an eventTimings key within the frame data JSON,
minimally including a timestamped event when the user proceeds to the
next frame. These events are listed under ‘Events’ in the documentation.

Structure of session data
~~~~~~~~~~~~~~~~~~~~~~~~~

The data saved when a subject participates in a study varies based on
how that experiment is defined. For concreteness, let’s start by looking
at an example of the data you can download about a single session. (The
``eventTimings`` objects have been shortened to show just a single
event.)

.. code:: json

   {
       "response": {
           "id": 1190,
           "uuid": "d96b3ba5-6806-4c09-86e2-77456163eb5a",
           "sequence": [
               "0-0-video-config",
               "1-1-video-consent",
               "2-2-instructions",
               "3-3-mood-survey",
               "4-4-pref-phys-videos",
               "5-5-exit-survey"
           ],
           "conditions": {
               "4-pref-phys-videos": {
                   "showStay": 18,
                   "startType": 21
               }
           },
           "exp_data": {
               "3-3-mood-survey": {
                   "active": "4",
                   "rested": "1",
                   "healthy": "2",
                   "eventTimings": [
                       {
                           "eventType": "exp-mood-questionnaire:nextFrame",
                           "timestamp": "2018-07-06T23:56:06.459Z"
                       }
                   ]
               },
               "0-0-video-config": {
                   "eventTimings": [
                       {
                           "pipeId": "",
                           "videoId": "videoStream_0f620873-2847-4eeb-9854-df7898934c17_0-video-config_d96b3ba5-6806-4c09-86e2-77456163eb5a_1530921299537_405",
                           "eventType": "exp-video-config:recorderReady",
                           "timestamp": "2018-07-06T23:54:59.548Z",
                           "streamTime": null
                       }
                   ]
               },
               "2-2-instructions": {
                   "eventTimings": [
                       {
                           "eventType": "exp-physics-intro:nextFrame",
                           "timestamp": "2018-07-06T23:55:53.530Z"
                       }
                   ]
               },
               "1-1-video-consent": {
                   "videoId": "videoStream_0f620873-2847-4eeb-9854-df7898934c17_1-video-consent_d96b3ba5-6806-4c09-86e2-77456163eb5a_1530921346557_292",
                   "videoList": [
                       "videoStream_0f620873-2847-4eeb-9854-df7898934c17_1-video-consent_d96b3ba5-6806-4c09-86e2-77456163eb5a_1530921346557_292"
                   ],
                   "eventTimings": [
                       {
                           "pipeId": "",
                           "videoId": "videoStream_0f620873-2847-4eeb-9854-df7898934c17_1-video-consent_d96b3ba5-6806-4c09-86e2-77456163eb5a_1530921346557_292",
                           "eventType": "exp-video-consent:recorderReady",
                           "timestamp": "2018-07-06T23:55:46.558Z",
                           "streamTime": 0
                       }
                   ]
               },
               "5-5-exit-survey": {
                   "feedback": "",
                   "birthDate": "2018-07-03T04:00:00.000Z",
                   "useOfMedia": "private",
                   "withdrawal": false,
                   "eventTimings": [
                       {
                           "eventType": "exp-exit-survey:nextFrame",
                           "timestamp": "2018-07-06T23:57:02.201Z"
                       }
                   ],
                   "databraryShare": "no"
               },
               "4-4-pref-phys-videos": {
                   "videoId": "videoStream_0f620873-2847-4eeb-9854-df7898934c17_4-pref-phys-videos_d96b3ba5-6806-4c09-86e2-77456163eb5a_1530921371545_923",
                   "videoList": [
                       "videoStream_0f620873-2847-4eeb-9854-df7898934c17_4-pref-phys-videos_d96b3ba5-6806-4c09-86e2-77456163eb5a_1530921371545_923"
                   ],
                   "videosShown": [
                       "https://s3.amazonaws.com/lookitcontents/exp-physics-final/stimuli/stay/webm/sbs_stay_near_mostly-on_book_c2_green_NN.webm",
                       "https://s3.amazonaws.com/lookitcontents/exp-physics-final/stimuli/stay/webm/sbs_stay_mostly-on_near_book_c2_green_NN.webm"
                   ],
                   "eventTimings": [
                       {
                           "pipeId": "",
                           "videoId": "videoStream_0f620873-2847-4eeb-9854-df7898934c17_4-pref-phys-videos_d96b3ba5-6806-4c09-86e2-77456163eb5a_1530921371545_923",
                           "eventType": "exp-video-physics:recorderReady",
                           "timestamp": "2018-07-06T23:56:11.549Z",
                           "streamTime": 0
                       }
                   ]
               }
           },
           "global_event_timings": [],
           "completed": true
       },
       "study": {
           "id": 12,
           "uuid": "0f620873-2847-4eeb-9854-df7898934c17"
       },
       "participant": {
           "id": 3047,
           "uuid": "31692a6c-df1e-47e1-8ad0-e2780d095c05",
           "nickname": "Kim"
       },
       "child": {
           "id": 3749,
           "uuid": "470a0d33-77ee-4dd5-a64e-ec7231f23913",
           "name": "ExperimenterChild",
           "birthday": "2018-02-05",
           "gender": "f",
           "age_at_birth": "30",
           "additional_information": "Test child"
       }
   }

There are four top-level keys in this data: ``response``, ``study``,
``participant``, and ``child``. Study, participant, and child
information should be fairly self-explanatory: which study does this
response pertain to, which family account created the response, and
which child was participating. (The child key ``age_at_birth`` refers to
gestational age in weeks at birth.) The ``response`` data contains
information concerning this particular session: when it happened, what
condition the child was assigned to, events that happened as the family
proceeded through the study, etc. The response properties are described
below:

-  *id*: short unique ID for the response
-  *uuid*: long unique ID for the response (should be used as primary
   identifier)
-  *sequence*: The sequence of **frames** the subject actually saw
   (after running randomization, etc.). Does not include frames skipped
   if they left early. The frame names follow the pattern
   ``<order>-<order>-<frame.id>``, where ``<order>`` is the order in the
   overall sequence where this **frame** appeared, and ``<frame.id>`` is
   the identifier of the frame as defined in the ‘frames’ property of
   the experiment structure.
-  *conditions*: An object containing information about conditions to
   which the subject was assigned in any frames that do randomization
   (choice frames). Keys are in the format ``<order>-<frame.id>``
   corresponds with the ``<order>`` from the ‘sequence’ of the
   *original* experiment structure, and the ``<frame.id>`` again
   corresponds with the identifier of the frame as defined in the
   ‘frames’ property of the experiment structure. Data will be stored in
   conditions for the *first* frame created by a randomizer (top-level
   only for now, i.e. not from nested randomizers). Values are objects
   containing mappings from condition names to their values for this
   session. The data stored by a particular randomizer can be found
   under ``methods: conditions`` in the `randomizer
   documentation <http://lookit.github.io/exp-addons/modules/randomizers.html>`__
-  *global_event_timings*: A list of events recorded during the study,
   not tied to a particular frame. Currently used for recording early
   exit from the study; an example value is:

.. code:: js

   [
               {
                   "exitType": "manualInterrupt",
                   "eventType": "exitEarly",
                   "timestamp": "2018-07-06T23:56:55.282Z",
                   "lastPageSeen": 10
               }
   ]

-  *completed*: A true/false flag indicating whether or not the
   participant submitted the last frame of the study. Note that this may
   not line up with your notion of whether the participant completed the
   study, in two ways: first, ``completed`` will be true even if the
   participant leaves early, as long as they submit the exit survey
   which they skip to when pressing F1. Second, ``completed`` will be
   false if they don’t submit that exit survey, even if they completed
   all of the important experimental parts of the study.
-  *exp_data*: A JSON object containing the data collected by each
   **frame** in the study. More on this to follow.

Interpreting ``exp_data``
~~~~~~~~~~~~~~~~~~~~~~~~~

Here’s an example of data collected during a session (note: not all
fields are shown):

.. code:: json

   {
       "sequence": [
           "0-0-intro-video",
           "1-1-survey",
           "2-2-exit-survey"
       ],
       "conditions": {
           "1-survey": {
               "parameterSet": {
                   "QUESTION1": "What is your favorite color?",
                   "QUESTION2": "What is your favorite number?"
               },
               "conditionNum": 0
           }
       },
       "exp_data": {
           "0-0-intro-video": {
               "eventTimings": [{
                   "eventType": "nextFrame",
                   "timestamp": "2016-03-23T16:28:20.753Z"
               }]
           },
           "1-1-survey": {
               "formData": {
                   "name": "Sam",
                   "favPie": "pecan"
               },
               "eventTimings": [{
                   "eventType": "nextFrame",
                   "timestamp": "2016-03-23T16:28:26.925Z"
               }]
           },
           "2-2-exit-survey": {
               "formData": {
                   "thoughts": "Great!",
                   "wouldParticipateAgain": "Yes"
               },
               "eventTimings": [{
                   "eventType": "nextFrame",
                   "timestamp": "2016-03-23T16:28:32.339Z"
               }]
           }
       }
   }

``exp_data`` is an object with three keys that correspond with the frame
names from ‘sequence’. Each of the associated values has an
``eventTimings`` property. This is a place to collect user-interaction
events during an experiment, and by default contains the ‘nextFrame’
event which records when the user progressed to the next **frame** in
the ‘sequence’. You can see which events a particular frame records by
looking at the ‘Events’ tab in its `frame
documentation <http://lookit.github.io/exp-addons/modules/frames.html>`__.
Events recorded by a frame that does video recording will include
additional information, for instance to indicate when relative to the
video stream this event happened.

The other properties besides ‘eventTimings’ are dependent on the
**frame** type. You can see which other properties a particular frame
type records by looking at the parameters of the ``serializeContent``
method under the ‘Methods’ tab in its `frame
documentation <http://lookit.github.io/exp-addons/modules/frames.html>`__.
