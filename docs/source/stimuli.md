# Preparing your stimuli

### Audio and video files

Most experiments will involve using audio and/or video files! You are responsible for hosting these somewhere (contact MIT if you need help finding a place to put them).

For basic editing of audio files, if you don't already have a system in place, we highly recommend [Audacity](http://www.audacityteam.org/). You can create many "tracks" or select portions of a longer recording using labels, and export them all at once; you can easily adjust volume so it's similar across your stimuli; and the simple "noise reduction" filter works well.

### File formats

To have your media play properly across various web browsers, you will generally need to provide multiple file formats. For a comprehensive overview of this topic, see [MDN](https://developer.mozilla.org/en-US/docs/Web/HTML/Supported_media_formats). 

MIT's standard practice is to provide mp3 and ogg formats for audio, and webm and mp4 (H.264 video codec + AAC audio codec) for video, to cover modern browsers. The easiest way to create the appropriate files, especially if you have a lot to convert, is to use the command-line tool [ffmpeg](https://ffmpeg.org/). It's a bit of a pain to get used to, but then you can do almost anything you might want to with audio and video files. 

Here's an example command to convert a video file INPUTPATH to mp4 with reasonable quality/filesize and using H.264 & AAC codecs:

```ffmpeg -i INPUTPATH -c:v libx264 -preset slow -b:v 1000k -maxrate 1000k -bufsize 2000k -c:a libfdk_aac -b:a 128k```

And to make a webm file:

```ffmpeg -i INPUTPATH -c:v libvpx -b:v 1000k -maxrate 1000k -bufsize 2000k -c:a libvorbis -b:a 128k -speed 2```

Converting all your audio and video files can be easily automated in python. Here's an example script that uses ffmpeg to convert all the m4a and wav files in a directory to mp3 and ogg files:

```python
import os
import subprocess as sp
import sys

audioPath = '/Users/kms/Dropbox (MIT)/round 2/ingroupobligations/lookit stimuli/audio clips/'

audioFiles = os.listdir(audioPath)

for audio in audioFiles:
	(shortname, ext) = os.path.splitext(audio)
	print shortname
	if not(os.path.isdir(os.path.join(audioPath, audio))) and ext in ['.m4a', '.wav']:
		sp.call(['ffmpeg', '-i', os.path.join(audioPath, audio), \
		       os.path.join(audioPath, 'mp3', shortname + '.mp3')])
		sp.call(['ffmpeg', '-i', os.path.join(audioPath, audio), \
		       os.path.join(audioPath, 'ogg', shortname + '.ogg')])
```

### Directory structure

For convenience, several of the newer frames allow you to define a base directory (`baseDir`) as part of the frame definition, so that instead of providing full paths to your stimuli (including multiple file formats) you can give relative paths and specify the audio and/or video formats to expect (`audioTypes` and `videoTypes`). 

**Images**: Anything without `://` in the string is assumed to be a relative image source. 

**Audio/video sources**: you will be providing a list of objects describing the source, like this:

```json
[
    {
        "src": "http://stimuli.org/myAudioFile.mp3",
        "type": "audio/mp3"
    },
    {
        "src": "http://stimuli.org/myAudioFile.ogg",
        "type": "audio/ogg"
    }
]
```

Instead of listing multiple sources, which are generally the same file in different formats, you can alternately list a single source like this:

```json
[
    {
        "stub": "myAudioFile"
    }
]
```

If you use this option, your stimuli will be expected to be organized into directories based on type. 

- **baseDir/img/**: all images (any file format; include the file format when specifying the image path)
- **baseDir/ext/**: all audio/video media files with extension `ext`

**Example**: Suppose you set `baseDir: 'http://stimuli.org/mystudy/` and then specified an image source as `train.jpg`. That image location would be expanded to `http://stimuli.org/mystudy/img/train.jpg`. If you specified that the audio types you were using were `mp3` and `ogg` (the default) by setting `audioTypes: ['mp3', 'ogg']`, and specified an audio source as `[{"stub": "honk"}]`, then audio files would be expected to be located at `http://stimuli.org/mystudy/mp3/honk.mp3` and `http://stimuli.org/mystudy/ogg/honk.ogg`.
