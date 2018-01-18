## How to capture video in an experiment

Webcam video recording during Lookit frames is currently accomplished using Flash as the interface to the webcam, and [HDFVR](https://hdfvr.com/) for Javascript and server-side APIs that support options such as setting preferred audio and video quality and codecs. This will change as soon as possible to HTML5.

Lookit frames that collect video data make use of an Ember mixin `VideoRecord` included in exp-addons, which makes a `VideoRecorderObject` available for use in the code for that frame. This object includes methods for showing/hiding the webcam view,  starting/pausing/resuming/stopping video recording, installing/destroying the recorder, and checking the current video timestamp (see http://centerforopenscience.github.io/exp-addons/classes/VideoRecorderObject.html). The programmer designing a new frame can therefore flexibly indicate when recording should begin and end, as well as recording video timestamps for any events recorded during this frame (e.g., so that during later data analysis, researchers know the exact time in the video where a new stimulus was presented). The name(s) of any videos collected during a particular frame as included in the session data recorded, to facilitate matching sessions to videos; video filenames also include the study ID, session ID, frame ID, and a timestamp. 

To begin, you will want to add the `VideoRecord` mixin to your experiment frame. This provides, but does not in itself 
activate, the capability for your frame to record videos.

```javascript
import ExpFrameBaseComponent from '../../components/exp-frame-base/component';
import VideoRecord from '../../mixins/video-record';

export default ExpFrameBaseComponent.extend(VideoRecord, {
    // Your code here
});
```

Within that frame, you will need some boilerplate that decides how to activate the recorder, and when to start recording.
Below is an example from `exp-video-physics`, which starts recording immediately, and makes a copy of the recorder 
available on the component so that you can use additional helper methods (like show, hide, and getTime) as appropriate 
to deal with recording problems.

```javascript
    didInsertElement() {
        this._super(...arguments);

        if (this.get('experiment') && this.get('id') && this.get('session') && !this.get('isLast')) {
            let recorder = this.get('videoRecorder').start(this.get('videoId'), this.$('#videoRecorder'), {
                hidden: true
            });
            recorder.install({
                record: true
            }).then(() => {
                this.sendTimeEvent('recorderReady');
                this.set('recordingIsReady', true);
            });
            recorder.on('onCamAccess', (hasAccess) => {
                this.sendTimeEvent('hasCamAccess', {
                    hasCamAccess: hasAccess
                });
            });
            recorder.on('onConnectionStatus', (status) => {
                this.sendTimeEvent('videoStreamConnection', {
                    status: status
                });
            });
            this.set('recorder', recorder);
        }
    },
```

Make sure to stop the recording when the user leaves the frame! You can ask the user to do this manually, or it can be 
done automatically via the following:

```javascript
    willDestroyElement() { // remove event handler
        // Whenever the component is destroyed, make sure that event handlers are removed and video recorder is stopped
        if (this.get('recorder')) {
            this.get('recorder').hide(); // Hide the webcam config screen
            this.get('recorder').stop();
        }

        this.sendTimeEvent('destroyingElement');
        this._super(...arguments);
        // Todo: make removal of event listener more specific (in case a frame comes between the video and the exit survey)
        $(document).off('keyup');
    }
```

### Limitations

One technical challenge imposed by webcam video streaming is that a connection to the server must be established before webcam recording can be quickly turned on and off, and this process may take up to several seconds. Each experiment frame records a separate video clip and establishes a separate connection to the server, so frames must be designed to wait for recording to begin before proceeding to a portion of the trial where video data is required. This fits well with typical study designs using looking time or preferential looking, where the child’s attention is returned to the center of the screen between trials; the first few seconds of the child watching the “attention grabber” are not critical and we can simply ensure that the webcam connection is established before proceeding to the actual experimental trial. When collecting verbal responses, the study frame can simply pause until the connection is established or, similarly, proceed with an initial portion of the trial where video data is not required. Currently, however, continuous webcam recording across frames is not possible on Lookit; any periods of continuous recording must be within a single frame. 

### Troubleshooting
If you are building a new ember app on this platform from scratch, you will need to do some setup to make video 
recording work. Because this relies on licensed software, it is not part of the default repository to be checked out.

1. Video recorder flash plugin (HDFVR): This is a Flash plugin that handles video recording. It requires a license; MIT 
  can provide both the license and the required file. See README.md install instructions for details.
2. Config string: MIT must provide you with the values of `WOWZA_PHP='{}'` and `WOWZA_ASP='{}'` that you will need to 
  place inside your `.env` file (as described in the project **README** file). This describes a WOWZA server backend 
  that has been configured to receive and process video clips. 
3. If you encounter problems finding the HDFVR video plugin, you may need to add the following markup to your 
  index.html file: `<base href="/" />` 
