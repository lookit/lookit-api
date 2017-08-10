#!/bin/sh
cp -r /checkouts/$CHECKOUT_DIR/ /checkout-dir/

cp /environment /checkout-dir/.env
cp /VideoRecorder.swf /checkout-dir/public/

cd /checkout-dir
yarn install --pure-lockfile
bower install --allow-root

cd /checkout-dir/lib/exp-player
yarn install --pure-lockfile
bower install --allow-root

cd /checkout-dir/
ember build

mkdir -p /deployments/$STUDY_OUTPUT_DIR/
cp -r /checkout-dir/dist/* /deployments/$STUDY_OUTPUT_DIR/
