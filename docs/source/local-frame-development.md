# Setup for local frame development

These are the instructions for previewing or participating in a study locally. We need to install the the django app and the ember app, and run both of those servers locally.  In Experimenter, we need to add an organization to our superuser, and then add a child and demographic data.  We then create a study locally.  We can then navigate directly to the study from the ember app to bypass the build process locally.

### Previewing
When you are previewing a study, the responses to the study will not be saved.  Video attachments will be saved, however, with an id of "PREVIEW_DATA_DISREGARD". You do not need to create demographic data, or a child, since this is just a preview.  You just need a study to navigate to.  The URL for previewing is `/exp/studies/study_uuid/preview/`.

### Participating
When you are participating in a study, you need to create demographic data and a child attached to the logged in user.  Video data is saved and responses are saved to your local server.  The URL for participating is `studies/study_uuid/child_uuid`.

## Django App steps
1. Install the [django app](django-project-installation.html) locally. Run the server.

2. Navigate to https://localhost:8000/admin/ to login to Experimenter's admin app. You should be redirected to login.  Use the superuser credentials created in the django installation steps.

3. Once you are in the Admin App, navigate to users, and then select the superuser you created.  If you just created your django app, there should be two users to pick from, your superuser, and an anonymous user. Your user information is here http://localhost:8000/admin/accounts/user/2/change/.

4. Update your superuser information through the admin app. The main thing we need to add is an organization to your user, but we must fill out the bold fields as well in order to save your user information.
    - Family Name: *Your last name*
    - Organization: *Select MIT in dropdown. If no organizations are in the dropdown, create one through the admin app, and come back and add it here.*
    - Identicon: *If no identicon, just type random text here*
    - Timezone: *American/New_York, as an example*
    - Locale: *en_US, as an example*
    - Place a check in the checkbox by "Is Researcher"
    Press "Save".

5. Create a token to allow the Ember app to access the API by navigating to http://localhost:8000/admin/authtoken/token/. Click "Add Token", find your superuser in the dropdown, and then click "Save". You will need this token later.

6. Create a study by navigating to http://localhost:8000/exp/studies/create/.  Fill out all the fields. The most
important field is the `structure`, where you define the frames and the sequence of the frames.

7. Add demographic information to your superuser (just for testing purposes), so your superuser can participate in studies. Navigate to  http://localhost:8000/account/demographics/.  Scroll down to the bottom and hit "Save". You're not required to answer any questions, but hitting save will save a blank demographic data version for your superuser.

8. Create a child by navigating to http://localhost:8000/account/children/, and clicking "Add Child".  Fill out all the information with test data and click "Add child".

Now we have a superuser with an organization, that has attached demographic data, and a child.  We've created a study, as well
as a token for accessing the API.  Leave the django server running and switch to a new tab in your console.

## Ember App steps

1. Install the [ember app](ember-app-installation.html) locally. Run the server.

2. If you are going to be making changes to frames, you should use npm link for local development. This allows you to make changes to the code without having to push to github.
In the terminal:
    ```
    $ cd ember-lookit-frameplayer
    $ npm link lib/exp-player
    ```
If you make changes to the frames, you should notifications that files have changed in the console where you are running your ember server:
`file changed components/exp-video-config/template.hbs`

3. Add your token to the header. This will allow your Ember app to talk to your local API. In the ember-frame-player directory, open the application adapter directory at `ember-lookit-frameplayer/app/adapters/application.js.` Add an "Authorization" key beneath the X-CSRFTOKEN line. Save the file.
    ```js
    headers: Ember.computed(function() {
            // Add cookie to http header
            return {
                'X-CSRFTOKEN': Ember.get(document.cookie.match(/csrftoken\=([^;]*)/), '1'),
                'Authorization': 'Token add-your-token-here'
            };
        }).volatile(),
    ```
4. To Preview a study, navigate to localhost:4200/exp/studies/study_uuid/preview.  To participate in a study, navigate to
localhost:4200/studies/study_uuid/child_uuid.
