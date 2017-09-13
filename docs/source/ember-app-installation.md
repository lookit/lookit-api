# Ember App Installation

This is a small Ember application that allows both researchers to preview an experiment and users to
participate in an experiment. This is meant to be used in conjunction with the [Lookit API Django project](https://github.com/CenterForOpenScience/lookit-api), which contains the Experimenter and Lookit applications.
The Django applications will proxy to these Ember routes for previewing/participating in an experiment.
The Ember routes will fetch the appropriate models and then pass them to the exp-player component in [exp-addons](https://github.com/CenterForOpenScience/exp-addons).

## Prerequisites

You will need the following things properly installed on your computer.

* [Git](http://git-scm.com/)
* [Node.js](http://nodejs.org/) (with NPM)
* [Bower](http://bower.io/)
* [Ember CLI](http://ember-cli.com/)
* [PhantomJS](http://phantomjs.org/)

## Installation

Before beginning, you will need to install Yarn, a package manager (like npm).

```bash
 git clone https://github.com/CenterForOpenScience/ember-lookit-frameplayer.git
 cd ember-lookit-frameplayer
 git submodule init
 git submodule update
 yarn install --pure-lockfile
 bower install

 cd lib/exp-player
 yarn install --pure-lockfile
 bower install
```

Create or open a file named '.env' in the root of the ember-lookit-frameplayer directory, and add the following entries:

```
WOWZA_PHP='{"minRecordTime":1,"showMenu":"false","showTimer":"false","enableBlinkingRec":1,"skipInitialScreen":1,"recordAgain":"false","showSoundBar":"true","hideDeviceSettingsButtons":1,"microphoneGain": 60,"connectionstring":"CONNECTIONSTRING"}'
WOWZA_ASP='{"showMenu":"false","loopbackMic":"true","skipInitialScreen":1,"showSoundBar":"true","snapshotEnable":"false"}'
```
A more complete configuration string is available upon request. In this application, we typically use WOWZA_PHP for settings in which a video is actually recorded, and WOWZA_ASP for video preview screens where no video is to be saved. The value of connectionstring is available internally but not committed to Github; it must be replaced with a reference to the streaming server. Other settings are as described in the sample avc_settings.php file provided in the HDFVR installation zip file.

## Video Recording
If you are using this ember app in conjunction with [lookit-api](https://github.com/CenterForOpenScience/lookit-api), the video recording functionality is taken care of in that repo. If you are not using lookit-api, and wish to use the video capture facilities of Lookit, you will need to place the file `VideoRecorder.swf`
in your `ember-lookit-frameplayer/public/` folder.  This file can be found in the [ember-build](https://github.com/CenterForOpenScience/lookit-api/tree/develop/ember_build) directory of lookit-api.

## Running / Development

* `ember serve`
* Visit your app at [http://localhost:4200](http://localhost:4200).

### Code Generators

Make use of the many generators for code, try `ember help generate` for more details

### Running Tests

* `ember test`
* `ember test --server`

### Building

* `ember build` (development)
* `ember build --environment production` (production)
