## How to capture video in an experiment

The Experimenter platform provides a means to capture video of a participant during an experiment, using the 
computer's webcam.

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
