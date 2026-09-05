"""Small helpers shared by the bot and the scraper."""

import random
import string


def generate_license_code(length=12):
    """Create a random 12-character licence code for a new user."""
    characters = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(random.choice(characters) for _ in range(length))


def title_match_percentage(search_term, listing_title):
    """
    Return how much of the search term appears in a listing title, as a percent.

    Example: "iPhone 13 Pro" against "iPhone 13 Pro Max blauw" -> 100.0
    """
    search_words = search_term.lower().split()
    if not search_words:
        return 0.0

    title_words = listing_title.lower().split()
    matched = sum(1 for word in search_words if word in title_words)
    return matched / len(search_words) * 100


def to_float(value, default=0.0):
    """Convert a value to float, falling back to `default` when it is not a number."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value, default=0):
    """Convert a value to int, falling back to `default` when it is not a number."""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def shorten(text, max_length):
    """Cut text down to `max_length` characters and mark it with an ellipsis."""
    text = str(text)
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
