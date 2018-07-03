# Ember App Local Installation

This is a small Ember application that allows both researchers to preview an experiment and users to
participate in an experiment. This is meant to be used in conjunction with the [Lookit API Django project](https://github.com/CenterForOpenScience/lookit-api), which contains the Experimenter and Lookit applications.
The Django applications will proxy to these Ember routes for previewing/participating in an experiment.
The Ember routes will fetch the appropriate models and then pass them to the exp-player component in [exp-addons](https://github.com/CenterForOpenScience/exp-addons).

## Note: These instructions are for Mac OS.

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

Create or open a file named '.env' in the root of the ember-lookit-frameplayer directory, 
and add the following entries to use the Pipe WebRTC-based recorder: `PIPE_ACCOUNT_HASH` 
(reference to account to send video to) and `PIPE_ENVIRONMENT` (which environment, e.g. 
staging or production). These are available upon request.

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
