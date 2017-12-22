# Experiment data

### Accessing experiment data

You can see and download collected data from sessions marked as 'completed' (user filled out the exit survey) directly from the Experimenter application. 

You can also download JSON study or accounts data from the command line using the python script [experimenter.py](https://github.com/CenterForOpenScience/lookit/blob/develop/scripts/experimenter.py) ([description](https://github.com/CenterForOpenScience/lookit/pull/85)); you'll need to set up a file config.json with the following content:

```json
{
    "host": "https://staging-metadata.osf.io",
    "namespace": "lookit",
    "osf_token": "YOUR_OSF_TOKEN_HERE"
}

```

You can create an OSF token for the staging server [here](https://staging.osf.io/settings/tokens/). 

The collection name to use to get study session records is `session[STUDYIDHERE]s`, e.g. `session58d015243de08a00400316e0s`.

### Structure of session data

The data saved when a subject participates in a study varies based on how that experiment is defined. The general structure for this **session** data is:

```json
{
    "type": "object",
    "properties": {
        "profileId": {
            "type": "string",
            "pattern": "\w+\.\w+"
        },
        "experimentId": {
            "type": "string",
            "pattern": "\w+"
        },
        "experimentVersion": {
            "type": "string"
        },
        "completed": {
            "type": "boolean"
        },
        "sequence": {
            "type": "array",
            "items": {
                "type": "string"
            }
        },
        "conditions": {
            "type": "object"
        },
        "expData": {
            "type": "object"
        },
        "feedback": {
            "$oneOf": [{
                "type": "string"
            }, null]
        },
        "hasReadFeedback": {
            "$oneOf": [{
                "type": "boolean"
            }, null]
        },
        "globalEventTimings": {
            "type": "array",
            "items": {
                "type": "object"
            }
        }
    },
    "required": [
        "profileId",
        "experimentId",
        "experimentVersion",
        "completed",
        "sequence",
        "expData"
    ]
}
```

And descriptions of these properties are enumerated below:

- *profileId*: This unique identifier of the participant. This field follows the form: `<account.id>.<profile.id>`, where `<account.id>` is the unique identifier of the associated account, and `<profile.id>` is the unique identifier of the profile active during this particular session (e.g. the participating child). Account data is stored in a separate database, and includes demographic survey data and the list of profiles associated with the account.
- *experimentId*: The unique identifier of the study the subject participated in. 
- *experimentVersion*: The unique identifier of the version of the study the subject participated in. TODO: more on JamDB, versioning
- *completed*: A true/false flag indicating whether or not the subject completed the study.
- *sequence*: The sequence of **frames** the subject actually saw (after running randomization, etc.)
- *conditions*: For randomizers, this records what condition the subject was assigned
- *expData*: A JSON object containing the data collected by each **frame** in the study. More on this to follow.
- *feedback*: Some researchers may have a need to leave some session-specific feedback for a subject; this is shown to the participant in their 'completed studies' view.
- *hasReadFeedback*: A true/false flag to indicate whether or not the given feedback has been read.
- *globalEventTimings*: A list of events recorded during the study, not tied to a particular frame. Currently used for recording early exit from the study; an example value is 

```json
"globalEventTimings": [
        {
            "exitType": "browserNavigationAttempt", 
            "eventType": "exitEarly", 
            "lastPageSeen": 0, 
            "timestamp": "2016-11-28T20:00:13.677Z"
        }
    ]
```

### Sessions and `expData` in detail

Lets walk through an example of data collected during a session (note: some fields are hidden):

```json
{
	"sequence": [
		"0-intro-video",
		"1-survey",
		"2-exit-survey"
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
	"expData": {
		"0-intro-video": {
			"eventTimings": [{
				"eventType": "nextFrame",
				"timestamp": "2016-03-23T16:28:20.753Z"
			}]
		},
		"1-survey": {
			"formData": {
				"name": "Sam",
				"favPie": "pecan"
			},
			"eventTimings": [{
				"eventType": "nextFrame",
				"timestamp": "2016-03-23T16:28:26.925Z"
			}]
		},
		"2-exit-survey": {
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
```

Things to note:
- 'sequence' has resolved to three items following the pattern `<order>-<frame.id>`, where `<order>` is the order in 
  the overall sequence where this **frame** appeared, and `<frame.id>` is the identifier of the frame as defined in 
  the 'frames' property of the experiment structure. Notice in particular that since 'survey-2' was randomly selected, 
  it appears here.
- 'conditions' has the key/value pair `"1-survey": 1`, where the format `<order>-<frame.id>` corresponds 
  with the `<order>` from the 'sequence' of the *original* experiment structure, and the `<frame.id>` again corresponds 
  with the identifier of the frame as defined in 
  the 'frames' property of the experiment structure. Data will be stored in conditions for the first frame created by a randomizer (top-level only for now, i.e. not from nested randomizers). The data stored by a particular randomizer can be found under `methods: conditions` in the [randomizer documentation](http://centerforopenscience.github.io/exp-addons/modules/randomizers.html)
- 'expData' is an object with three properties (corresponding with the values from 'sequence'). Each of these objects has an 'eventTimings' property. This is a place to collect user-interaction events during an experiment, and by default contains the 'nextFrame' event which records when the 
  user progressed to the next **frame** in the 'sequence'. You can see which events a particular frame records by looking at the 'Events' tab in its [frame documentation](http://centerforopenscience.github.io/exp-addons/modules/frames.html). Other properties besides 'eventTimings' are dependent on 
  the **frame** type. You can see which properties a particular frame type records by looking at the parameters of the `serializeContent` method under the 'Methods' tab in its [frame documentation](http://centerforopenscience.github.io/exp-addons/modules/frames.html).  Notice that 'exp-video' captures no data, and that both 'exp-survey' **frames** capture a 'formData' object.
