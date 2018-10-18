How to capture video in your frame
----------------------------------

Webcam video recording during Lookit frames is currently accomplished
using WebRTC as the interface to the webcam and
`Pipe <https://addpipe.com/>`__ for video streaming and processing.

Lookit frames that collect video data make use of an Ember mixin
``VideoRecord`` included in exp-addons, which makes a
``VideoRecorderObject`` available for use in the code for that frame.
This object includes methods for showing/hiding the webcam view,
starting/pausing/resuming/stopping video recording,
installing/destroying the recorder, and checking the current video
timestamp (see
https://lookit.github.io/exp-addons/classes/VideoRecorderObject.html).
The programmer designing a new frame can therefore flexibly indicate
when recording should begin and end, as well as recording video
timestamps for any events recorded during this frame (e.g., so that
during later data analysis, researchers know the exact time in the video
where a new stimulus was presented). The name(s) of any videos collected
during a particular frame as included in the session data recorded, to
facilitate matching sessions to videos; video filenames also include the
study ID, session ID, frame ID, and a timestamp.

To begin, you will want to add the ``VideoRecord`` mixin to your
experiment frame. This provides, but does not in itself activate, the
capability for your frame to record videos.

.. code:: javascript

   import ExpFrameBaseComponent from '../../components/exp-frame-base/component';
   import VideoRecord from '../../mixins/video-record';

   export default ExpFrameBaseComponent.extend(VideoRecord, {
       // Your code here
   });

Limitations
~~~~~~~~~~~

One technical challenge imposed by webcam video streaming is that a
connection to the server must be established before webcam recording can
be quickly turned on and off, and this process may take up to several
seconds. Each experiment frame records a separate video clip and
establishes a separate connection to the server, so frames must be
designed to wait for recording to begin before proceeding to a portion
of the trial where video data is required. This fits well with typical
study designs using looking time or preferential looking, where the
child’s attention is returned to the center of the screen between
trials; the first few seconds of the child watching the “attention
grabber” are not critical and we can simply ensure that the webcam
connection is established before proceeding to the actual experimental
trial. When collecting verbal responses, the study frame can simply
pause until the connection is established or, similarly, proceed with an
initial portion of the trial where video data is not required.

Currently, continuous webcam recording across frames is not possible on
Lookit; any periods of continuous recording must be within a single
frame. This is not a hard technical limitation, though.

How it works
~~~~~~~~~~~~

The VideoRecord mixin is how a new frame makes use of video recording
functionality. In turn, this mixin uses the video-recorder service,
which relies on `Pipe <https://addpipe.com/>`__. To set everything up
from scratch, e.g. if you’re creating Mookit, an online experimental
platform for cows, you’ll need to do the following:

-  Make a Pipe account, and get the account hash and environment ID
   where you want to send videos.

-  Create an Amazon S3 bucket (where video will be sent by Pipe, then
   renamed). Set up Pipe to send your videos to this bucket; you’ll need
   to create an access key that just allows putting videos in this
   bucket. Go to IAM credentials, and make a group with the following
   policy:

::

   {
       "Version": "2012-10-17",
       "Statement": [
           {
               "Sid": "VisualEditor0",
               "Effect": "Allow",
               "Action": "s3:ListAllMyBuckets",
               "Resource": "*"
           },
           {
               "Sid": "VisualEditor1",
               "Effect": "Allow",
               "Action": "s3:GetBucketLocation",
               "Resource": "arn:aws:s3:::*"
           },
           {
               "Sid": "VisualEditor2",
               "Effect": "Allow",
               "Action": "s3:PutObject",
               "Resource": [
                   "arn:aws:s3:::MYBUCKET/*",
                   "arn:aws:s3:::MYBUCKET"
               ]
           }
       ]
   }

Then make a user, and add it to your new group. Use the keys for this
user in Pipe.

-  Create a webhook key in Pipe, and store it in as ``PIPE_WEBHOOK_KEY``
   in the lookit-api Django app .env file. This will let Lookit rename
   the video files to something sensible upon being uploaded to S3.

-  Create a webhook in Pipe for the event video_copied_s3, and send it
   to ``https://YOURAPP/exp/renamevideo/``

-  Store the ``PIPE_ACCOUNT_HASH`` and ``PIPE_ENVIRONMENT`` in the
   ember-lookit-frameplayer .env file. This is what lets Lookit video go
   to the right Pipe account.
