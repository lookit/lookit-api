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

===========================================
Adding researchers to your organization
===========================================

Navigate to `Manage Organization` http://localhost:8000/exp/researchers/.  Only users with organization admin and organization read permissions can view other researchers in the org.
The researchers displayed are researchers that currently belong to your organization, or researchers still needing approval.  Researchers awaiting approval have "No organization groups" listed as the permission.
Navigate to a researcher awaiting approval (only organization admins are permitted to do this).

.. image:: _static/img/researcher_list.png
    :alt: Researcher list image


Under permissions at the bottom of the researcher detail page, select `Researcher`, `Organization Read`, or `Organization Admin` from the dropdown, and click the check mark.  This will give
that researcher the associated permissions and add them to your organization. They will receive an email notification.

.. image:: _static/img/researcher_detail.png
    :alt: Researcher detail image
