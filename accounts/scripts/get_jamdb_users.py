import requests
import json

JAMDB_AUTHORIZATION_TOKEN = 'JWT_SECRET_TOKEN'
# To set this make this request
# POST https://metadata.osf.io/v1/auth
#
# {
#   "data": {
#     "type": "users",
#     "attributes": {
#       "provider": "osf",
#       "access_token": "PERSONAL_ACCESS_TOKEN"
#     }
#   }
# }
# Fill this in with a Personal Access Token from the osf
# with a user that has super magic access to JamDB for lookit accounts
# The JAMDB_AUTHORIZATION_TOKEN will be returned as data.attributes.token in the response.
# It's good for a limited time and the call will need to be repeated to rerun this.


def get_jamdb_users():
    with open('../../participants.json', mode='w') as f:
        peeps = []
        for x in range(1, 35):
            try:
                response = requests.get(
                    url="https://metadata.osf.io/v1/id/collections/lookit.accounts/_search",
                    params={
                        "page[size]": "100",
                        "page": str(x),
                    },
                    headers={
                        "Authorization": JAMDB_AUTHORIZATION_TOKEN,
                    },
                )
                print('Response HTTP Status Code: {status_code}'.format(
                    status_code=response.status_code))
            except requests.exceptions.RequestException:
                print('HTTP Request failed')
            try:
                peeps.extend(response.json()['data'])
            except KeyError:
                continue
        print(len(peeps))
        f.write(json.dumps(peeps, indent=4))
