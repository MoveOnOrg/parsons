import json

import requests
from parsons.etl.table import Table
from parsons.utilities import check_env


class MobileCommons(object):
    """
    Instantiate the MobileCommons class

    `Args:`
        username: str
            The authorized ActionKit username. Not required if ``MOBILE_COMMONS_USERNAME`` env
            variable set.
        password: str
            The authorized ActionKit user password. Not required if ``MOBILE_COMMONS_PASSWORD``
            env variable set.
    `Returns:`
        MobileCommons Class
    """

    _default_headers = {
        "content-type": "application/json",
        "accepts": "application/json",
    }

    def __init__(self, username=None, password=None):
        self.username = check_env.check("MOBILE_COMMONS_USERNAME", username)
        self.password = check_env.check("MOBILE_COMMONS_PASSWORD", password)
        self.conn = self._conn()

    def _conn(self, default_headers=_default_headers):
        client = requests.Session()
        client.auth = (self.username, self.password)
        client.headers.update(default_headers)
        return client

    def _base_endpoint(self, endpoint, entity_id=None):
        # Create the base endpoint URL

        url = f"https://secure.mcommons.com/api/{endpoint}/"

        if entity_id:
            return url + f"{entity_id}/"
        return url

    def _base_post(self, endpoint, exception_message, return_full_json=False, **kwargs):
        # Make a general post request to Mobile Commons

        resp = self.conn.post(self._base_endpoint(endpoint), data=json.dumps(kwargs))

        if resp.status_code != 201:
            raise Exception(self.parse_error(resp, exception_message))

        # Some of the methods should just return pointer to location of created object.
        if "headers" in resp.__dict__ and not return_full_json:
            return resp.__dict__["headers"]["Location"]

        # Not all responses return a json
        try:
            return resp.json()

        except ValueError:
            return None

    def parse_error(self, resp, exception_message):
        # Mobile Commons provides some pretty robust/helpful error reporting. We should surface them with our exceptions.

        if "errors" in resp.json().keys():
            if isinstance(resp.json()["errors"], list):
                exception_message += "\n" + ",".join(resp.json()["errors"])
            else:
                for k, v in resp.json()["errors"].items():
                    exception_message += str("\n" + k + ": " + ",".join(v))

        return exception_message

    def profile_opt_out(self, phone_number, **kwargs):
        return self._base_post(
            endpoint="profile_opt_out",
            exception_message="Could not opt out profile",
            phone_number=phone_number,
            **kwargs,
        )
