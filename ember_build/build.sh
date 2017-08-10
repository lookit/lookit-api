#!/bin/sh
# copy git checkout into local env for faster development
# could probably be removed in production
cp -r /checkouts/$CHECKOUT_DIR/ /checkout-dir/

# Copy in required files
cp /environment /checkout-dir/.env
cp /VideoRecorder.swf /checkout-dir/public/

cd /checkout-dir
# install requirements for ember-frame-player
yarn install --pure-lockfile
bower install --allow-root

cd /checkout-dir/lib/exp-player
# install requirements for exp-player
yarn install --pure-lockfile
bower install --allow-root

cd /checkout-dir/
# build ember app
ember build

# clean up the old one
rm -rf /deployments/$STUDY_OUTPUT_DIR/
mkdir -p /deployments/$STUDY_OUTPUT_DIR/
# copy the built ember app into the output dir
cp -r /checkout-dir/dist/* /deployments/$STUDY_OUTPUT_DIR/
