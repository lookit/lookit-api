#################
API Documentation
#################

=========
API Tips
=========
-------
General
-------
Most endpoints in this API are just meant for retrieving data. Typically, you can retrieve data associated with studies you have permission to view, or view any data that belongs to you.  You can only create *responses* and *feedback* through the API.  You can only update *responses* through the API.  There is *nothing* that is permitted to be deleted through the API.

---------------
Authentication
---------------
We are using a token-based HTTP Authentication scheme.

- Go to Experimenter's admin app to create a token `/admin/authtoken/token/add/` (Only users marked as "Staff" can access the admin app.)

.. image:: _static/img/add_token.png
    :alt: Add token image

- Select your user from the dropdown and hit 'Save'. Copy the token.

.. image:: _static/img/specific_token.png
    :alt: Copy token image

-  Include this token in your Authorization HTTP header.  The word "Token" should come before it.

.. code-block:: bash

    curl -X GET <API_URL_HERE> -H 'Authorization: Token <paste_token_here>'

- For example, here's how you would access users using curl:

.. code-block:: bash

    curl -X GET https://localhost:8000/api/v1/users/ -H 'Authorization: Token 123456789abcdefghijklmnopqrstuvwxyz'

------------
Pagination
------------
- This API is paginated, so results are returned in batches of 10. Follow the pagination links in the API response to fetch the subsequent pages of data.  In the example below, the "links" section of the API response has the first, last, next, and previous links.

*Sample Response:*

.. code-block:: json

    {
        "links": {
            "first": "http://localhost:8000/api/v1/responses/?page=1",
            "last": "http://localhost:8000/api/v1/responses/?page=5",
            "next": "http://localhost:8000/api/v1/responses/?page=2",
            "prev": null,
            "meta": {
                "page": 1,
                "pages": 5,
                "count": 50
            }
        }
    }

===================
Available Endpoints
===================
-------------
Children
-------------

Viewing the list of children
---------------------------------
GET /api/v1/children/

Permissions: Must be authenticated.  You can only view children that have responded to studies you have permission to view, or your own children.

*Sample Response:*

.. code-block:: json

    {
        "links": {
            "first": "http://localhost:8000/api/v1/children/?page=1",
            "last": "http://localhost:8000/api/v1/children/?page=1",
            "next": null,
            "prev": null,
            "meta": {
                "page": 1,
                "pages": 1,
                "count": 1
            }
        },
        "data": [
            {
                "type": "children",
                "id": "0b380366-31b9-45c1-86ef-0fd9ea238ff4",
                "attributes": {
                    "given_name": "Ashley",
                    "birthday": "2015-01-01",
                    "gender": "f",
                    "age_at_birth": "36",
                    "additional_information": "",
                    "deleted": false
                },
                "relationships": {
                    "user": {
                        "links": {
                            "related": "http://localhost:8000/api/v1/users/834bbf33-b249-4737-a041-43574cd137a7/"
                        }
                    }
                },
                "links": {
                    "self": "http://localhost:8000/api/v1/children/0b380366-31b9-45c1-86ef-0fd9ea238ff4/"
                }
            }
        ]
    }

Retrieving a single child
---------------------------------
GET /api/v1/children/<child_id>/

Permissions: Must be authenticated.  You can only view a child if he or she has responded to a study you have permission to view. You can additionally view your own child via the API.

*Sample Response:*

.. code-block:: json

    {
        "data": {
            "type": "children",
            "id": "0b380366-31b9-45c1-86ef-0fd9ea238ff4",
            "attributes": {
                "given_name": "Ashley",
                "birthday": "2015-01-01",
                "gender": "f",
                "age_at_birth": "36",
                "additional_information": "",
                "deleted": false
            },
            "relationships": {
                "user": {
                    "links": {
                        "related": "http://localhost:8000/api/v1/users/834bbf33-b249-4737-a041-43574cd137a7/"
                    }
                }
            },
            "links": {
                "self": "http://localhost:8000/api/v1/children/0b380366-31b9-45c1-86ef-0fd9ea238ff4/"
            }
        }
    }

Creating a Child
---------------------------------
POST /api/v1/children/

METHOD NOT ALLOWED.  Not permitted via the API.


Updating a Child.
---------------------------------
PUT /api/v1/children/<child_id>/

METHOD NOT ALLOWED.  Not permitted via the API.


Deleting a Child
---------------------------------
DELETE /api/v1/children/<child_id>/

METHOD NOT ALLOWED.  Not permitted via the API.

-----------------
Demographic Data
-----------------

Viewing the list of demographic data
--------------------------------------
GET /api/v1/demographics/

Permissions: Must be authenticated.  You can only view demographics of participants whose children have responded to studies you can view.  You can additionally view your own demographic data via the API.

*Sample Response:*

.. code-block:: json

    {
        "links": {
            "first": "http://localhost:8000/api/v1/demographics/?page=1",
            "last": "http://localhost:8000/api/v1/demographics/?page=1",
            "next": null,
            "prev": null,
            "meta": {
                "page": 1,
                "pages": 1,
                "count": 1
            }
        },
        "data": [
            {
                "type": "demographics",
                "id": "f5fa60ca-d428-46cd-9820-846492dd9900",
                "attributes": {
                    "number_of_children": "1",
                    "child_birthdays": [
                        "2015-01-01"
                    ],
                    "languages_spoken_at_home": "English and French",
                    "number_of_guardians": "2",
                    "number_of_guardians_explanation": "",
                    "race_identification": [
                        "white"
                    ],
                    "age": "30-34",
                    "gender": "f",
                    "education_level": "grad",
                    "spouse_education_level": "bach",
                    "annual_income": "30000",
                    "number_of_books": 100,
                    "additional_comments": "",
                    "country": "US",
                    "state": "AZ",
                    "density": "urban",
                    "extra": {
                        "no": "extra"
                    }
                },
                "links": {
                    "self": "http://localhost:8000/api/v1/demographics/f5fa60ca-d428-46cd-9820-846492dd9900/"
                }
            }
        ]
    }

Retrieving a single piece of demographic data
------------------------------------------------
GET /api/v1/demographics/<demographic_data_id>/

Permissions: Must be authenticated.  You can only view demographics of participants whose children have responded to studies you can view.  You can additionally view your own demographic data via the API.

*Sample Response:*

.. code-block:: json

    {
        "data": {
            "type": "demographics",
            "id": "f5fa60ca-d428-46cd-9820-846492dd9900",
            "attributes": {
                "number_of_children": "1",
                "child_birthdays": [
                    "2015-01-01"
                ],
                "languages_spoken_at_home": "English and French",
                "number_of_guardians": "2",
                "number_of_guardians_explanation": "",
                "race_identification": [
                    "white"
                ],
                "age": "30-34",
                "gender": "f",
                "education_level": "grad",
                "spouse_education_level": "bach",
                "annual_income": "30000",
                "number_of_books": 100,
                "additional_comments": "",
                "country": "US",
                "state": "AZ",
                "density": "urban",
                "extra": {
                    "no": "extra"
                }
            },
            "links": {
                "self": "http://localhost:8000/api/v1/demographics/f5fa60ca-d428-46cd-9820-846492dd9900/"
            }
        }
    }

Creating Demographics
---------------------------------
POST /api/v1/demographics/

METHOD NOT ALLOWED.  Not permitted via the API.


Updating Demographics
---------------------------------
PUT /api/v1/demographics/<demographic_data_id>/

METHOD NOT ALLOWED.  Not permitted via the API.


Deleting Demographics
---------------------------------
DELETE /api/v1/demographics/<demographic_data_id>/

METHOD NOT ALLOWED.  Not permitted via the API.

-------------
Feedback
-------------

Viewing the list of feedback
---------------------------------
GET /api/v1/feedback/

Permissions: Must be authenticated.  You can only view feedback on study responses you have permission to view. Additionally, you can view feedback left on your own responses.

*Sample Response:*

.. code-block:: json

    {
        "links": {
            "first": "http://localhost:8000/api/v1/feedback/?page=1",
            "last": "http://localhost:8000/api/v1/feedback/?page=1",
            "next": null,
            "prev": null,
            "meta": {
                "page": 1,
                "pages": 1,
                "count": 1
            }
        },
        "data": [
            {
                "type": "feedback",
                "id": "cbfc64ee-30a3-491e-bd0e-1bef81540ea5",
                "attributes": {
                    "comment": "Thanks for participating!  Next time, please center the webcam; you were off-center in many of the video clips."
                },
                "relationships": {
                    "response": {
                        "links": {
                            "related": "http://localhost:8000/api/v1/responses/841c8a77-b322-4e25-8e03-47a83fa326ff/"
                        }
                    },
                    "researcher": {
                        "links": {
                            "related": "http://localhost:8000/api/v1/users/834bbf33-b249-4737-a041-43574cd137a7/"
                        }
                    }
                },
                "links": {
                    "self": "http://localhost:8000/api/v1/feedback/cbfc64ee-30a3-491e-bd0e-1bef81540ea5/"
                }
            }
        ]
    }

Retrieving a single piece of feedback
---------------------------------------
GET /api/v1/feedback/<feedback_id>/

Permissions: Must be authenticated. You can only retrieve feedback attached to a study response you have permission to view.  Additionally, you can retrieve feedback attached to one of your own responses.

*Sample Response:*

.. code-block:: json

    {
        "data": {
            "type": "feedback",
            "id": "cbfc64ee-30a3-491e-bd0e-1bef81540ea5",
            "attributes": {
                "comment": "Thanks for participating!  Next time, please center the webcam; you were off-center in many of the video clips."
            },
            "relationships": {
                "response": {
                    "links": {
                        "related": "http://localhost:8000/api/v1/responses/841c8a77-b322-4e25-8e03-47a83fa326ff/"
                    }
                },
                "researcher": {
                    "links": {
                        "related": "http://localhost:8000/api/v1/users/834bbf33-b249-4737-a041-43574cd137a7/"
                    }
                }
            },
            "links": {
                "self": "http://localhost:8000/api/v1/feedback/cbfc64ee-30a3-491e-bd0e-1bef81540ea5/"
            }
        }
    }


Creating Feedback
---------------------------------
POST /api/v1/feedback/

Permissions: Must be authenticated. Must have permission to edit the study response where you are leaving feedback (which only admins have).

*Sample Request body:*

.. code-block:: json

    {
     "data": {
           "attributes": {
             "comment": "Thank you so much for participating in round one! Please try to respond to the second round some time in the next three weeks!"
           },
           "relationships": {
             "response": {
               "data": {
                 "type": "responses",
                 "id": "841c8a77-b322-4e25-8e03-47a83fa326ff"
               }
             }
           },
           "type": "feedback"
         }
    }

*Sample Response*

.. code-block:: json

    {
        "data": {
            "type": "feedback",
            "id": "aabf86c7-3dc0-4284-844c-89e04a1f154f",
            "attributes": {
                "comment": "Thank you so much for participating in round one! Please try to respond to the second round some time in the next three weeks!"
            },
            "relationships": {
                "response": {
                    "links": {
                        "related": "http://localhost:8000/api/v1/responses/841c8a77-b322-4e25-8e03-47a83fa326ff/"
                    }
                },
                "researcher": {
                    "links": {
                        "related": "http://localhost:8000/api/v1/users/834bbf33-b249-4737-a041-43574cd137a7/"
                    }
                }
            },
            "links": {
                "self": "http://localhost:8000/api/v1/feedback/aabf86c7-3dc0-4284-844c-89e04a1f154f/"
            }
        }
    }

Updating Feedback
---------------------------------
PUT /api/v1/feedback/<feedback_id>/

METHOD NOT ALLOWED.  Not permitted via the API.


Deleting Feedback
---------------------------------
DELETE /api/v1/feedback/<feedback_id>/

METHOD NOT ALLOWED.  Not permitted via the API.

-------------
Organizations
-------------

Viewing the list of organizations
---------------------------------
GET /api/v1/organizations/

Permissions: Must be authenticated.

*Sample Response:*

.. code-block:: json

    {
        "links": {
            "first": "http://localhost:8000/api/v1/organizations/?page=1",
            "last": "http://localhost:8000/api/v1/organizations/?page=1",
            "next": null,
            "prev": null,
            "meta": {
                "page": 1,
                "pages": 1,
                "count": 1
            }
        },
        "data": [
            {
                "type": "organizations",
                "id": "665c4457-a02e-4842-bd72-7043de3d66d0",
                "attributes": {
                    "name": "MIT"
                },
                "links": {
                    "self": "http://localhost:8000/api/v1/organizations/665c4457-a02e-4842-bd72-7043de3d66d0/"
                }
            }
        ]
    }

Retrieving a single organization
---------------------------------
GET /api/v1/organizations/<organization_id>/

Permissions: Must be authenticated.

*Sample Response:*

.. code-block:: json

    {
        "data": {
            "type": "organizations",
            "id": "665c4457-a02e-4842-bd72-7043de3d66d0",
            "attributes": {
                "name": "MIT"
            },
            "links": {
                "self": "http://localhost:8000/api/v1/organizations/665c4457-a02e-4842-bd72-7043de3d66d0/"
            }
        }
    }


Creating an Organization
---------------------------------
POST /api/v1/organizations/

METHOD NOT ALLOWED.  Not permitted via the API.


Updating an Organization
---------------------------------
PUT /api/v1/organizations/<organization_id>/

METHOD NOT ALLOWED.  Not permitted via the API.


Deleting an Organization
---------------------------------
DELETE /api/v1/organizations/<organization_id>/

METHOD NOT ALLOWED.  Not permitted via the API.

-------------
Responses
-------------

Viewing the list of responses
---------------------------------
GET /api/v1/responses/

Permissions: Must be authenticated.  You can only view responses to studies you have permission to view. Additionally, you can view your own responses through the API.

*Sample Response:*

.. code-block:: json

    {
        "links": {
            "first": "http://localhost:8000/api/v1/feedback/?page=1",
            "last": "http://localhost:8000/api/v1/feedback/?page=1",
            "next": null,
            "prev": null,
            "meta": {
                "page": 1,
                "pages": 1,
                "count": 1
            }
        },
        "data": [
          {
             "type":"responses",
             "id":"8260ca67-6ec0-4749-ba11-fa35612ea030",
             "attributes":{
                "conditions":{

                },
                "global_event_timings":[
                   {
                      "exit_type":"browserNavigationAttempt",
                      "timestamp":"2017-09-05T14:33:41.322Z",
                      "event_type":"exitEarly",
                      "last_page_seen":0
                   }
                ],
                "exp_data":{

                },
                "sequence":[

                ],
                "completed":false
             },
             "relationships":{
                "child":{
                   "links":{
                      "related":"http://localhost:8000/api/v1/children/0b380366-31b9-45c1-86ef-0fd9ea238ff4/"
                   }
                },
                "study":{
                   "links":{
                      "related":"http://localhost:8000/api/v1/studies/a8a80880-5539-4650-9387-c62afa202d43/"
                   }
                },
                "demographic_snapshot":{
                   "links":{
                      "related":"http://localhost:8000/api/v1/demographics/f5fa60ca-d428-46cd-9820-846492dd9900/"
                   }
                }
             },
             "links":{
                "self":"http://localhost:8000/api/v1/responses/8260ca67-6ec0-4749-ba11-fa35612ea030/"
             }
          }
        ]
    }


Retrieving a single response
---------------------------------
GET /api/v1/responses/<response_id>/

Permissions: Must be authenticated. You can only view responses to studies you have permission to view as well as your own responses.

*Sample Response:*

.. code-block:: json

    {
        "data": {
            "type": "responses",
            "id": "8260ca67-6ec0-4749-ba11-fa35612ea030",
            "attributes": {
                "conditions": {},
                "global_event_timings": [
                    {
                        "exit_type": "browserNavigationAttempt",
                        "timestamp": "2017-09-05T14:33:41.322Z",
                        "event_type": "exitEarly",
                        "last_page_seen": 0
                    }
                ],
                "exp_data": {},
                "sequence": [],
                "completed": false
            },
            "relationships": {
                "child": {
                    "links": {
                        "related": "http://localhost:8000/api/v1/children/0b380366-31b9-45c1-86ef-0fd9ea238ff4/"
                    }
                },
                "study": {
                    "links": {
                        "related": "http://localhost:8000/api/v1/studies/a8a80880-5539-4650-9387-c62afa202d43/"
                    }
                },
                "demographic_snapshot": {
                    "links": {
                        "related": "http://localhost:8000/api/v1/demographics/f5fa60ca-d428-46cd-9820-846492dd9900/"
                    }
                }
            },
            "links": {
                "self": "http://localhost:8000/api/v1/responses/8260ca67-6ec0-4749-ba11-fa35612ea030/"
            }
        }
    }


Creating a Response
---------------------------------
POST /api/v1/responses/.  Possible to do programmatically, but really intended to be used by ember-lookit-frameplayer app.

Permissions: Must be authenticated.  Child in response must be your child.

*Sample Request body:*

.. code-block:: json

    {
        "data": {
            "attributes": {},
            "relationships": {
              "child": {
                "data": {
                  "type": "children",
                  "id": "0b380366-31b9-45c1-86ef-0fd9ea238ff4"
                }
              },
              "study": {
                "data": {
                  "type": "studies",
                  "id": "a8a80880-5539-4650-9387-c62afa202d43"
                }
              }
            },
        "type": "responses"
        }
    }

Updating a Response
---------------------------------
PATCH /api/v1/responses/<response_id>/  Possible to do programmatically, but really intended for the ember-lookit-frameplayer to update
as it moves through each frame of the study.

*Sample Request body:*

.. code-block:: json

    {
     "data": {
       "attributes": {
           "conditions": {"cloudy": "skies"}
       },
       "type": "responses",
       "id": "51c0a355-375d-481f-a3d0-6471db8f9f14"
     }
    }

Deleting a Response
---------------------------------
DELETE /api/v1/responses/<response_id>/

METHOD NOT ALLOWED.  Not permitted via the API.

-------------
Studies
-------------

Viewing the list of studies
---------------------------------
GET /api/v1/studies/

Permissions: Must be authenticated. You can view studies that are active/public as well as studies you have permission to edit.

*Sample Response:*

.. code-block:: json

    {
        "links": {
            "first": "http://localhost:8000/api/v1/studies/?page=1",
            "last": "http://localhost:8000/api/v1/studies/?page=1",
            "next": null,
            "prev": null,
            "meta": {
                "page": 1,
                "pages": 1,
                "count": 1
            }
        },
        "data": [
            {
                "type": "studies",
                "id": "65680ade-510c-4437-a58a-e41d4b94d8ed",
                "attributes": {
                    "name": "Sample Study",
                    "date_modified": "2017-09-06T19:33:24.826892Z",
                    "short_description": "A short description of your study would go here.",
                    "long_description": "A longer purpose of your study would be here.",
                    "criteria": "Children should be around five.",
                    "duration": "20 minutes",
                    "contact_info": "Contact Sally",
                    "image": "http://localhost:8000/media/study_images/download.jpeg",
                    "structure": {
                        "frames": {},
                        "sequence": []
                    },
                    "display_full_screen": true,
                    "exit_url": "http://www.cos.io",
                    "state": "created",
                    "public": true
                },
                "relationships": {
                    "organization": {
                        "links": {
                            "related": "http://localhost:8000/api/v1/organizations/665c4457-a02e-4842-bd72-7043de3d66d0/"
                        }
                    },
                    "creator": {
                        "links": {
                            "related": "http://localhost:8000/api/v1/users/834bbf33-b249-4737-a041-43574cd137a7/"
                        }
                    },
                    "responses": {
                        "links": {
                            "related": "http://localhost:8000/api/v1/studies/65680ade-510c-4437-a58a-e41d4b94d8ed/responses/"
                        }
                    }
                },
                "links": {
                    "self": "http://localhost:8000/api/v1/studies/65680ade-510c-4437-a58a-e41d4b94d8ed/"
                }
            }
        ]
    }

Retrieving a single study
---------------------------------
GET /api/v1/studies/<study_id>/

Permissions: Must be authenticated.  You can fetch an active study or a study you have permission to edit.

*Sample Response:*

.. code-block:: json

    {
        "data": {
            "type": "studies",
            "id": "65680ade-510c-4437-a58a-e41d4b94d8ed",
            "attributes": {
                "name": "Sample Study",
                "date_modified": "2017-09-06T19:33:24.826892Z",
                "short_description": "A short description of your study would go here.",
                "long_description": "A longer purpose of your study would be here.",
                "criteria": "Children should be around five.",
                "duration": "20 minutes",
                "contact_info": "Contact Sally",
                "image": "http://localhost:8000/media/study_images/download.jpeg",
                "structure": {
                    "frames": {},
                    "sequence": []
                },
                "display_full_screen": true,
                "exit_url": "http://www.cos.io",
                "state": "created",
                "public": true
            },
            "relationships": {
                "organization": {
                    "links": {
                        "related": "http://localhost:8000/api/v1/organizations/665c4457-a02e-4842-bd72-7043de3d66d0/"
                    }
                },
                "creator": {
                    "links": {
                        "related": "http://localhost:8000/api/v1/users/834bbf33-b249-4737-a041-43574cd137a7/"
                    }
                },
                "responses": {
                    "links": {
                        "related": "http://localhost:8000/api/v1/studies/65680ade-510c-4437-a58a-e41d4b94d8ed/responses/"
                    }
                }
            },
            "links": {
                "self": "http://localhost:8000/api/v1/studies/65680ade-510c-4437-a58a-e41d4b94d8ed/"
            }
        }
    }

Retrieving a Study's responses
---------------------------------
GET /api/v1/studies/<study_id>/responses/

Permissions: Must be authenticated.  Must have permission to view the responses to the particular study.


Creating a Study
---------------------------------
POST /api/v1/studies/

METHOD NOT ALLOWED.  Not permitted via the API.


Updating a Study
---------------------------------
PUT /api/v1/studies/<study_id>/

METHOD NOT ALLOWED.  Not permitted via the API.


Deleting a Study
---------------------------------
DELETE /api/v1/studies/<study_id>/

METHOD NOT ALLOWED.  Not permitted via the API.


-------------
Users
-------------

Viewing the list of users
---------------------------------
GET /api/v1/users/

Permissions: Must be authenticated.  You can view participants that have responded to studies you have permission to view, as well as own user information.
Endpoint can return both participants and researchers, if you have permission to view them.

*Sample Response:*

.. code-block:: json

    {
        "links": {
            "first": "http://localhost:8000/api/v1/users/?page=1",
            "last": "http://localhost:8000/api/v1/users/?page=1",
            "next": null,
            "prev": null,
            "meta": {
                "page": 1,
                "pages": 1,
                "count": 1
            }
        },
        "data": [
            {
                "type": "users",
                "id": "834bbf33-b249-4737-a041-43574cd137a7",
                "attributes": {
                    "given_name": "Test",
                    "middle_name": "",
                    "family_name": "User",
                    "identicon": "data:image/png;base64,aaaabbbbccccddddeeeefffffgggg",
                    "is_active": true,
                    "is_staff": true
                },
                "relationships": {
                    "demographics": {
                        "links": {
                            "related": "http://localhost:8000/api/v1/users/834bbf33-b249-4737-a041-43574cd137a7/demographics/"
                        }
                    },
                    "organization": {
                        "links": {
                            "related": "http://localhost:8000/api/v1/organizations/665c4457-a02e-4842-bd72-7043de3d66d0/"
                        }
                    },
                    "children": {
                        "links": {
                            "related": "http://localhost:8000/api/v1/users/834bbf33-b249-4737-a041-43574cd137a7/children/"
                        }
                    }
                },
                "links": {
                    "self": "http://localhost:8000/api/v1/users/834bbf33-b249-4737-a041-43574cd137a7/"
                }
            }
        ]
    }

Retrieving a single user
---------------------------------
GET /api/v1/users/<user_id>/

Permissions: Must be authenticated.  You can view participants that have responded to studies you have permission to view, as well as own user information.

*Sample Response:*

.. code-block:: json
    {
        "data": {
            "type": "users",
            "id": "834bbf33-b249-4737-a041-43574cd137a7",
            "attributes": {
                "given_name": "Test",
                "middle_name": "",
                "family_name": "User",
                "identicon": "data:image/png;base64,aaaabbbbccccddddeeeefffffgggg",
                "is_active": true,
                "is_staff": true
            },
            "relationships": {
                "demographics": {
                    "links": {
                        "related": "http://localhost:8000/api/v1/users/834bbf33-b249-4737-a041-43574cd137a7/demographics/"
                    }
                },
                "organization": {
                    "links": {
                        "related": "http://localhost:8000/api/v1/organizations/665c4457-a02e-4842-bd72-7043de3d66d0/"
                    }
                },
                "children": {
                    "links": {
                        "related": "http://localhost:8000/api/v1/users/834bbf33-b249-4737-a041-43574cd137a7/children/"
                    }
                }
            },
            "links": {
                "self": "http://localhost:8000/api/v1/users/834bbf33-b249-4737-a041-43574cd137a7/"
            }
        }
    }

Creating a User
---------------------------------
POST /api/v1/users/

METHOD NOT ALLOWED.  Not permitted via the API.


Updating a User
---------------------------------
PUT /api/v1/users/<user_id>/

METHOD NOT ALLOWED.  Not permitted via the API.


Deleting a User
---------------------------------
DELETE /api/v1/users/<user_id>/

METHOD NOT ALLOWED.  Not permitted via the API.
