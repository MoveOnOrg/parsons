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

    def delete_user(self, id):
        """
        Delete Auth0 user.

        `Args:`
            id: str
                The user ID of the record to delete.
        `Returns:`
            int
        """
        return requests.delete(
            f"{self.base_url}/api/v2/users/{id}", headers=self.headers
        ).status_code

    def get_users_by_email(self, email):
        """
        Get Auth0 users by email.

        `Args:`
            email: str
                The user email of the record to get.
        `Returns:`
            Table Class
        """
        return Table(
            requests.get(
                f"{self.base_url}/api/v2/users-by-email",
                headers=self.headers,
                params={"email": email},
            ).json()
        )

    def upsert_user(
        self,
        email,
        username=None,
        given_name=None,
        family_name=None,
        app_metadata={},
        user_metadata={},
    ):
        """
        Upsert Auth0 users by email.

        `Args:`
            email: str
                The user email of the record to get.
            username: optional str
                Username to set for user
            given_name: optional str
                Given to set for user
            family_name: optional str
                Family name to set for user
            app_metadata: optional dict
                App metadata to set for user
            user_metadata: optional dict
                User metadata to set for user
        `Returns:`
            Requests Response object
        """
        payload = json.dumps(
            {
                "email": email.lower(),
                "given_name": given_name,
                "family_name": family_name,
                "username": username,
                "connection": "Username-Password-Authentication",
                "app_metadata": app_metadata,
                "blocked": False,
                "user_metadata": user_metadata,
            }
        )
        existing = self.get_users_by_email(email.lower())
        if existing.num_rows > 0:
            a0id = existing[0]["user_id"]
            ret = requests.patch(
                f"{self.base_url}/api/v2/users/{a0id}",
                headers=self.headers,
                data=payload,
            )
        else:
            ret = requests.post(
                f"{self.base_url}/api/v2/users", headers=self.headers, data=payload
            )
        if ret.status_code != 200:
            raise ValueError(f"Invalid response {ret.json()}")
        return ret
