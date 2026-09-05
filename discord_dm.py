"""
Sending a direct message to a Discord user through the REST API.

The scraper is not a Discord client, so it opens a DM channel and posts the
message itself instead of going through discord.py.
"""

import logging

import requests

import config

log = logging.getLogger(__name__)

API_BASE_URL = "https://discord.com/api/v10"


def send_direct_message(user_id, message, token):
    """
    Send `message` as a DM to `user_id`.

    Returns True when Discord accepted the message, False otherwise. Never
    raises, so a Discord outage cannot stop the scraper.
    """
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
    }

    try:
        # Step 1: open (or reuse) a DM channel with this user.
        channel_response = requests.post(
            f"{API_BASE_URL}/users/@me/channels",
            headers=headers,
            json={"recipient_id": str(user_id)},
            timeout=config.REQUEST_TIMEOUT,
        )

        if channel_response.status_code != 200:
            log.error(
                "Could not open a DM channel with %s: HTTP %s - %s",
                user_id, channel_response.status_code, channel_response.text[:200],
            )
            return False

        channel_id = channel_response.json().get("id")
        if not channel_id:
            log.error("Discord returned no DM channel id for user %s", user_id)
            return False

        # Step 2: post the message, mentioning the user so they get a ping.
        message_response = requests.post(
            f"{API_BASE_URL}/channels/{channel_id}/messages",
            headers=headers,
            json={"content": f"<@{user_id}> {message}"},
            timeout=config.REQUEST_TIMEOUT,
        )

        if message_response.status_code not in (200, 201):
            log.error(
                "Could not send DM to %s: HTTP %s - %s",
                user_id, message_response.status_code, message_response.text[:200],
            )
            return False

        return True

    except (requests.RequestException, ValueError) as error:
        log.error("Discord request failed for user %s: %s", user_id, error)
        return False


def send_admin_alert(message, token):
    """
    Warn every admin in alert-admins.txt that something is wrong.

    Used for proxy and connection problems. Returns how many admins were
    reached.
    """
    admin_ids = config.load_alert_admins()
    if not admin_ids:
        log.warning("No admins listed in %s, alert not sent", config.ALERT_ADMINS_FILE)
        return 0

    reached = 0
    for admin_id in admin_ids:
        if send_direct_message(admin_id, f"**Scraper alert**\n{message}", token):
            reached += 1

    log.info("Admin alert delivered to %s of %s admin(s)", reached, len(admin_ids))
    return reached
