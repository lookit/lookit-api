# Development: Mixins of premade functionality

Sometimes, you will wish to add a preset bundle of functionality to any arbitrary experiment frame. The Experimenter
platform provides support for this via *mixins*. Below is a brief introduction to each of the common mixins;
see sample usages throughout the exp-addons codebase. More documentation may be added in the future.


## FullScreen
This mixin is helpful when you want to show something (like a video) in fullscreen mode without distractions.
You will need to specify the part of the page that will become full screen. By design, most browsers require that you
interact with the page at least once before full screen mode can become active.

## MediaReload
If your component uses video or audio, you will probably want to use this mixin. It is very helpful if you ever expect
to show two consecutive frames of the same type (eg two physics videos, or two things that play an audio clip). It
automatically addresses a quirk of how ember renders the page; see [stackoverflow post](http://stackoverflow.com/a/18454389/1422268)
for more information.

## VideoPause
Functionality related to pausing a video when the user presses the spacebar.

## VideoRecord
Functionality related to video capture, in conjunction with the HDFVR/ Wowza system (for which MIT has a license).
