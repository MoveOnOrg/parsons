import json
import logging
from typing import Any, Optional, cast

from pydantic import BaseModel, ConfigDict

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
        instance_subdomain = check_env.check("PROMPT_IO_INSTANCE_SUBDOMAIN", instance_subdomain)
        if not instance_subdomain:
            raise ValueError(
                "`PROMPT_IO_INSTANCE_SUBDOMAIN` environment variable or "
                "`instance_subdomain` parameter must be provided."
            )
        api_key = check_env.check("PROMPT_IO_API_KEY", api_key)
        if not api_key:
            raise ValueError(
                "`PROMPT_IO_API_KEY` environment variable or `api_key` parameter must be provided."
            )
        self.api_key = api_key
        self.instance_subdomain = instance_subdomain
        self.api = APIConnector(
            uri=f"https://{self.instance_subdomain}.{PROMPT_IO_API_PARTIAL_URI}",
            headers={
                "orgAuthToken": self.api_key,
                "Content-Type": "application/json",
            },
        )

    def _get_request_all_paginated_results(
        self,
        endpoint: str,
        params: Optional[dict] = None,
    ) -> list[Any]:
        """
        Internal method to get all results from a paginated endpoint.

        `Args:`
            endpoint: `str`
                The API endpoint to query.
            params: `dict`
                Additional query parameters to include in the request.
        `Returns:`
            `list[dict]`
                A list of all results from the paginated endpoint.
        """

        # list responses will always contain only 2 keys: `count` and the data list;
        # the list key in the response is different based on the endpoint called,
        # i.e. `contactLists`, `customerOptOutsModels`, etc.

        class ResponseModel(BaseModel):
            model_config = ConfigDict(extra="allow")
            count: int

        MAX_PAGE_SIZE = 200  # maximum page size for Prompt.io API
        all_results = []
        offset = 0

        while True:
            request_params = {**(params or {}), "first": offset, "max": MAX_PAGE_SIZE}
            res = self.api.get_request(endpoint, params=request_params)

            response = ResponseModel.model_validate(res)

            for value in response.model_dump().values():
                if isinstance(value, list):
                    # map values to snake_case keys
                    all_results.extend(value)
                    break

            if len(all_results) == response.count:
                break
            offset += MAX_PAGE_SIZE

        return all_results

    def create_contact_list_from_csv(
        self,
        api_id: str,
        display_name: str,
        csv_file_url: str,
        description: Optional[str] = None,
        icon_url: Optional[str] = None,
    ) -> dict:
        """
        Create a new Contact List from a .csv file hosted online.
        Note that if the .csv is malformed an error will not be returned,
        nor be available to query anywhere; the list will just be created
        and the contact count will remain at 0.

        `Args:`
            api_id: `str`
                The unique API ID key for the contact list.
            display_name: `str`
                The full UI display name for the contact list.
            csv_file_url: `str`
                The web URL of the .csv file, such as a presigned or otherwise public AWS S3 URL.
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

        return cast(
            "dict",
            self.api.post_request(
                "contact_lists",
                data=json.dumps(
                    {
                        "apiId": api_id,
                        "name": display_name,
                        "externalUrl": csv_file_url,
                        "description": description or "",
                        "icon": icon_url or parsons_icon_url,
                        "type": "PROMPT",  # not documented but must be passed or call won't work
                    }
                ),
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

        contact_list = cast(
            "dict",
            self.api.get_request(f"contact_lists/{contact_list_id}"),
        )

        # contact count is not included in the base object; make another call to get it
        contacts_response = cast(
            "dict",
            self.api.get_request(f"contact_lists/{contact_list_id}/contacts", params={"max": 1}),
        )

        return {**contact_list, "contactsCount": contacts_response["count"]}

    def get_all_contact_lists(self) -> Table:
        """
        Get all Contact Lists. Will return all records starting from the specified
        offset; each request can return no more than 200 rows per page.

        `Args:`
            offset_index: `int`
                `Optional` Default is 0. The first record to retrieve (ordered by ID ascending).
        `Returns:`
            Parsons `Table`
                A Parsons Table with all contact lists.
        """

        contact_lists = self._get_request_all_paginated_results("contact_lists")

        return Table(contact_lists)

    def delete_contact_list(self, contact_list_id: str) -> None:
        """
        Delete one Contact List with its primary ID.

        `Args:`
            contact_list_id: `str`
                The primary ID for the contact list.
        `Returns:`
            None
        """
        self.api.delete_request(f"contact_lists/{contact_list_id}")
        return None

    def upsert_contact(
        self,
        phone_number: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        tag_ids: Optional[list[int]] = None,
        additional_data: Optional[dict[str, str]] = None,
    ) -> dict:
        """
        Create or update a Contact.

        `Args:`
            phone_number: `str`
                The E164 formatted (+1555222345) phone number for the contact.
            first_name: `str`
                `Optional` The first name of the contact.
            last_name: `str`
                `Optional` The last name of the contact.
            tag_ids: `list[int]`
                `Optional` A list of Tag IDs to assign to the contact.
            additional_data: `dict[str, str]`
                `Optional` A dictionary of additional data key/value fields to assign to the contact.
        `Returns:`
            `dict`
                The created or updated Contact object.
        """

        response = self.api.post_request(
            "customers",
            data=json.dumps(
                {
                    "displayName": f"{first_name or ''} {last_name or ''}".strip(),
                    "firstName": first_name,
                    "lastName": last_name,
                    "identities": [{"type": "SMS", "key": phone_number}],
                    "tagIds": tag_ids,
                    "data": {
                        "firstName": first_name,
                        "lastName": last_name,
                        **(additional_data or {}),
                    },
                }
            ),
        )

        return cast("dict", response)

    def get_contact_by_id(self, contact_id: int) -> dict:
        """
        Get one Contact by its primary ID.

        `Args:`
            contact_id: `int`
                The primary ID for the contact.
        `Returns:`
            `dict`
                The Contact object.
        """

        return cast("dict", self.api.get_request(f"customers/{contact_id}"))

    def get_opt_out_report(
        self,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        time_window: Optional[str] = None,
    ) -> Table:
        """
        Get all opted out phone numbers within a specified time range.
        Note that the request will likely time out if attempting to request
        large amounts of data in a single request.

        `Args:`
            start_time: `int`
                `Optional` The start time as a Unix timestamp in milliseconds.
            end_time: `int`
                `Optional` The end time as a Unix timestamp in milliseconds.
            time_window: `str`
                `Optional` A predefined time window. Valid values are:
                Available values: `last_60_mins`, `yesterday`, `today`, `last_month`, `this_month`,
                `last_quarter`, `this_quarter`, `last_year`, `this_year`, `custom`, `all_time`
        `Returns:`
            Parsons Table
                A Parsons Table with all opted-out contacts.
        """

        opt_outs = self.api.get_request(
            "analytics/opt_out_report",
            params={
                "start_time": start_time,
                "end_time": end_time,
                "timeWindow": time_window,
            },
        )

        return Table(opt_outs)

    def opt_out_contact(self, contact_id: int) -> dict:
        """
        Opt a Contact **out** of receiving messages.

        `Args:`
            contact_id: `int`
                The primary ID for the contact.
        `Returns:`
            `dict`
                The updated Contact object.
        """

        return cast(
            "dict",
            self.api.put_request(
                f"customers/{contact_id}", data=json.dumps({"globalOptOut": True})
            ),
        )

    def opt_in_contact(self, contact_id: int) -> dict:
        """
        Opt a Contact **in** to receive messages.

        `Args:`
            contact_id: `int`
                The primary ID for the contact.
        `Returns:`
            `dict`
                The updated Contact object.
        """

        return cast(
            "dict",
            self.api.put_request(
                f"customers/{contact_id}", data=json.dumps({"globalOptOut": False})
            ),
        )

    def create_tag(self, name: str, color_hex_code: str, note: Optional[str] = None) -> dict:
        """
        Create a new Tag.

        `Args:`
            name: `str`
                The name of the Tag.
            color_hex_code: `str`
                The hex code color for the Tag (e.g., #FF5733).
            note: `Optional[str]`
                `Optional` A friendly description for the Tag. Max 50 chars;
                will be truncated if longer.
        `Returns:`
            `dict`
                The created Tag object.

        """

        return cast(
            "dict",
            self.api.post_request(
                "tags",
                data=json.dumps(
                    {
                        "name": name,
                        "colorCode": color_hex_code,
                        "note": note[:50] if note else "",
                    }
                ),
            ),
        )

    # TODO: currently not an endpoint, implement when available
    # def update_tag(
    #     self,
    #     tag_id: int,
    #     name: Optional[str] = None,
    #     color_hex_code: Optional[str] = None,
    #     note: Optional[str] = None,
    # ) -> dict:
    #     """
    #     Update an existing Tag. At least one field must be provided to update.

    #     `Args:`
    #         tag_id: `int`
    #             The primary ID for the Tag.
    #         name: `Optional[str]`
    #             `Optional` The new name of the Tag.
    #         color_hex_code: `Optional[str]`
    #             `Optional` The new hex code color for the Tag (e.g., #FF5733).
    #         note: `Optional[str]`
    #             `Optional` A new friendly description for the Tag. Max 50 chars;
    #             will be truncated if longer.
    #     `Returns:`
    #         `dict`
    #             The updated Tag object.
    #     """

    #     if name is None and color_hex_code is None and note is None:
    #         raise ValueError(
    #             "At least one of name, color_hex_code, or note must be provided"
    #         )

    #     tag_data = {}
    #     if name is not None:
    #         tag_data["name"] = name
    #     if color_hex_code is not None:
    #         tag_data["colorCode"] = color_hex_code
    #     if note is not None:
    #         tag_data["note"] = note[:50]
    #     return cast(
    #         "dict",
    #         self.api.put_request(
    #             f"tags/{tag_id}",
    #             data=json.dumps(tag_data),
    #         ),
    #     )

    def delete_tag(self, tag_id: int) -> None:
        """
        Delete one Tag with its primary ID.

        `Args:`
            tag_id: `int`
                The primary ID for the Tag.
        `Returns:`
            None
        """
        self.api.delete_request(f"tags/{tag_id}")
        return None

    def get_all_tags(self) -> Table:
        """
        Get all Tags.

        `Returns:`
            Parsons `Table`
                A Parsons Table with all Tags.
        """

        # this endpoint does not use paging, it always returns the full single list array.
        tags = self.api.get_request("tags")

        return Table(tags)

    def add_contact_tags(self, contact_id: int, tag_ids: list[int]) -> None:
        """
        Add Tags to a Contact.

        `Args:`
            contact_id: `int`
                The primary ID for the contact.
            tag_ids: `list[int]`
                A list of Tag IDs to assign to the contact.
        `Returns:`
            `None`
        """

        all_tags = cast("dict", self.api.get_request("/tags"))
        tags_to_add = [tag for tag in all_tags if tag["id"] in tag_ids]

        self.api.post_request(
            f"customers/{contact_id}/tags",
            data=json.dumps(tags_to_add),
        )
        return None

    def remove_contact_tag(self, contact_id: int, tag_name_or_id: str | int) -> None:
        """
        Remove a Tag from a Contact.

        `Args:`
            contact_id: `int`
                The primary ID for the contact.
            tag_name_or_id: `str | int`
                The Tag name or ID to remove from the contact.
        `Returns:`
            `None`
        """

        tag_name = str(tag_name_or_id)

        if isinstance(tag_name_or_id, int) or tag_name_or_id.isdigit():
            tag_record = cast(
                "dict",
                self.api.get_request(f"/tags/{tag_name_or_id}"),
            )
            if tag_record:
                tag_name = tag_record.get("name")

        self.api.delete_request(f"customers/{contact_id}/tags/{tag_name}")
        return None

    def create_automation(self, automation_data: dict) -> dict:
        """
        Create a new Automation.

        `Args:`
            automation_data: `dict`
                A dictionary containing the Automation data.
                https://<subdomain>.prompt.io/prompt.io/rest/1.0/api-docs#!/automations/createAutomation

        `Returns:`
            `dict`
                The created Automation object.
        """

        return cast(
            "dict",
            self.api.post_request(
                "automations",
                data=json.dumps(automation_data),
            ),
        )

    def update_automation(self, automation_id: int, automation_data: dict) -> dict:
        """
        Update an existing Automation.

        `Args:`
            automation_id: `int`
                The primary ID for the Automation.
            automation_data: `dict`
                A dictionary containing the updated Automation data.
                https://<subdomain>.prompt.io/prompt.io/rest/1.0/api-docs#!/automations/updateAutomation

        `Returns:`
            `dict`
                The updated Automation object.
        """

        return cast(
            "dict",
            self.api.put_request(
                f"automations/{automation_id}",
                data=json.dumps(automation_data),
            ),
        )

    def delete_automation(self, automation_id: int) -> None:
        """
        Delete one Automation with its primary ID.

        `Args:`
            automation_id: `int`
                The primary ID for the Automation.
        `Returns:`
            None
        """

        self.api.delete_request(f"automations/{automation_id}")
        return None

    def get_all_automations(self) -> Table:
        """
        Get all Automations.

        `Returns:`
            Parsons `Table`
                A Parsons Table with all Automations.
        """

        automations = self._get_request_all_paginated_results("automations")

        return Table(automations)
