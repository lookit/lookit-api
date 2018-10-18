Setup for local frame development
=================================

Suppose that for your study, you need a frame that’s not part of the
standard exp-addons library. Maybe you want to use a particular game
you’ve already implemented in Javascript, or you want to slightly change
how one of the existing frames works, or you want to hard-code a
particular complicated counterbalancing scheme. That’s okay! You can add
a new frame to your own version of the exp-addons repository, and tell
Experimenter to use your Github fork of exp-addons when building your
study. But for efficiency, you will probably want to run Lookit on your
own computer as you implement your new frame, so that you can test out
changes immediately rather than repeatedly pushing your changes to
Github and re-building your study on Experimenter. These instructions
will walk you through setting up to run Lookit locally.

Overview
--------

Even though we will probably just be changing the frame definitions in
exp-addons, we will need to install *both* the the Django app
(``lookit-api``) and the Ember app (``ember-lookit-frameplayer``), tell
them how to talk to each other, and run both of those servers locally.
In Experimenter, we need to add an organization to our superuser, and
then add a child and demographic data. We then create a study locally.
The exp-player needs to be linked for local development, and a token
added to the headers of the API requests the
``ember-lookit-frameplayer`` is sending. We can then navigate directly
to the study from the ember app to bypass the build process locally.
This will enable you to make changes to frames locally and rapidly see
the results of those changes, participating in a study just as if you
were a participant on the Lookit website.

Django App steps
----------------

1. Follow the instructions to install the `django
   app <django-project-installation.html>`__ locally. Run the server.

2. Navigate to http://localhost:8000/admin/ to login to Experimenter’s
   admin app. You should be redirected to login. Use the superuser
   credentials created in the django installation steps.

3. Once you are in the Admin App, navigate to users, and then select
   your superuser. If you just created your django app, there should be
   two users to pick from, your superuser, and an anonymous user. In
   that case, your superuser information is here
   http://localhost:8000/admin/accounts/user/2/change/.

4. Update your superuser information through the admin app. We primarily
   need to add an organization to the user, but have to fill out the
   bold fields additionally in order to save the user information.

   -  Family Name: *Your last name*
   -  Organization: *Select MIT in dropdown. If no organizations are in
      the dropdown, create one through the admin app, and come back and
      add it here.*
   -  Identicon: *If no identicon, just type random text here*
   -  Timezone: *America/New_York, as an example*
   -  Locale: *en_US, as an example*
   -  Place a check in the checkbox by “Is Researcher”

   Click “Save”.

5. Create a token to allow the Ember app to access the API by navigating
   to http://localhost:8000/admin/authtoken/token/. Click “Add Token”,
   find your superuser in the dropdown, and then click “Save”. You will
   need this token later.

6. Create a study by navigating to
   http://localhost:8000/exp/studies/create/. Fill out all the fields.
   The most important field is the ``structure``, where you define the
   frames and the sequence of the frames. Be sure the frame and the
   details for the frame you are testing are listed in the structure.

7. Add demographic information to your superuser (just for testing
   purposes), so your superuser can participate in studies. Navigate to
   http://localhost:8000/account/demographics/. Scroll down to the
   bottom and hit “Save”. You’re not required to answer any questions,
   but hitting save will save a blank demographic data version for your
   superuser.

8. Create a child by navigating to
   http://localhost:8000/account/children/, and clicking “Add Child”.
   Fill out all the information with test data and click “Add child”.

Now we have a superuser with an organization, that has attached
demographic data, and a child. We’ve created a study, as well as a token
for accessing the API. Leave the django server running and switch to a
new tab in your console.

   Remember: The OAuth authentication used for access to Experimenter
   does not work when running locally. You can access Experimenter by
   first logging in as your superuser, or by giving another local user
   researcher permissions using the Admin app.

Ember App steps
---------------

1. Follow the instructions to install the `ember
   app <ember-app-installation.html>`__ locally.

2. If you are going to be making changes to frames, you should use
   ``npm link`` for local development. This allows you to make changes
   to the code without having to push to github. In the terminal:
   ``$ cd ember-lookit-frameplayer  $ npm link lib/exp-player`` If you
   make changes to the frames, you should see notifications that files
   have changed in the console where your ember server is running, like
   this:

   ::

      file changed components/exp-video-config/template.hbs

3. Add your token to the header. This will allow your Ember app to talk
   to your local API. In the ember-frame-player directory, open the
   application adapter directory at
   ``ember-lookit-frameplayer/app/adapters/application.js``. Add an
   “Authorization” key beneath the X-CSRFTOKEN line. The word ‘Token’
   must be included. Save the file.

   .. code:: js

      headers: Ember.computed(function() {
              // Add cookie to http header
              return {
                  'X-CSRFTOKEN': Ember.get(document.cookie.match(/csrftoken\=([^;]*)/), '1'),
                  'Authorization': 'Token <add-your-token-here>'
              };
          }).volatile(),

4. If you want to use the HTML5 video recorder, you’ll need to set up to
   use https locally. Open ``ember-lookit-frameplayer/.ember-cli`` and
   make sure it includes ``ssl: true``:

   .. code:: js

      "disableAnalytics": false,
      "ssl": true

   Create ``server.key`` and ``server.crt`` files in the root
   ``ember-lookit-frameplayer`` directory as follows:

   ::

      openssl genrsa -des3 -passout pass:x -out server.pass.key 2048
      openssl rsa -passin pass:x -in server.pass.key -out server.key
      rm server.pass.key
      openssl req -new -key server.key -out server.csr
      openssl x509 -req -sha256 -days 365 -in server.csr -signkey server.key -out server.crt

   Leave the challenge password blank and enter ``localhost`` as the
   Common Name.

5. Run the ember server.

Starting up once initial setup is completed
-------------------------------------------

This is much quicker! Once you have gotten through the initial setup
steps, you don’t need to go through them every time you want to work on
something.

1. Start the Django app:

   ::

      $ cd lookit-api
      $ source VENVNAME/bin/activate
      $ python manage.py runserver

2. Start the Ember app:

   ::

      $ cd ember-lookit-frameplayer
      $ ember serve

3. Log in as your local superuser at http://localhost:8000/admin/

Previewing a study
------------------

When you are previewing a study, the responses to the study will not be
saved. You will get an error at the end of the study about this - that’s
expected and not something to worry about. Video attachments will be
saved, however, with an id of “PREVIEW_DATA_DISREGARD”. You do not need
to create demographic data, or a child, since this is just a preview.
You just need a study to navigate to. The URL for previewing is
``/exp/studies/study_uuid/preview/``.

To fetch the identifier of the study, you can use the API. To fetch
studies, navigate to http://localhost:8000/api/v1/studies. Copy the id
of the study you created earlier.

Now, you can navigate to
https://localhost:4200/exp/studies/study_id/preview, replacing study_id
with the id you obtained from the API. (For simplicity, bookmark this
link while you’re working!)

Participating in a study
------------------------

To participate in a study locally, you need demographic data and a child
attached to the logged in user, as well as a study.

Responses are saved to your local server. The URL for participating is
``studies/study_uuid/child_uuid``. To fetch studies, navigate to
http://localhost:8000/api/v1/studies/. Copy the id of the study you
created earlier. To fetch children, navigate to
http://localhost:8000/api/v1/children/. Copy the id of your child.

Finally, to participate in a study, navigate to
https://localhost:4200/studies/study_id/child_id, replacing study_id and
child_id with the ids you obtained from the API. (For simplicity,
bookmark this link while you’re working!)

Where does my video go?
-----------------------

If you have set up the Pipe recorder environment variables as described
in `the installation instructions <ember-app-installation.html>`__,
video recorded during your local testing will go to Pipe and then to an
S3 bucket for Lookit development video. Contact us for directions about
accessing this bucket. [TODO: documentation on setting up access.]

Using https
-----------

You may need to adjust browser settings to allow using https with the
self-signed certificate. For instance, in Chrome, set Camera and
Microphone permissions at
chrome://settings/content/siteDetails?site=https://localhost:4200.

If not using https locally, replace the https://localhost:4200 addresses
with http://localhost:4200.
