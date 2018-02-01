###########
Definitions
###########

Children
--------
Children belonging to Participants.  Many Studies on Organization Sites involve testing the behavior of children.  The Participant registering the child must be the child's parent or legal guardian.  A Child can only belong to one Participant.

Demographic Data
----------------
When Participants create accounts on an Organization Site, they are asked to fill out a demographic survey. Demographic Data is versioned, so if Participants update their
Demographic Data, a new version is saved. When Participants take part in a study, the latest version of Demographic Data is linked to their study Response.

Experimenter
------------
Application where Researchers develop Studies, request to post Studies to an Organization Site, and access data collected.

Feedback
--------
Researchers can leave Feedback to Participants via the API about a particular Response to a Study.  The Participant can view this Feedback on the Past Studies page.

Groups
------
Each Organization and each Study will have one group for each set of permissions. Groups are an easy way to manage many permissions. These groups will be created automatically when an Organization or Study is created.
For example, if we have an Organization called MIT, then there will be an MIT_ORG_ADMIN, MIT_ORG_READ, and MIT_ORG_RESEARCHER group.  A Researcher belonging to any of these groups will
inherit all of the permissions associated.  Members of MIT_ORG_ADMIN can edit any Study in MIT, while MIT_ORG_READ members can only view Studies within MIT.  Members of MIT_ORG_RESEARCHER
can create Studies but can only view Studies they have specific permission to view.

When a Study is created, two permission groups will also be created for it.  If you create a Study called "Apples", and you belong to the MIT Organization, the groups created will be
MIT_APPLES_<STUDY_ID>_STUDY_ADMIN and MIT_APPLES_<STUDY_ID>_STUDY_READ.  The Study's creator is automatically added to the Study's admin group.  Researchers belonging to a Study's
admin or Study's read group will inherit the associated permissions to that Study.

Organization
------------
An institution (e.g., Lookit) or lab that has been registered with Experimenter.  Each Organization has its own interface (Organization Site) where Studies are posted.
All Organizations' data are separate.  Each Organization has their own Researchers, admins, Studies, Participants, etc.  You can only
view data that you have permission to see (depending on your admin/read/researcher permissions), and only data within your Organization.

Organization Site
------------------
One instance of a front-end where studies are posted. (Example: lookit.mit.edu)

Participants
------------
Account holders - registered Lookit users who can take part in studies. 'Participant' refers to the account (generally held by a parent) rather than the individual child. 

Researchers
-----------
Individuals posting Studies, collecting data, or administrating Organization Sites.

Responses
---------
When a Participant takes part in a study, the answers to their questions, as well as other metadata like the time taking the study, are saved in a Response.  In addition,
many Responses are associated with video attachments.

Study
------
An experiment posted to an Organization Site.
