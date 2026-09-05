"""
The Discord bot worker.

It is the control panel for the service:

  * admins add or remove users, blacklist sellers and hand out licence codes
  * users activate their licence code and manage their saved searches

Everything is stored in userFiles/users.json, which the scraper reads.

Run it with `python run.py bot`, or on its own with `python bot.py`.
"""

import logging

import discord

import config
import storage
from utils import generate_license_code, shorten, to_int

log = logging.getLogger("bot")


class AlertBot(discord.Client):
    """
    A slash-command only bot.

    Everything runs through slash commands and buttons, so the bot never reads
    message text. That means it needs no privileged intents at all.
    """

    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = discord.app_commands.CommandTree(self)

    async def setup_hook(self):
        """Register the slash commands with Discord before the bot goes live."""
        try:
            synced = await self.tree.sync()
            log.info("Registered %s slash command(s): %s",
                     len(synced), ", ".join(f"/{c.name}" for c in synced))
        except discord.HTTPException as error:
            log.error("Could not sync slash commands: %s", error)


bot = AlertBot()


# --------------------------------------------------------------------------- #
# Small shared helpers
# --------------------------------------------------------------------------- #
def load_users():
    """Read all users from users.json."""
    return storage.read_json(config.USERS_FILE)


def save_users(users):
    """Write all users back to users.json."""
    return storage.save_json(config.USERS_FILE, users)


def find_user(users, discord_id):
    """Find one user by their Discord id, or None."""
    return next((user for user in users if user.get("discord-id") == discord_id), None)


def is_admin(interaction):
    """True when the Discord account is listed in admins.txt."""
    return interaction.user.name in storage.read_lines(config.ADMINS_FILE)


async def reply(interaction, text):
    """Send a private reply, whether or not the interaction was answered already."""
    try:
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)
    except discord.HTTPException as error:
        log.error("Could not reply to %s: %s", interaction.user, error)


def as_table(header, rows):
    """Format rows as a code block so the columns line up in Discord."""
    if not rows:
        return "```Nothing to show```"
    return "```" + header + "\n" + "\n".join(rows) + "```"


# --------------------------------------------------------------------------- #
# Admin panel
# --------------------------------------------------------------------------- #
class AddUserModal(discord.ui.Modal, title="Add a new user"):
    """Creates a user record and returns a fresh licence code."""

    name = discord.ui.TextInput(label="Name", placeholder="Enter user name...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        users = load_users()
        license_code = generate_license_code()

        users.append({
            "name": str(self.name.value).strip(),
            "license-code": license_code,
            "discord-id": "",
            "discord-username": "",
            "activated": False,
            "listings": [],
        })

        if save_users(users):
            log.info("Admin %s added user %s", interaction.user, self.name.value)
            await reply(interaction, f"User added.\nLicence code: `{license_code}`")
        else:
            await reply(interaction, "Could not save the user, please try again.")

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.exception("AddUserModal failed: %s", error)
        await reply(interaction, "Something went wrong, please try again.")


class BlacklistSellerModal(discord.ui.Modal, title="Blacklist a seller"):
    """Adds a seller id to excluded-users.txt so the scraper ignores them."""

    seller_id = discord.ui.TextInput(label="Seller ID", placeholder="Enter seller ID...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        seller = str(self.seller_id.value).strip()

        if seller in storage.read_lines(config.EXCLUDED_USERS_FILE):
            await reply(interaction, "That seller is already blacklisted.")
            return

        if storage.append_line(config.EXCLUDED_USERS_FILE, seller):
            log.info("Admin %s blacklisted seller %s", interaction.user, seller)
            await reply(interaction, "Seller added to the blacklist.")
        else:
            await reply(interaction, "Could not update the blacklist, please try again.")

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.exception("BlacklistSellerModal failed: %s", error)
        await reply(interaction, "Something went wrong, please try again.")


class DeleteUserSelect(discord.ui.Select):
    """Dropdown that deletes the chosen user. The value is the licence code."""

    def __init__(self, users):
        options = [
            discord.SelectOption(
                label=shorten(f"{user.get('name', '?')} | {user.get('discord-username') or 'not activated'}", 100),
                value=user["license-code"],
            )
            for user in users[: config.MAX_SELECT_OPTIONS]
            if user.get("license-code")
        ]
        super().__init__(placeholder="Choose a user to delete...", options=options)

    async def callback(self, interaction: discord.Interaction):
        license_code = self.values[0]
        users = load_users()
        remaining = [user for user in users if user.get("license-code") != license_code]

        if len(remaining) == len(users):
            await reply(interaction, "User not found.")
        elif save_users(remaining):
            log.info("Admin %s deleted a user", interaction.user)
            await reply(interaction, "User deleted.")
        else:
            await reply(interaction, "Could not save the change, please try again.")

        self.view.stop()


class AdminOptionsView(discord.ui.View):
    """Buttons shown to an admin."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Add User", style=discord.ButtonStyle.primary)
    async def add_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddUserModal())

    @discord.ui.button(label="Show All Users", style=discord.ButtonStyle.secondary)
    async def show_users(self, interaction: discord.Interaction, button: discord.ui.Button):
        rows = [
            f"{user.get('name', '')} | {user.get('license-code', '')} | "
            f"{user.get('discord-id', '')} | {user.get('discord-username', '')} | "
            f"{user.get('activated', False)}"
            for user in load_users()
        ]
        await reply(
            interaction,
            as_table("Name | LicenceCode | DiscordID | DiscordUsername | Activated", rows),
        )

    @discord.ui.button(label="Delete User", style=discord.ButtonStyle.danger)
    async def delete_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        users = load_users()
        if not users:
            await reply(interaction, "There are no users yet.")
            return

        view = discord.ui.View(timeout=None)
        view.add_item(DeleteUserSelect(users))
        await interaction.response.send_message("Select a user to delete:", view=view, ephemeral=True)

    @discord.ui.button(label="Blacklist Seller", style=discord.ButtonStyle.green)
    async def blacklist_seller(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BlacklistSellerModal())


# --------------------------------------------------------------------------- #
# User panel
# --------------------------------------------------------------------------- #
class LicenseCodeModal(discord.ui.Modal, title="Enter your licence code"):
    """Links a Discord account to an unused licence code."""

    license_code = discord.ui.TextInput(
        label="Licence code", placeholder="Enter your licence code...", required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        code = str(self.license_code.value).strip()
        users = load_users()

        account = next(
            (user for user in users
             if user.get("license-code", "").strip() == code and not user.get("activated")),
            None,
        )

        if account is None:
            await reply(interaction, "That licence code is invalid or already in use.")
            return

        account["discord-id"] = interaction.user.id
        account["discord-username"] = interaction.user.name
        account["activated"] = True

        if not save_users(users):
            await reply(interaction, "Could not activate your licence, please try again.")
            return

        await self._give_paid_role(interaction)
        log.info("User %s activated a licence", interaction.user)

        await reply(interaction, "Great, you are now a member!")
        await interaction.followup.send(
            "Here are your options:",
            view=UserOptionsView(interaction.user.id),
            ephemeral=True,
        )

    @staticmethod
    async def _give_paid_role(interaction):
        """Try to add the paid role. Not being able to is not a failure."""
        try:
            role = discord.utils.get(interaction.guild.roles, name=config.PAID_ROLE_NAME)
            if role:
                await interaction.user.add_roles(role)
        except (discord.HTTPException, AttributeError) as error:
            log.warning("Could not give the paid role to %s: %s", interaction.user, error)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.exception("LicenseCodeModal failed: %s", error)
        await reply(interaction, "Something went wrong, please try again.")


class AddListingModal(discord.ui.Modal, title="Add a search"):
    """Saves one search keyword with its filters. Discord allows 5 fields here."""

    product = discord.ui.TextInput(label="Product", placeholder="Enter search term...", required=True)
    postal_code = discord.ui.TextInput(label="Location (zipcode)", placeholder="e.g. 3823ZG", required=True)
    distance_range = discord.ui.TextInput(
        label="Distance range (km)", placeholder="e.g. 80", required=False
    )
    price_range = discord.ui.TextInput(
        label="Price range (min-max)", placeholder="e.g. 200-350", required=False
    )
    seller_account_age = discord.ui.TextInput(
        label="Minimum seller age (years)", placeholder="0 for no limit", required=False
    )

    def __init__(self, discord_id):
        super().__init__(timeout=None)
        self.discord_id = discord_id

    async def on_submit(self, interaction: discord.Interaction):
        min_price, max_price = self._split_price_range(str(self.price_range.value))

        users = load_users()
        account = find_user(users, self.discord_id)
        if account is None:
            await reply(interaction, "Your account was not found, run /start again.")
            return

        account.setdefault("listings", []).append({
            "id": generate_license_code(),
            "product": str(self.product.value).strip(),
            "distance-range": str(self.distance_range.value).strip() or "0",
            "postal-code": str(self.postal_code.value).strip(),
            "min-price": min_price,
            "max-price": max_price,
            "seller-account-age": to_int(self.seller_account_age.value, 0),
        })

        if save_users(users):
            log.info("User %s added search '%s'", interaction.user, self.product.value)
            await reply(interaction, "Search added. Alerts start from the next scan.")
        else:
            await reply(interaction, "Could not save the search, please try again.")

    @staticmethod
    def _split_price_range(price_range):
        """Turn "200-350" into ("200", "350"). Anything else becomes ("0", "0")."""
        if "-" in price_range:
            minimum, _, maximum = price_range.partition("-")
            return minimum.strip() or "0", maximum.strip() or "0"
        return "0", "0"

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.exception("AddListingModal failed: %s", error)
        await reply(interaction, "Something went wrong, please try again.")


class DeleteListingSelect(discord.ui.Select):
    """Dropdown that deletes the chosen search. The value is the search id."""

    def __init__(self, discord_id, listings):
        options = [
            discord.SelectOption(
                label=shorten(
                    f"{listing.get('product', '?')} | {listing.get('postal-code', '')} | "
                    f"{listing.get('min-price', '0')}-{listing.get('max-price', '0')}",
                    100,
                ),
                value=listing["id"],
            )
            for listing in listings[: config.MAX_SELECT_OPTIONS]
            if listing.get("id")
        ]
        super().__init__(placeholder="Choose a search to delete...", options=options)
        self.discord_id = discord_id

    async def callback(self, interaction: discord.Interaction):
        listing_id = self.values[0]
        users = load_users()
        account = find_user(users, self.discord_id)

        if account is None:
            await reply(interaction, "Your account was not found, run /start again.")
            self.view.stop()
            return

        remaining = [item for item in account.get("listings", []) if item.get("id") != listing_id]

        if len(remaining) == len(account.get("listings", [])):
            await reply(interaction, "Search not found.")
        else:
            account["listings"] = remaining
            if save_users(users):
                log.info("User %s deleted a search", interaction.user)
                await reply(interaction, "Search deleted.")
            else:
                await reply(interaction, "Could not save the change, please try again.")

        self.view.stop()


class UserOptionsView(discord.ui.View):
    """Buttons shown to an activated user."""

    def __init__(self, discord_id):
        super().__init__(timeout=None)
        self.discord_id = discord_id

    def _my_listings(self):
        account = find_user(load_users(), self.discord_id)
        return account.get("listings", []) if account else []

    @discord.ui.button(label="Add Search", style=discord.ButtonStyle.primary)
    async def add_listing(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddListingModal(self.discord_id))

    @discord.ui.button(label="Show All Searches", style=discord.ButtonStyle.secondary)
    async def show_listings(self, interaction: discord.Interaction, button: discord.ui.Button):
        rows = [
            f"{listing.get('product', '')} | {listing.get('distance-range', '')} | "
            f"{listing.get('postal-code', '')} | {listing.get('min-price', '')} | "
            f"{listing.get('max-price', '')} | {listing.get('seller-account-age', 0)}"
            for listing in self._my_listings()
        ]
        await reply(
            interaction,
            as_table("Product | Distance | PostalCode | Min | Max | SellerAge", rows),
        )

    @discord.ui.button(label="Delete Search", style=discord.ButtonStyle.danger)
    async def delete_listing(self, interaction: discord.Interaction, button: discord.ui.Button):
        listings = self._my_listings()
        if not listings:
            await reply(interaction, "You have no searches yet.")
            return

        view = discord.ui.View(timeout=None)
        view.add_item(DeleteListingSelect(self.discord_id, listings))
        await interaction.response.send_message("Select a search to delete:", view=view, ephemeral=True)


class RoleSelectView(discord.ui.View):
    """First screen: are you a user or an admin?"""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="User", style=discord.ButtonStyle.primary)
    async def user_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LicenseCodeModal())

    @discord.ui.button(label="Admin", style=discord.ButtonStyle.danger)
    async def admin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if is_admin(interaction):
            await interaction.response.send_message(
                "Welcome Admin", view=AdminOptionsView(), ephemeral=True
            )
        else:
            await reply(interaction, "You are not an admin.")


# --------------------------------------------------------------------------- #
# Slash commands
# --------------------------------------------------------------------------- #
@bot.tree.command(name="start", description="Open your control panel")
async def start_command(interaction: discord.Interaction):
    account = find_user(load_users(), interaction.user.id)

    if account:
        await interaction.response.send_message("Hello, welcome back!", ephemeral=True)
        await interaction.followup.send(
            "Here are your options:",
            view=UserOptionsView(interaction.user.id),
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            "Select your type:", view=RoleSelectView(), ephemeral=True
        )


@bot.tree.command(name="admin", description="Open the admin panel")
async def admin_command(interaction: discord.Interaction):
    if is_admin(interaction):
        await interaction.response.send_message(
            "Welcome Admin", view=AdminOptionsView(), ephemeral=True
        )
    else:
        await interaction.response.send_message("You are not an admin.", ephemeral=True)


@bot.event
async def on_ready():
    """Report that the bot is connected and which servers it can see."""
    log.info("Bot is ready, logged in as %s", bot.user)
    for guild in bot.guilds:
        log.info("  server: %s (%s members)", guild.name, guild.member_count)


@bot.tree.error
async def on_command_error(interaction: discord.Interaction, error: Exception):
    """Catch anything a command raises so the user always gets an answer."""
    log.exception("Slash command failed: %s", error)
    await reply(interaction, "Something went wrong, please try again.")


def main():
    """Start the Discord bot."""
    config.setup_logging("bot")
    bot.run(config.load_discord_token(), log_handler=None)


if __name__ == "__main__":
    main()
