import json
import logging
from typing import Optional

from parsons import Table
from parsons.utilities import check_env
from parsons.utilities.api_connector import APIConnector

logger = logging.getLogger(__name__)

PROMPT_IO_API_PARTIAL_URI = "prompt.io/rest/1.0"


class PromptIO:
    """
    Instantiate the PromptIO class.

    `Args:`
        api_key: `str`
            A valid API Key created by a Prompt.io account. Not required if
            `PROMPT_IO_API_KEY` env variable is set.
        instance_subdomain: `str`
            The subdomain for your Prompt.io instance. For example, if your
            Prompt.io URL is `example.prompt.io`, your subdomain is `example`.
            Not required if `PROMPT_IO_INSTANCE_SUBDOMAIN` env variable is set.
    """

    def __init__(self, api_key=None, instance_subdomain=None):
        self.api_key = check_env.check("PROMPT_IO_API_KEY", api_key)
        self.instance_subdomain = check_env.check(
            "PROMPT_IO_INSTANCE_SUBDOMAIN", instance_subdomain
        )
        self.api = APIConnector(
            uri=f"https://{self.instance_subdomain}.{PROMPT_IO_API_PARTIAL_URI}",
            headers={
                "orgAuthToken": self.api_key,
                "Content-Type": "application/json",
            },
        )

    def create_contact_list_from_s3_csv(
        self,
        api_id: str,
        display_name: str,
        s3_csv_url: str,
        description: Optional[str] = None,
        icon_url: Optional[str] = None,
    ) -> dict:
        """
        Create a new Contact List from a .csv file hosted on an AWS S3 bucket.
        Will generate a presigned URL valid for 5 minutes to upload the file.

        `Args:`
            api_id: `str`
                The unique API ID key for the contact list.
            display_name: `str`
                The full UI display name for the contact list.
            s3_csv_url: `str`
                The URL of the .csv file hosted on AWS S3. Must be presigned if in private bucket.
            description: `Optional[str]`
                `Optional` A friendly description for the contact list.
            icon_url: `Optional[str]`
                `Optional` A URL for an icon to be displayed in the UI.
        `Returns:`
            `dict`
                The created Contact List object.

        """

        # note the L2 logo will be displayed by default (bug?); use Parsons if one isn't provided
        parsons_icon_url = (
            "https://move-coop.github.io/parsons/html/stable/_images/parsons_logo.png"
        )

        return self.api.post_request(
            "contact_lists",
            data=json.dumps(
                {
                    "apiId": api_id,
                    "name": display_name,
                    "externalUrl": s3_csv_url,
                    "description": description or "",
                    "icon": icon_url or parsons_icon_url,
                    "type": "PROMPT",  # not documented but must be passed or call won't work
                }
            ),
        )

    def get_contact_list_by_id(self, contact_list_id: str) -> dict:
        """
        Get one Contact List by its primary ID.

        `Args:`
            contact_list_id: `str`
                The primary ID for the contact list.
        `Returns:`
            `dict`
                The Contact List object.
        """

        contact_list = self.api.get_request(f"contact_lists/{contact_list_id}")

        # contact count is not included in the base object; make another call to get it
        contacts_response = self.api.get_request(
            f"contact_lists/{contact_list_id}/contacts", params={"max": 1}
        )

        return {**contact_list, "contact_count": contacts_response["count"]}

    def get_contact_lists(self, offset_index: int = 0) -> Table | None:
        """
        Get all Contact Lists. Will return all records starting from the specified
        offset; each request can return no more than 200 rows per page.

        `Args:`
            offset_index: int
                Optional, Default is 0. The first record to retrieve (ordered by ID ascending).
        `Returns:`
            Parsons Table
                A Parsons Table with all contact lists.
        """

        response = self.api.get_request("contact_lists", params={"first": offset_index, "max": 200})
        data = Table(response["contactLists"])
        total_count = response["count"]

        logger.info(f"Retrieved {data.num_rows} of {total_count} total contact lists.")

        return data

    def delete_contact_list(self, contact_list_id: str) -> dict:
        """
        Delete one Contact List with its primary ID.

        `Args:`
            contact_list_id: `str`
                The primary ID for the contact list.
        `Returns:`
            `dict`
                The Contact List object.
        """

        return self.api.delete_request(f"contact_lists/{contact_list_id}")
