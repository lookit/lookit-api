###############
Experimenter
###############

===========
Logging in
===========

Researchers should log into Experimenter via oauth through the Open Science Framework.  If running locally, visit `<http://localhost:8000/accounts/login/>`_.

.. image:: _static/img/login_to_exp.png
    :alt: Login to experimenter image

If you don't have an OSF account, click `register` to create one.
If you do have an OSF account, click the Open Science Framework link. Enter your OSF credentials.

.. image:: _static/img/osf-login.png
    :alt: Enter your osf credentials
    :width: 300
    :align: center

If you haven't yet been approved to join Experimenter, you'll receive a notification when this is done.

.. image:: _static/img/dashboard.png
    :alt: Login to experimenter image

Otherwise, you will be logged into Experimenter.

===========================
Managing your Organization
===========================
-----------------------------------------
Adding researchers to your organization
-----------------------------------------

Navigate to `Manage Organization` http://localhost:8000/exp/researchers/.  Only users with organization admin and organization read permissions can view other researchers in the org.
The researchers displayed are researchers that currently belong to your organization, or researchers still needing approval.  Researchers awaiting approval have "No organization groups" listed as the permission.
Navigate to a researcher awaiting approval (only organization admins are permitted to do this).

.. image:: _static/img/researcher_list.png
    :alt: Researcher list image


Under permissions at the bottom of the researcher detail page, select `Researcher`, `Organization Read`, or `Organization Admin` from the dropdown, and click the check mark.  This will give
that researcher the associated permissions and add them to your organization. They will receive an email notification.

.. image:: _static/img/researcher_detail.png
    :alt: Researcher detail image

------------------------------------------------
Editing a researcher's organization permissions
------------------------------------------------
Navigate to a particular researcher's detail page http://localhost:8000/exp/researchers/researcher_id.  Only organization admins can view this page. Under permissions at the bottom of the researcher detail page, select `Researcher`, `Organization Read`, or `Organization Admin` from the dropdown, and click the check mark.  This will modify
the researcher's positions.

.. image:: _static/img/researcher_detail2.png
    :alt: Researcher detail image

------------------------------------------------
Deleting a researcher's organization permissions
------------------------------------------------
Navigate to `Manage Organization` http://localhost:8000/exp/researchers/. Only users with organization admin and organization read permissions can view other researchers in the org.  Click "Remove" beside the
researcher you wish to delete, and then click "Remove" again in the confirmation modal.  The researcher will be marked as inactive and will no longer be permitted to login to Experimenter.

.. image:: _static/img/deleting_a_researcher.png
    :alt: Deleting a researcher

====================
Managing Studies
====================
--------------------
Creating a study
--------------------
To create a study, navigate to http://localhost:8000/exp/studies/create/. A researcher must have been added to an organization to add a study.
Here's an explanation of some the field names:

- *Name*: title of your study, must be <255 characters
- *Image*: Image that will be displayed to participants on Lookit Studies page.  File must be an image-type, and please keep the file size reasonable (<1 MB)
- *Exit URL*: Must enter a URL. After the participant has completed the study, we will direct them to the Exit URL.
- *Participant Eligibility*: Participant-facing eligibility string.  Make this readable so participants understand if their child can take part in the study.
- *Minimum/Maximum Age cutoffs*: Integer fields that give a warning to the participant if their child falls outside of the age range. It is a hard cutoff. If you say 3 to 5 years, child must be just greater than 3 years and just less than 5 years.  So if they're a day before their fifth birthday, they are eligibile.
- *Discoverable* - Do you want to make this study public or not?  If marked discoverable, once the study is activated, it will appear on the Lookit site.
- *Build Study* - This needs to be a valid JSON block describing the different frames (pages) of your study, and the sequence. You can add these later under localhost:8000/exp/studies/study_id/edit/build/.
- *Study Type* - This indicates the type of frame player that you wish to cycle through the pages in your experiment. Right now, we just have one option, the Ember Frame Player.
    - The *addons_repo_url* is the repo where the frames and the player are stored.  This is the default addons_repo_url: https://github.com/centerforopenscience/exp-addons.  If you want to add new frames, fork this repo, and use your fork.
    - The *last_known_addons_sha* is the commit of your addons_repo_url that you want to point to.
    - The *last_known_player_sha* is the commit of the ember app https://github.com/CenterForOpenScience/ember-lookit-frameplayer that talks to our API and passes that info onto the frame player
    - ** If you don't want any customization and want to use the existing player and frames, just select the defaults and press "Create study"

.. image:: _static/img/create_study.png
    :alt: Creating a study
