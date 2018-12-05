#!/bin/sh
echo "*** BEGINNING BUILD ***"
mkdir -p deployments/$STUDY_UUID && cd deployments
cp -Rv /checkouts/frameplayer_exp_bundle/dist/* $STUDY_UUID
chown -Rv www-data:www-data $STUDY_UUID
echo "*** DONE ***"
