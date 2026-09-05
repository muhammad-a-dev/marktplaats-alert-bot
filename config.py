"""
All settings in one place: file paths, timings, limits and secrets.

Change a value here instead of editing the bot or the scraper.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# --------------------------------------------------------------------------- #
# Folders and files
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
USER_FILES_DIR = BASE_DIR / "userFiles"
LOG_DIR = BASE_DIR / "logs"

USERS_FILE = USER_FILES_DIR / "users.json"
ADMINS_FILE = USER_FILES_DIR / "admins.txt"
TOKEN_FILE = USER_FILES_DIR / "token.txt"
PROXY_FILE = USER_FILES_DIR / "proxy.txt"
ALREADY_DONE_FILE = USER_FILES_DIR / "already-done.txt"
SEARCHED_BEFORE_FILE = USER_FILES_DIR / "searched-before.txt"
EXCLUDED_USERS_FILE = USER_FILES_DIR / "excluded-users.txt"
EXCLUDED_KEYWORDS_FILE = USER_FILES_DIR / "excluded-keywords.txt"
ALERT_ADMINS_FILE = USER_FILES_DIR / "alert-admins.txt"

# --------------------------------------------------------------------------- #
# Discord
# --------------------------------------------------------------------------- #
PAID_ROLE_NAME = "Paid Access"       # role given to a user after activation
MAX_SELECT_OPTIONS = 25              # Discord allows 25 items in a dropdown
MAX_MESSAGE_LENGTH = 1900            # Discord's hard limit is 2000

# --------------------------------------------------------------------------- #
# Search behaviour
# --------------------------------------------------------------------------- #
DRY_RUN = False                      # True = log alerts instead of sending them
SEARCH_RESULT_LIMIT = 50             # listings requested per search
TITLE_MATCH_THRESHOLD = 75           # % of search words that must appear in the title
DEFAULT_DISTANCE_KM = 0              # used when a listing has no distance set

# --------------------------------------------------------------------------- #
# Network
# --------------------------------------------------------------------------- #
REQUEST_TIMEOUT = 30                 # seconds before a request is given up on
MAX_REQUEST_ATTEMPTS = 3             # retries before a request is abandoned
RETRY_DELAY_SECONDS = 5              # wait between retries
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# --------------------------------------------------------------------------- #
# Proxy / connection alerts
# --------------------------------------------------------------------------- #
PROXY_ALERT_AFTER = 3                # DM the admins after this many failures in a row
PROXY_ALERT_COOLDOWN = 30 * 60       # wait this long before repeating the same alert

# --------------------------------------------------------------------------- #
# Scraper pacing (seconds)
# --------------------------------------------------------------------------- #
DELAY_BETWEEN_KEYWORDS = 4
DELAY_BETWEEN_USERS = 15
DELAY_BETWEEN_CYCLES = 120
DELAY_WHEN_NO_USERS = 8

# --------------------------------------------------------------------------- #
# Supervisor (run.py)
# --------------------------------------------------------------------------- #
RESTART_DELAY_SECONDS = 5            # wait before restarting a crashed worker
MAX_RUNTIME_SECONDS = 20 * 60        # restart a worker every 20 min as a safety net
HEALTH_CHECK_INTERVAL = 2            # how often the supervisor checks its workers

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
LOG_MAX_BYTES = 5 * 1024 * 1024      # rotate the log file at 5 MB
LOG_BACKUP_COUNT = 3                 # keep 3 old log files
LOG_LEVEL = logging.INFO             # use logging.DEBUG to also record skipped listings


def load_discord_token():
    """Return the Discord bot token, or raise a clear error if it is missing."""
    if not TOKEN_FILE.exists():
        raise FileNotFoundError(f"Discord token file not found: {TOKEN_FILE}")

    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not token:
        raise ValueError(f"Discord token file is empty: {TOKEN_FILE}")
    return token


def load_proxies():
    """
    Return a requests-style proxy dict, or None when no proxy is configured.

    userFiles/proxy.txt should hold a single line such as:
        http://username:password@host:port
    """
    if not PROXY_FILE.exists():
        return None

    proxy_url = PROXY_FILE.read_text(encoding="utf-8").strip()
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


def load_alert_admins():
    """
    Return the Discord IDs that should be warned about proxy trouble.

    userFiles/alert-admins.txt holds one ID per line. Lines starting with # are
    treated as comments.
    """
    if not ALERT_ADMINS_FILE.exists():
        return []

    admin_ids = []
    for line in ALERT_ADMINS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            admin_ids.append(line)
    return admin_ids


def setup_logging(name):
    """
    Send log messages to both the console and a size-limited file.

    `name` becomes the file name, e.g. "scraper" -> logs/scraper.log
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Never let an odd character in a listing title crash the console output.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    file_handler = RotatingFileHandler(
        LOG_DIR / f"{name}.log",
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )

    logging.basicConfig(
        level=LOG_LEVEL,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[file_handler, logging.StreamHandler(sys.stdout)],
        force=True,
    )
    return logging.getLogger(name)
