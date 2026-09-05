"""
Everything that talks to Marktplaats.nl.

Two things are fetched here:
  1. the search results for a saved keyword (JSON API)
  2. the HTML of a single listing page, when the auction price or the seller
     account age is needed
"""

import logging
import re
import time
import urllib.parse

import requests

import config
from utils import to_float, to_int

log = logging.getLogger(__name__)

SEARCH_API_URL = "https://www.marktplaats.nl/lrp/api/search"
LISTING_BASE_URL = "https://www.marktplaats.nl/"
SELLER_BASE_URL = "https://www.marktplaats.nl/u"

# A real listing page always contains these fields. If none of them are there we
# were blocked or the listing is gone.
PAGE_LOADED_MARKERS = ("activeYears", "priceType")

CURRENT_BID_PATTERN = re.compile(r'"currentMinimumBid":([^,]+)')

# Seller account age, newest page layout first. Marktplaats has changed the
# wording before, so older layouts are kept as a fallback.
SELLER_AGE_PATTERNS = (
    re.compile(r'"activeYears":(\d+)'),        # data field, always present
    re.compile(r"(\d+) jaar op Marktplaats"),  # visible text
    re.compile(r">(\d+) jaar ac"),             # layout used before 2026
)

HEADERS = {"User-Agent": config.USER_AGENT}


def build_search_url(keyword):
    """Build the search API URL for one saved keyword."""
    distance_km = to_int(keyword.get("distance-range"), config.DEFAULT_DISTANCE_KM)
    distance_meters = distance_km * 1000
    postal_code = str(keyword.get("postal-code", "")).strip()
    search_term = urllib.parse.quote(str(keyword.get("product", "")).strip())

    return (
        f"{SEARCH_API_URL}?attributesByKey[]=offeredSince%3AVandaag"
        f"&distanceMeters={distance_meters}"
        f"&limit={config.SEARCH_RESULT_LIMIT}"
        f"&offset=0"
        f"&postcode={postal_code}"
        f"&query={search_term}"
        f"&searchInTitleAndDescription=true"
        f"&sortBy=SORT_INDEX&sortOrder=DECREASING&viewOptions=list-view"
    )


def search_listings(keyword, proxies=None):
    """
    Fetch today's listings for one keyword.

    Returns a list of listings when the search worked, which may be empty when
    there is simply nothing for sale. Returns None when every attempt failed,
    so the caller can tell "no results" apart from "the connection is broken".
    """
    url = build_search_url(keyword)
    product = keyword.get("product", "?")

    for attempt in range(1, config.MAX_REQUEST_ATTEMPTS + 1):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                proxies=proxies,
                timeout=config.REQUEST_TIMEOUT,
            )
            return response.json().get("listings", [])
        except (requests.RequestException, ValueError) as error:
            log.warning(
                "Search failed for '%s' (attempt %s/%s): %s",
                product, attempt, config.MAX_REQUEST_ATTEMPTS, error,
            )
            time.sleep(config.RETRY_DELAY_SECONDS)

    log.error("Giving up on search for '%s'", product)
    return None


def fetch_listing_page(listing_url, proxies=None):
    """
    Download the HTML of one listing page.

    Returns an empty string when the page cannot be loaded, which usually means
    the listing was removed or the proxy is being blocked.
    """
    for attempt in range(1, config.MAX_REQUEST_ATTEMPTS + 1):
        try:
            response = requests.get(
                listing_url,
                headers=HEADERS,
                proxies=proxies,
                timeout=config.REQUEST_TIMEOUT,
            )
            html = response.text
        except requests.RequestException as error:
            log.warning(
                "Page request failed %s (attempt %s/%s): %s",
                listing_url, attempt, config.MAX_REQUEST_ATTEMPTS, error,
            )
            time.sleep(config.RETRY_DELAY_SECONDS)
            continue

        if any(marker in html for marker in PAGE_LOADED_MARKERS):
            return html

        log.warning(
            "Listing page not available or blocked (attempt %s/%s): %s",
            attempt, config.MAX_REQUEST_ATTEMPTS, listing_url,
        )
        time.sleep(config.RETRY_DELAY_SECONDS)

    return ""


def parse_current_bid(html):
    """Read the current minimum bid (in euros) from a listing page. 0 if unknown."""
    match = CURRENT_BID_PATTERN.search(html)
    if not match:
        return 0.0

    raw_value = match.group(1)
    if "-" in raw_value:  # negative values mean "no bid yet"
        return 0.0

    return to_float(raw_value) / 100


def parse_seller_age(html):
    """Read the seller's account age in years from a listing page. 0 if unknown."""
    for pattern in SELLER_AGE_PATTERNS:
        match = pattern.search(html)
        if match:
            return to_int(match.group(1), 0)
    return 0


def build_listing_url(listing_id):
    """Public URL of a listing."""
    return f"{LISTING_BASE_URL}{listing_id}"


def build_seller_url(seller_name, seller_id):
    """Public URL of a seller profile."""
    return f"{SELLER_BASE_URL}/{seller_name}/{seller_id}/".lower()
