# Glossary of Experimental Components

For the most current documentation of individual frames available to use, please see [http://centerforopenscience.github.io/exp-addons/modules/frames.html](http://centerforopenscience.github.io/exp-addons/modules/frames.html) and [http://centerforopenscience.github.io/exp-addons/modules/randomizers.html](http://centerforopenscience.github.io/exp-addons/modules/randomizers.html).


For each frame, you will find an **example** of using it in a JSON schema; documentation of the **properties** which can be defined in the schema; and, under Methods / serializeContent, a description of the **data** this frame records. Any frame-specific **events** that are recorded and may be included in the eventTimings object sent with the data are also described.

The below documentation may be out-of-date.

### general patterns

##### text-blocks

Many of these components expect one or more parameters with the structure:
```json
{
   "title": "My title",
   "text": "Some text here",  // optional
   "markdown": "Some markdown text here" // optional
}
```

This pattern will be referred to in the rest of this document as a 'text-block'. Note: a text-block may 
specify _either_ a  'text' property or a 'markdown' property. The 'text' property supports lightweight formatting 
using the '\n' character to create a newline, and '\t' to create indentation. The 'markdown' property will be 
formatted as [markdown](http://daringfireball.net/projects/markdown/).

##### remote-resources

Some items support loading additional content from a remote resource. This uses the syntax:

`(JSON|URL):<url>`

where the `JSON:` prefix means the fetched content should be parsed as JSON, and the `URL:` prefix should be 
interpreted as plain text. Examples are:

`"formSchema": "JSON:https://s3.amazonaws.com/exampleexp/my_survey.json"`

and

`"text": "URL:https://s3.amazonaws.com/exampleexp/consent_text.txt"`

### exp-audioplayer

> Play some audio for the participant. Optionally some some images while the audio is playing.

[view source code](https://github.com/CenterForOpenScience/exp-addons/blob/develop/exp-player/addon/components/exp-audioplayer.js)

##### example

![example](_static/img/exp-audioplayer.png)

```json
{
    "kind": "exp-audioplayer",
    "autoplay": false,
    "fullControls": true,
    "mustPlay": true,
    "images": [],
    "prompts": [{
        "title": "Instead of a consent form...",
        "text": "Here's a helpful tip."
    }, {
        "title": "A horse is a horse",
        "text": "But please don't say that backwards."
    }],
    "sources": [{
        "type": "audio/ogg",
        "src": "horse.ogg"
    }]
}
```

##### parameters

- **autoplay**: whether to autoplay the audio on load
  - type: true/false
  - default: true
- **fullControls**: whether to use the full player controls. If false, display a single button to play audio from the start.
  - type: true/false
  - default: true
- **mustPlay**: should the participant be forced to play the clip before leaving the page?
  - type: true/false
  - default: true
- **sources**: list of objects specifying audio src and type
  - type: list
  - default: empty
- **title**:  a title to show at the top of the frame
  - type: text
  - default: empty
- **titlePrompt**: a title and description to show at the top of the frame
  - type: text-block
  - default empty
- **images**: a list of objects specifying image src, alt, and title
  - type: list
  - default: empty
- **prompts**: text of any header/prompt paragraphs to show the participant
  - type: list of text-blocks
  - default: empty

##### data

- **didFinishSound**: did the use play through the sound all of the way?
  - type: true/false

- - -

### exp-consent

> A simple consent form. Forces the participant to accept before continuing.

[view source code](https://github.com/CenterForOpenScience/exp-addons/blob/develop/exp-player/addon/components/exp-consent.js)

##### example

![example](_static/img/exp-consent.png)

```json
{
    "kind": "exp-consent",
    "title": "Just checking",
    "body": "Are you sure you know what you're getting into?",
    "consentLabel": "I'm sure."
}
```

##### parameters

- **title**: a title for the consent form
  - type: text
  - default: 'Notice of Consent'
- **body**: body text for the consent form
  - type: text
  - default: 'Do you consent to take this experiment?'
- **consentLabel**: a label next to the consent form checkbox
  - type: text
  - default: 'I agree'

##### data

- **consentGranted**: did the participant grant consent?
  - type: true/false

- - -

### exp-info

> Show some text instructions to the participant.

[view source code](https://github.com/CenterForOpenScience/exp-addons/blob/develop/exp-player/addon/components/exp-info/component.js)

##### example

![example](_static/img/exp-info.png)

```json
{
    "kind": "exp-info",
    "title": "For yor information",
    "blocks": [{
        "title": "Example 1.",
        "text": "This is just an example."
    }, {
        "title": "Example 2.",
        "text": "And this is another example"
    }]
}
```

##### parameters

- **title**: a title to go at the top of this block
  - type: text
  - default: empty
- **blocks**: a list of text-blocks to show
  - type: list of text-blocks
  - default: empty

##### data

None

- - -

### exp-survey

> Presents the participant with a survey.

[view source code](https://github.com/CenterForOpenScience/exp-addons/blob/develop/exp-player/addon/components/exp-survey/component.js)

##### example

![example](_static/img/exp-survey.png)

```json
{
    "kind": "exp-survey",
    "formSchema": {
        "schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "title": "What is your name?"
                },
                "favColor": {
                    "type": "string",
                    "enum": [
                        "red",
                        "orange",
                        "yellow",
                        "green",
                        "blue",
                        "indigo",
                        "violet"
                    ],
                    "title": "What is your favorite color?"
                }
            },
            "title": "Survey One"
        }
    }
}
```

##### parameters

- **formSchema**: a JSON Schema defining a form; uses [Alpaca Forms](http://www.alpacajs.org/)
  - type: object (JSON Schema) or remote-resource
  - default: empty

##### data

- **formData**: an object mapping to the properties defined in **formSchema**
  - type: object

- - -

### exp-video-config

> Help guide the participant through setting up her webcam.

[view source code](https://github.com/CenterForOpenScience/exp-addons/blob/develop/exp-player/addon/components/exp-video-config.js)

##### example

![example](_static/img/exp-video-config.png)

```json
{
    "kind": "exp-video-config",
    "instructions": "Please make sure your webcam and microphone are functioning correctly."
}
```

##### parameters

- **instructions**: some instructions to show the participant
  - type: text
  - default: 'Configure your video camera for the upcoming sections. Press next when you are finished.'

##### data

None

- - -

### exp-video-consent

> present the participant with a written consent document then capture her spoken consent

[view source code](https://github.com/CenterForOpenScience/exp-addons/blob/develop/exp-player/addon/components/exp-video-consent.js)

##### example

![example](_static/img/exp-video-consent-1.png)
![example](_static/img/exp-video-consent-2.png)

```json
{
    "kind": "exp-video-consent",
    "prompt": "I give my consent to participate in this study",
    "blocks": [{
        "text": "The purpose of this study is to learn about ...",
        "title": "Introduction"
    }, {
        "text": "We will not share your personal information with anyone.",
        "title": "Privacy"
    }],
    "title": "Notice of consent"
}
```

##### parameters

- **title**:  title of written consent
  - type: text
  - default: 'Notice of Consent'
- **blocks**: text-blocks of written consent
  - type: list of text-blocks
  - default: []
- **prompt**: a prompt to show for spoken consent
  - type: text
  - default: 'I consent to participate in this study'

##### data

- **videoId**: this unique id of the captured video
  - type: text

- - -

### exp-video-preview

##### parameters
- **index**: the zero-based index of the first video to show
  - type: number
  - default: 0
- **videos**: a list of videos to preview
  - type: list of objects with a src and type property
  - default: []
- prompt: Require a button press before showing the videos
  - type: text
  - default: empty
- text: Text to display to the user
 - type: text-block
 - default: Empty

##### data

None


