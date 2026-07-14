import json
import logging
import urllib.parse
from typing import Any, Literal, Optional, cast

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
        time_window: Optional[
            Literal[
                "last_60_mins",
                "yesterday",
                "today",
                "last_month",
                "this_month",
                "last_quarter",
                "this_quarter",
                "last_year",
                "this_year",
                "custom",
                "all_time",
            ]
        ] = None,
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

    def update_contact_global_opt_out(
        self, contact_id: int, is_opted_out: bool, updated_contact_name: Optional[str] = None
    ) -> dict:
        """
        Opt a Contact **out** of receiving messages.

        `Args:`
            contact_id: `int`
                The primary ID for the contact.
            is_opted_out: `bool`
                `True` to opt the contact out, `False` to opt back in
                (only possible if not via carrier keyword).
            updated_contact_name: `str`
                `Optional` A new display name for the contact.
        `Returns:`
            `dict`
                The updated Contact object.
        """

        data: dict = {"globalOptOut": is_opted_out}

        if updated_contact_name:
            data["displayName"] = updated_contact_name

        return cast(
            "dict",
            self.api.put_request(f"customers/{contact_id}", data=json.dumps(data)),
        )

    def delete_contact_data_fields(self, contact_id: int, data_field_keys: list[str]) -> None:
        """
        Delete specific data fields for a Contact.

        Reserved fields (keys prefixed with `pio_`) are skipped, as are any fields
        the API reports as non-modifiable reserved fields.

        `Args:`
            contact_id: `int`
                The primary ID for the contact.
            data_field_keys: `list[str]`
                The data field keys to delete from the contact.
        `Returns:`
            None
        """

        for key in data_field_keys:
            field_key = str(key or "").strip()
            if not field_key:
                continue
            if field_key.startswith("pio_"):
                logger.info("Skipping reserved data field `%s`.", field_key)
                continue

            endpoint = (
                f"data/customer/{urllib.parse.quote(str(contact_id))}"
                f"/keys/{urllib.parse.quote(field_key)}"
            )
            response = self.api.request(endpoint, "DELETE")

            if response.status_code >= 400:
                is_reserved_field_error = (
                    response.status_code == 500 and "cannotModifyReservedField" in response.text
                )
                if is_reserved_field_error:
                    logger.info("Skipping non-modifiable data field `%s`.", field_key)
                    continue
                # Delegate to the connector's standard error handling for anything else.
                self.api.validate_response(response)

            logger.debug("Deleted data field `%s` for contact %s.", field_key, contact_id)

        return None

    def delete_contact_instant_app_data(self, identity_key: str) -> Table:
        """
        Collect all Instant App element data associated with a Contact's message
        history.

        Fetches the Contact's message history, discovers every unique Instant App
        referenced by those messages, and gathers each app's stored element data.

        `Args:`
            identity_key: `str`
                The identity key (e.g. phone number) of the contact.
        `Returns:`
            Parsons `Table`
                A Table with columns `id`, `element_key`, and `element_value`, one
                row per Instant App element value.
        """

        identity_key = str(identity_key or "").strip()
        if not identity_key:
            raise ValueError("`identity_key` must be provided.")

        history_payload = self.api.get_request(
            f"messages/history/{urllib.parse.quote(identity_key)}"
        )

        if isinstance(history_payload, list):
            messages = history_payload
        elif isinstance(history_payload, dict):
            messages = history_payload.get("items") or history_payload.get("data") or []
        else:
            messages = []

        # Collect the unique Instant App IDs referenced by the messages, preserving
        # the order in which they were first seen.
        instant_app_ids = []
        for message in messages:
            instant_app = (message or {}).get("instantApp") or {}
            instant_app_id = instant_app.get("id")
            if instant_app_id in (None, "") or instant_app_id in instant_app_ids:
                continue
            instant_app_ids.append(instant_app_id)

        logger.info("Discovered %s instant app(s).", len(instant_app_ids))

        rows = []
        for instant_app_id in instant_app_ids:
            elements_payload = self.api.get_request(
                f"instant_apps/{urllib.parse.quote(str(instant_app_id))}/elements"
            )
            existing_data = (
                elements_payload.get("data") if isinstance(elements_payload, dict) else None
            )
            if not isinstance(existing_data, dict) or not existing_data:
                logger.debug("No element data found for instant app `%s`.", instant_app_id)
                continue

            for key, value in existing_data.items():
                rows.append(
                    {
                        "id": str(instant_app_id),
                        "element_key": str(key),
                        "element_value": str(value),
                    }
                )

        return Table(rows if rows else [["id", "element_key", "element_value"]])

    def delete_contact_polls_surveys(self, contact_id: int) -> None:
        """
        Delete all polls and surveys (Instant Apps) associated with a Contact.

        Fetches the Contact's Instant Apps and deletes the poll/survey for each
        one that exposes a `schemaApiId`.

        `Args:`
            contact_id: `int`
                The primary ID for the contact.
        `Returns:`
            None
        """

        list_payload = self.api.get_request(
            f"customers/{urllib.parse.quote(str(contact_id))}/instant_apps",
            params={"first": 0, "max": 100, "desc": True},
        )

        if isinstance(list_payload, list):
            instant_apps = list_payload
        elif isinstance(list_payload, dict):
            instant_apps = list_payload.get("items") or list_payload.get("data") or []
        else:
            instant_apps = []

        logger.info("Fetched %s instant app(s) for contact %s.", len(instant_apps), contact_id)

        for app in instant_apps:
            schema_api_id = str((app or {}).get("schemaApiId") or "").strip()
            if not schema_api_id:
                continue

            self.api.delete_request(f"instant_apps/polls/{urllib.parse.quote(schema_api_id)}")
            logger.debug("Deleted poll/survey `%s`.", schema_api_id)

        return None

    def delete_contact_wallet_cards(self, contact_id: int) -> None:
        """
        Delete all wallet card instances associated with a Contact.

        Fetches every wallet card, then for each card deletes all of the card
        instances belonging to the given contact.

        `Args:`
            contact_id: `int`
                The primary ID for the contact.
        `Returns:`
            None
        """

        cards_payload = self.api.get_request("wallets/cards")
        wallet_cards = (
            cards_payload.get("walletCards") if isinstance(cards_payload, dict) else None
        ) or []

        wallet_card_ids = []
        for card in wallet_cards:
            card_id = (card or {}).get("id")
            if card_id in (None, ""):
                continue
            wallet_card_ids.append(card_id)

        logger.info("Fetched %s wallet card(s).", len(wallet_card_ids))

        for wallet_card_id in wallet_card_ids:
            instances_payload = self.api.get_request(
                f"wallets/cards/{urllib.parse.quote(str(wallet_card_id))}/instances",
                params={"customerId": contact_id, "first": 0, "max": 100},
            )
            models = (
                instances_payload.get("models") if isinstance(instances_payload, dict) else None
            ) or []

            instance_ids = []
            for model in models:
                instance_id = (model or {}).get("id")
                if instance_id in (None, ""):
                    continue
                instance_ids.append(instance_id)

            logger.debug(
                "Fetched %s instance(s) for wallet card `%s`.", len(instance_ids), wallet_card_id
            )

            for instance_id in instance_ids:
                self.api.delete_request(
                    f"wallets/cards/{urllib.parse.quote(str(wallet_card_id))}"
                    f"/instances/{urllib.parse.quote(str(instance_id))}"
                )
                logger.debug(
                    "Deleted wallet card instance `%s` (card `%s`).",
                    instance_id,
                    wallet_card_id,
                )

        return None

    def remove_contact_from_contact_lists(
        self, phone_number: str, contact_list_ids: list[str]
    ) -> None:
        """
        Remove a Contact from one or more Contact Lists.

        `Args:`
            phone_number: `str`
                The phone number identifying the contact.
            contact_list_ids: `list[str]`
                The IDs of the contact lists to remove the contact from.
        `Returns:`
            None
        """

        phone_number = str(phone_number or "").strip()
        if not phone_number:
            raise ValueError("`phone_number` must be provided.")

        for contact_list_id in contact_list_ids:
            if contact_list_id is None or str(contact_list_id).strip() == "":
                continue

            endpoint = (
                f"contact_lists/{urllib.parse.quote(str(contact_list_id))}"
                f"/contacts/{urllib.parse.quote(phone_number)}"
            )
            self.api.delete_request(endpoint)
            logger.debug("Removed contact from contact list `%s`.", contact_list_id)

        return None

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
