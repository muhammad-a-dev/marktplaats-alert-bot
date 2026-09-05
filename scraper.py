"""
The scraper worker.

It keeps repeating one simple cycle:

    for every user -> for every saved search -> ask Marktplaats for today's
    listings -> drop the ones that do not fit -> DM the user about the rest

Run it with `python run.py scraper`, or on its own with `python scraper.py`.
"""

import logging
import time

import config
import marktplaats
import storage
from discord_dm import send_admin_alert, send_direct_message
from utils import shorten, title_match_percentage, to_float

log = logging.getLogger("scraper")

# What to do with a single listing after checking it.
SKIP = "skip"        # seen in an earlier run, leave it alone
REJECT = "reject"    # does not fit the filters, remember it so we skip it later
ALERT = "alert"      # a match, send the user a DM


class Scraper:
    """Searches Marktplaats for every saved keyword and alerts the users."""

    def __init__(self):
        self.token = config.load_discord_token()
        self.proxies = config.load_proxies()

        # Listings already handled, kept in memory so we do not re-read a very
        # large file for every search.
        self.already_done = set(storage.read_lines(config.ALREADY_DONE_FILE))

        # Searches that have run at least once. The very first run of a new
        # search only records its results, it does not DM the user, otherwise
        # they would get every listing of the day at once.
        self.searched_before = set(storage.read_lines(config.SEARCHED_BEFORE_FILE))

        # Connection health. After several failures in a row the admins get a
        # DM, because that almost always means the proxy is down or blocked.
        self.failures_in_a_row = 0
        self.alert_is_active = False
        self.last_alert_at = 0.0

        log.info(
            "Scraper ready - %s listings remembered, %s searches known, proxy %s",
            len(self.already_done),
            len(self.searched_before),
            "on" if self.proxies else "off",
        )

    # ----------------------------------------------------------------- #
    # Main loop
    # ----------------------------------------------------------------- #
    def run_forever(self):
        """Keep running search cycles until the process is stopped."""
        while True:
            users = storage.read_json(config.USERS_FILE)

            if not users:
                log.info("No users configured, waiting...")
                time.sleep(config.DELAY_WHEN_NO_USERS)
                continue

            for user in users:
                self._process_user(user)
                time.sleep(config.DELAY_BETWEEN_USERS)

            log.info("Cycle finished, next one in %s seconds", config.DELAY_BETWEEN_CYCLES)
            time.sleep(config.DELAY_BETWEEN_CYCLES)

    def _process_user(self, user):
        """Run every saved search of one user."""
        user_name = user.get("name", "unknown")

        for keyword in user.get("listings", []):
            try:
                listings = marktplaats.search_listings(keyword, self.proxies)

                # None means the connection failed, not that nothing is for sale.
                if listings is None:
                    self._record_failure(f"search for '{keyword.get('product', '?')}'")
                    time.sleep(config.DELAY_BETWEEN_KEYWORDS)
                    continue

                self._record_success()
                log.info(
                    "%s | '%s' | %s result(s)",
                    user_name, keyword.get("product", "?"), len(listings),
                )
                self._handle_results(listings, keyword, user)
            except Exception as error:  # one bad search must not stop the rest
                log.exception(
                    "Unexpected error while searching '%s' for %s: %s",
                    keyword.get("product", "?"), user_name, error,
                )

            time.sleep(config.DELAY_BETWEEN_KEYWORDS)

    # ----------------------------------------------------------------- #
    # Filtering
    # ----------------------------------------------------------------- #
    def _handle_results(self, listings, keyword, user):
        """Check every search result and DM the user about the good ones."""
        # Reloaded each time so admin changes take effect without a restart.
        blocked_sellers = {line.lower() for line in storage.read_lines(config.EXCLUDED_USERS_FILE)}
        excluded_keywords = [line.lower() for line in storage.read_lines(config.EXCLUDED_KEYWORDS_FILE)]

        keyword_id = keyword.get("id", "")
        is_first_run = keyword_id not in self.searched_before

        for listing in listings:
            decision, message = self._check_listing(
                listing, keyword, user, blocked_sellers, excluded_keywords
            )

            if decision == SKIP:
                continue

            if decision == ALERT and not is_first_run:
                if not self._send_alert(user, message):
                    # Leave it unmarked so the alert is retried next cycle.
                    continue

            self._remember(self._listing_key(listing, user))

        if is_first_run and keyword_id:
            self.searched_before.add(keyword_id)
            storage.append_line(config.SEARCHED_BEFORE_FILE, keyword_id)
            log.info("First run of search '%s' recorded, alerts start next cycle", keyword_id)

    def _check_listing(self, listing, keyword, user, blocked_sellers, excluded_keywords):
        """
        Decide what to do with one listing.

        Returns (SKIP | REJECT | ALERT, message). The message is only filled in
        for ALERT.
        """
        listing_id = str(listing.get("itemId", ""))
        title = listing.get("title", "")
        description = listing.get("description", "")
        price_info = listing.get("priceInfo", {})
        price_type = str(price_info.get("priceType", "")).upper().strip()
        seller = listing.get("sellerInformation", {})
        seller_id = str(seller.get("sellerId", ""))
        seller_name = seller.get("sellerName", "")

        listing_url = marktplaats.build_listing_url(listing_id)
        unique_key = self._listing_key(listing, user)

        min_price = to_float(keyword.get("min-price"))
        max_price = to_float(keyword.get("max-price"))
        minimum_seller_age = to_float(keyword.get("seller-account-age"))

        # 1. Already handled in an earlier cycle.
        if unique_key in self.already_done:
            return SKIP, None

        log.debug("Checking %s | %s | %s", listing_id, price_type, title)

        # 2. Seller is blacklisted.
        if seller_id.lower() in blocked_sellers:
            return self._reject(title, "blacklisted seller")

        # 3. Title contains a banned word (cases, repairs, iCloud locked, ...).
        if any(word in title.lower() for word in excluded_keywords):
            return self._reject(title, "excluded keyword")

        # 4. Title does not really match what the user searched for.
        match_score = title_match_percentage(keyword.get("product", ""), title)
        if match_score < config.TITLE_MATCH_THRESHOLD:
            return self._reject(title, f"title match only {match_score:.0f}%")

        # 5. Auctions with a hidden reserve price are never useful.
        if "RESERVE" in price_type:
            return self._reject(title, "reserve price")

        price = to_float(price_info.get("priceCents")) / 100

        # A "minimum bid" listing that already shows a price behaves like a
        # fixed price listing.
        if price_type == "MIN_BID" and price > 0:
            price_type = "FIXED"

        # 6. Fixed price must fall inside the user's price range.
        if price_type == "FIXED":
            if price < min_price:
                return self._reject(title, f"price {price} below {min_price}")
            if price > max_price:
                return self._reject(title, f"price {price} above {max_price}")

        # 7. The listing page is only downloaded when we actually need it:
        #    to read the seller's account age or the current auction bid.
        page_html = ""
        if minimum_seller_age > 0 or price_type != "FIXED":
            page_html = marktplaats.fetch_listing_page(listing_url, self.proxies)
            if not page_html:
                self._record_failure(f"listing page {listing_url}")
                return self._reject(title, "listing page unavailable")
            self._record_success()

        # 8. Seller account must be old enough.
        if minimum_seller_age > 0:
            seller_age = marktplaats.parse_seller_age(page_html)
            if seller_age < minimum_seller_age:
                return self._reject(
                    title, f"seller account {seller_age}y, needs {minimum_seller_age:.0f}y"
                )

        # 9. For auctions, use the current bid instead of the listed price.
        if price_type != "FIXED":
            price = marktplaats.parse_current_bid(page_html)
            if price != 0:
                if price < min_price:
                    return self._reject(title, f"bid {price} below {min_price}")
                if price > max_price:
                    return self._reject(title, f"bid {price} above {max_price}")

        message = self._build_message(
            title=title,
            price=price,
            price_type=price_type,
            description=description,
            seller_name=seller_name,
            seller_url=marktplaats.build_seller_url(seller_name, seller_id),
            listing_url=listing_url,
        )
        log.info("MATCH for %s | %s | %s", user.get("name", "?"), price, title)
        return ALERT, message

    # ----------------------------------------------------------------- #
    # Helpers
    # ----------------------------------------------------------------- #
    @staticmethod
    def _listing_key(listing, user):
        """Unique key per listing per user, so two users can both be alerted."""
        return f"{listing.get('itemId', '')}:{user.get('name', '')}"

    @staticmethod
    def _reject(title, reason):
        """Log why a listing was dropped and return a REJECT decision."""
        log.debug("Dropped '%s': %s", title, reason)
        return REJECT, None

    # ----------------------------------------------------------------- #
    # Connection health
    # ----------------------------------------------------------------- #
    def _record_failure(self, what_failed):
        """
        Count a failed request and warn the admins once it keeps happening.

        A single failure is normal, the internet is not perfect. Several in a
        row almost always means the proxy is down, blocked or out of credit.
        """
        self.failures_in_a_row += 1
        log.warning("Connection failure %s in a row (%s)", self.failures_in_a_row, what_failed)

        if self.failures_in_a_row < config.PROXY_ALERT_AFTER:
            return

        # Do not send the same warning over and over while it stays broken.
        if time.time() - self.last_alert_at < config.PROXY_ALERT_COOLDOWN:
            return

        self.last_alert_at = time.time()
        self.alert_is_active = True

        message = (
            f"{self.failures_in_a_row} connection failures in a row.\n"
            f"Last one: {what_failed}\n\n"
            f"The proxy is probably down, blocked or out of traffic. "
            f"Check userFiles/proxy.txt and the logs.\n"
            f"No alerts can be sent to customers until this is fixed."
        )

        if config.DRY_RUN:
            log.info("[DRY RUN] would send admin alert: %s", message.replace("\n", " "))
            return

        log.error("Proxy looks broken, warning the admins")
        send_admin_alert(message, self.token)

    def _record_success(self):
        """Reset the failure count, and tell the admins when things recover."""
        if self.alert_is_active:
            self.alert_is_active = False
            self.last_alert_at = 0.0
            log.info("Connection recovered, telling the admins")
            if not config.DRY_RUN:
                send_admin_alert("Connection is working again, alerts have resumed.", self.token)

        self.failures_in_a_row = 0

    def _remember(self, unique_key):
        """Record a listing so it is never checked again for this user."""
        if unique_key in self.already_done:
            return
        self.already_done.add(unique_key)
        storage.append_line(config.ALREADY_DONE_FILE, unique_key)

    @staticmethod
    def _build_message(title, price, price_type, description, seller_name,
                       seller_url, listing_url):
        """Build the DM text. The description is trimmed to fit Discord's limit."""
        start = (
            f"\nPRODUCT: {title}"
            f"\n\nPrice: {price}"
            f"\n\nPrice Type: {price_type}"
            f"\n\nDESCRIPTION: "
        )
        end = (
            f"\n\nSELLER NAME: {seller_name}"
            f"\n\nSELLER URL: {seller_url}"
            f"\n\nURL: {listing_url}"
        )

        room_left = config.MAX_MESSAGE_LENGTH - len(start) - len(end)
        return start + shorten(description, max(room_left, 0)) + end

    def _send_alert(self, user, message):
        """DM one user about a matching listing. Returns True when it worked."""
        discord_id = user.get("discord-id")
        if not discord_id:
            log.warning("User %s has no Discord id, cannot send alert", user.get("name", "?"))
            return False

        # Test mode: show what would be sent, but do not bother the user.
        if config.DRY_RUN:
            log.info("[DRY RUN] would alert %s: %s", user.get("name", "?"),
                     message.replace("\n", " ").strip()[:120])
            return True

        if send_direct_message(discord_id, message, self.token):
            log.info("Alert sent to %s", user.get("name", "?"))
            return True

        log.error("Alert could not be sent to %s", user.get("name", "?"))
        return False


def main():
    """Start the scraper and restart it if it ever crashes."""
    config.setup_logging("scraper")

    while True:
        try:
            Scraper().run_forever()
        except KeyboardInterrupt:
            log.info("Scraper stopped by user")
            return
        except Exception as error:
            log.exception("Scraper crashed: %s", error)
            log.info("Restarting in %s seconds", config.RESTART_DELAY_SECONDS)
            time.sleep(config.RESTART_DELAY_SECONDS)


if __name__ == "__main__":
    main()
