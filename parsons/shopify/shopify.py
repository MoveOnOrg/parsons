import json
import logging
import requests
import time

from parsons.etl.table import Table
from parsons.utilities import check_env

logger = logging.getLogger(__name__)


class Shopify(object):
    """
    Instantiate the Shopify class

    `Args:`
        subdomain: str
            The Shopify subdomain (e.g. ``myorg`` for myorg.myshopify.com) Not required if
            ``SHOPIFY_SUBDOMAIN`` env variable set.
        password: str
            The Shopify account password. Not required if ``SHOPIFY_PASSWORD`` env
            variable set.
        api_key: str
            The authorized ActionKit user password. Not required if ``SHOPIFY_API_KEY``
            env variable set.
    """

    def __init__(self, subdomain=None, password=None, api_key=None):
        self.subdomain = check_env.check('SHOPIFY_SUBDOMAIN', subdomain)
        self.password = check_env.check('SHOPIFY_PASSWORD', password)
        self.api_key = check_env.check('SHOPIFY_API_KEY', api_key)
