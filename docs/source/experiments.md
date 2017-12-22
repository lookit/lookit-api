# Building an Experiment

### Prerequisites

If you are unfamiliar with the JSON format, you may want to spend a couple minutes reading the introduction here: 
[http://www.json.org/](http://www.json.org/).

Additionally, we use JSON Schema heavily throughout this project. The examples [here](http://json-schema.org/examples.html) 
are a great place to learn more about this specification.

A helpful resource to check your JSON Schema for simple errors like missing or extra commas, unmatched braces, etc. is [jsonlint](http://jsonlint.com/).

### Creating a new study and setting study details

You can click 'New Experiment' to get started working on your own study, or clone an existing study to copy its experiment definition. 

Here is the 'experiment detail view' for an example study. The primary purpose of the details you can edit in this view is to display the study to parents who might be interested in participating. You can select a thumbnail image, give a brief description of the study (like you would to a parent on the phone or at the museum if you were recruiting), and define an age range or other eligibility criteria. The "Participant Eligibility" string is just a description and can be in any format you want (e.g. "for girls ages 3 to 5" is fine) but parents will only see a warning about study eligibility based on the minimum/maximum ages you set. Those can be in months, days, or years. Parents who try to participate will see a warning if their child is younger (asking them to wait if they can) or older (letting them know we won't be able to use their data) but are not actually prevented from participating.

You won't see your study on Lookit until it's started (made active). You can start/stop your study here on the detail page.

![example](_static/img/experimenter-detail-view.png)

Here are the corresponding study views on Lookit:

![example](_static/img/lookit-view-1.png)

![example](_static/img/lookit-view-2.png)

> Try it yourself: Make your own study on staging-experimenter, choose a thumbnail, and enter a description. Look on Lookit: you don't see it, because you haven't started the study yet. Start the study from Experimenter and refresh Lookit: there it is! 

Your study's unique ID can be seen in the URL as you view it from either Experimenter or Lookit.

### Experiment structure

To define what actually happens in your study, go to "Build Experiment" at the bottom of the detail page. In this "experiment editor" view, Experimenter provides an interface to define the structure of an experiment using a JSON document. This is composed of two segments:

- **structure**: a definition of the **frames** you want to utilize in your experiment. This must take the form of a JSON object, i.e. a set of key/value pairs.
- **sequence**: a list of keys from the **structure** object. These need not be unique, and items from **structure** may be repeated. This determines the order that **frames** in your experiment will be shown.

> *Note:* the term **frame** refers to a single segment of your experiment. Examples of this might be: a consent form, 
a survey, or some video stimulus. Hopefully this idea will become increasing clear as you progress through this guide.

To explain these concepts, let's walk through an example:

```json
{
    "frames": {
        "intro-video": {
            "kind": "exp-video",
            "sources": [
                {
                    "type": "video/webm",
                    "src": "https://s3.amazonaws.com/exampleexp/my_video.webm"
                },
                {
                    "type": "video/ogg",
                    "src": "https://s3.amazonaws.com/exampleexp/my_video.ogg"
                },
                {
                    "type": "video/mp4",
                    "src": "https://s3.amazonaws.com/exampleexp/my_video.m4v"
                }
            ]
        },
        "survey-1": {
            "formSchema": "URL:https://s3.amazonaws.com/exampleexp/survey-1.json",
            "kind": "exp-survey"
        },
        "survey-2": {
            "formSchema": "URL:https://s3.amazonaws.com/exampleexp/survey-2.json",
            "kind": "exp-survey"
        },
        "survey-3": {
            "formSchema": "URL:https://s3.amazonaws.com/exampleexp/survey-3.json",
            "kind": "exp-survey"
        },
        "survey-randomizer": {
            "options": [
                "survey-1",
                "survey-2",
                "survey-3"
            ],
            "sampler": "random",
            "kind": "choice"
        },
        "exit-survey": {
            "formSchema": "URL:https://s3.amazonaws.com/exampleexp/exit-survey.json",
            "kind": "exp-survey"
        }
    },
    "sequence": [
        "intro-video",
        "survey-randomizer",
        "exit-survey"
    ]
}

```

This JSON document describes a fairly simple experiment. It has three basic parts (see 'sequence'):

1. intro-video: A short video clip that prepares participants for what is to come in the study. Multiple file formats
 are specified to support a range of web browsers.
2. survey-randomizer: A **frame** that randomly selects from one of the three 'options', in this case 'survey-1', 
  'survey-2', or 'survey-3'. The `"sampler": "random"` setting tells Experimenter to simply pick of of the options at 
  random. Other supported options are described [here](http://centerforopenscience.github.io/exp-addons/modules/randomizers.html).
3. exit-survey: A simple post-study survey. Notice for each of the **frames** with `"type": "exp-survey"` there is 
  a `formSchema` property that specifies the URL of another JSON schema to load. This corresponds with the input data 
  expected by [Alpaca Forms](http://www.alpacajs.org/documentation.html). An example of one of these schemas is below:
  
```json
{
    "schema": {
        "title": "Survey One",
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "title": "What is your name?"
            },
            "favColor": {
                "type": "string",
                "title": "What is your favorite color?",
                "enum": ["red", "orange", "yellow", "green", "blue", "indigo", "violet"]
            }
        }
    }
}

```


### A Lookit study schema

A typical Lookit study might contain the following frame types:

1. exp-video-config
2. exp-video-consent
3. exp-lookit-text
4. exp-lookit-preview-explanation
5. exp-video-preview
6. exp-lookit-mood-questionnaire
7. exp-video-config-quality
8. exp-lookit-instructions
9. [Study-specific frames, e.g. exp-lookit-geometry-alternation, exp-lookit-story-page, exp-lookit-preferential-looking, exp-lookit-dialogue-page; generally, a sequence of these frames would be put together with a randomizer]
10. exp-lookit-exit-survey

For now, before any fullscreen frames, a frame that extends exp-frame-base-unsafe (like exp-lookit-instructions) needs to be used so that the transition to fullscreen works smoothly. A more flexible way to achieve this behavior is in the works!

### Randomizer frames

Generally, you'll want to show slightly different versions of the study to different participants: perhaps you have a few different conditions, and/or need to counterbalance the order of trials or left/right position of stimuli. To do this, you'll use a special frame called a **randomizer** to select an appropriate sequence of frames for a particular trial. A randomizer frame can be automatically expanded to a list of frames, so that for instance you can specify your 12 looking-time trials all at once.

For complete documentation of available randomizers, see [http://centerforopenscience.github.io/exp-addons/modules/randomizers.html](http://centerforopenscience.github.io/exp-addons/modules/randomizers.html).

To use a randomizer frame, you set `"kind"` to `"choice"` and `"sampler"` to the appropriate type of randomizer. The most common type of randomizer you will use is called [random-parameter-set](http://centerforopenscience.github.io/exp-addons/classes/randomParameterSet.html). 

To select this randomizer, you need to define a frame that has the appropriate `"kind"` and `"sampler"`:

```json

"frames": {
    "test-trials": {
        "sampler": "random-parameter-set",
        "kind": "choice",
        "id": "test-trials",
        ...
    }
}
```

There are three special properties you need to define to use `random-parameter-set`: `frameList`, `commonFrameProperties`, and `parameterSets`. 

`frameList` is just what it sounds like: a list of all the frames that should be generated by this randomizer. Each frame is a JSON object just like you would use in the overall schema, with two differences:

- You can define default properties, to share across all of the frames generated by this randomizer, in the JSON object `commonFrameProperties` instead, as a convenience.

- You can use placeholder strings for any of the properties in the frame; they will be replaced based on the values in the selected `parameterSet`.

`parameterSets` is a list of mappings from placeholder strings to actual values. When a participant starts your study, one of these sets will be randomly selected, and any parameter values in the `frameList` (including `commonFrameProperties`) that match any of the keys in this parameter set will be replaced.

Let's walk through an example of using this randomizer. Suppose we start with the following study JSON schema:

```json
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
```

But what we really want to do is have some kids think about how tasty broccoli is, and others think about how yucky it is! We can use a `random-parameter-set` frame to replace both text frames:

```

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
```

Notice that since both of the frames in the `frameList` were of the same kind, we could define the kind in `commonFrameProperties`. We no longer define `id` values for the frames, as they will be automatically identified as `instruct-and-manip-1` and `instruct-and-manip-2`.

If we wanted to have 75% of participants think about how tasty broccoli is, we could also weight the parameter sets by providing the optional parameter `"parameterSetWeights": [3, 1]"` to the randomizer frame. 

> Note: One use of parameterSetWeights is to stop testing conditions that you already have enough children in as data collection proceeds.

#### Nested randomizers

The frame list you provide to the randomParameterSet randomizer can even include other randomizer frames! This allows you to, for instance, define a **trial** that includes several distinct **blocks** (say, an intro, video, and then 4 test questions), then show 10 of those trials with different parameters - without having to write out all 60 blocks. There's nothing "special" about doing this, but it can be a little more confusing. 

Here's an example. Notice that `"kind": "choice"`, `"sampler": "random-parameter-set"`, `"frameList": ...`, and `commonFrameProperties` are `commonFrameProperties` of the outer frame `nested-trials`. That means that every "frame" we'll create as part of `nested-trials` will itself be a random-parameter-set generated list with the same frame sequence, although we'll be substituting in different parameter values. (This doesn't have to be the case - we could show different types of frames in the list - but in the simplest case where you're using randomParameterSet just to group similar repeated frame sequences, this is probably what you'd do.) The only thing that differs across the two (outer-level) **trials** is the `parameterSet` used, and we list only one parameter set for each trial, to describe (deterministically) how the outer-level `parameterSet` values should be applied to each particular frame.

```json
    "nested-trials": {
        "kind": "choice",
        "sampler": "random-parameter-set",
        "commonFrameProperties": {
            "kind": "choice",
            "sampler": "random-parameter-set",
            "frameList": [
                {
                    "nPhase": 0,
                    "doRecording": false,
                    "autoProceed": false,
                    "parentTextBlock": {
                        "title": "Parents!",
                        "text": "Phase 0: instructions",
                        "emph": true
                    },
                    "images": [
                        {
                            "id": "protagonist",
                            "src": "PROTAGONISTFACELEFT",
                            "left": "40",
                            "bottom": "2",
                            "height": "60",
                            "animate": "fadein"
                        }       
                    ],
                    "audioSources": [
                        {
                            "audioId": "firstAudio",
                            "sources": [{"stub": "0INTRO"}]
                        }
                    ]
                },
                {
                    "nPhase": 1,
                    "doRecording": false,
                    "autoProceed": false,
                    "parentTextBlock": {
                        "title": "Parents!",
                        "text": "Phase 1: instructions",
                        "emph": true
                    },
                    "images": [
                        {
                            "id": "protagonist",
                            "src": "PROTAGONISTFACELEFT",
                            "left": "40",
                            "bottom": "2",
                            "height": "60"
                        }       
                    ],
                    "audioSources": [
                        {
                            "audioId": "firstAudio",
                            "sources": [{"stub": "1INTRO"}]
                        }
                    ]
                }
            ],
            "commonFrameProperties": {
                "kind": "exp-lookit-dialogue-page",
                "doRecording": true,
                "nTrial": "NTRIAL",
                "backgroundImage": "BACKGROUNDIMG",
                "baseDir": "https://s3.amazonaws.com/lookitcontents/politeness/",
                "audioTypes": ["mp3", "ogg"]
            }
        }, 
        "frameList": [
            {
                "parameterSets": [
                    {
                        "PROTAGONISTFACELEFT": "PROTAGONISTFACELEFT_1",
                        "BACKGROUNDIMG": "BACKGROUNDIMG_1",
                        "0INTRO": "0INTRO_1",
                        "1INTRO": "1INTRO_1",
                        "NTRIAL": 1
                    }
                ]
            },
            {
                "parameterSets": [
                    {
                        "PROTAGONISTFACELEFT": "PROTAGONISTFACELEFT_2",
                        "BACKGROUNDIMG": "BACKGROUNDIMG_2",
                        "0INTRO": "0INTRO_2",
                        "1INTRO": "1INTRO_2",
                        "NTRIAL": 2
                    }
                ]
            }
        ],
        "parameterSets": [
            {
                "PROTAGONISTFACELEFT_1": "order1_test1_listener1.png",
                "PROTAGONISTFACELEFT_2": "order1_test1_listener1_second.png",
                "BACKGROUNDIMG_1": "order1_test1_background.png",
                "BACKGROUNDIMG_2": "order1_test1_background.png",
                "0INTRO_1": "polcon_example_1intro",
                "1INTRO_1": "polcon_example_1intro",
                "0INTRO_2": "polcon_example_1intro",
                "1INTRO_2": "polcon_example_1intro"
            }
        ]
    }
```



### Testing your study

Experimenter has a built-in tool that allows you to try out your study. However, some functionality may not be exactly the same as on Lookit. We recommend testing your study from Lookit, which will be how participants experience it.
