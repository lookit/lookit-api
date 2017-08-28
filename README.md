
# Creating feedback
To add feedback to a response via the API, you must have "can_edit_study"
permissions for the associated study.

POST /api/v1/feedback/
```json
{
 "data": {
   "attributes": {
     "comment": "<add your comment here>"
   },
   "relationships": {
     "response": {
       "data": {
         "type": "responses",
         "id": "<response_id>"
       }
     }
   },
   "type": "feedback"
 }
}
```
