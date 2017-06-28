#   - pull the study model instance
#   - check to see if it is simple or advanced
#   - simple:
#       - save sha of current head of ember experimenter to study model instance
#       - save sha of current head of ember addons to study model instance
#       - create a build directory based on the uuid of the study and a timestamp
#       - create package.json referencing those as dependencies
#       - use yarn or npm to install dependencies
#       - ember-build to create a packagable application
#       - zip up packaged application
#       - create folder on s3 bucket
#       - transfer files to folder on s3 bucket
#       - save the url of the s3 bucket folder in study model instance
#       - send notification that deployment is completed
#   - advanced:
#       - user uploads a file with experiment
#       - file is saved in temporary location
#       - file is extracted to a temporary location
#       - create folder on s3 bucket
#       - transfer files to folder on s3 bucket
#       - save the url of the s3 bucket folder in the study model instance
#       - send notification that deployment is complete
#   - preview
#       - create a random build folder name based on the uuid of the study and a timestamp
#       - Do the deployment steps without copying to s3
#       - launch a new browser window at proxy view that requires login to the url of the temporary build folder
#       - task to clean up the temporary build folders nightly, weekly, monthly?
