#!/bin/sh
# copy git checkout into local env for faster development
# could probably be removed in production
cp -r $CHECKOUT_DIR /checkout-dir/

sed -i "s/prepend: ''/$REPLACEMENT/g" /checkout-dir/ember-cli-build.js
sed -i "s/VideoRecorder.swf/$RECORDER_REPLACEMENT/g" /checkout-dir/lib/exp-player/addon/services/video-recorder.js

# Copy in required files
cp /environment /checkout-dir/.env
cp /VideoRecorder.swf /checkout-dir/public/

cd /checkout-dir/lib/exp-player
# install requirements for exp-player
yarn --frozen-lockfile
./node_modules/.bin/bower install --allow-root

cd /checkout-dir
# install requirements for ember-frame-player
yarn --frozen-lockfile
./node_modules/.bin/bower install --allow-root
# build ember app
./node_modules/.bin/ember build --environment=production

# clean up the old one
rm -rf $STUDY_OUTPUT_DIR
mkdir -p $STUDY_OUTPUT_DIR
# copy the built ember app into the output dir
cp -r /checkout-dir/dist/* $STUDY_OUTPUT_DIR
