"""
Reading and writing the data files in userFiles/.

Every function here fails softly: a missing or damaged file gives back an empty
result instead of stopping the bot or the scraper.
"""

import json
import logging
import os
import tempfile

log = logging.getLogger(__name__)


def read_json(file_path, default=None):
    """Load a JSON file. Returns `default` if the file is missing or broken."""
    if default is None:
        default = []

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        log.warning("File not found, using empty data: %s", file_path)
    except (json.JSONDecodeError, OSError) as error:
        log.error("Could not read %s: %s", file_path, error)
    return default


def save_json(file_path, data):
    """
    Write a JSON file safely.

    The data is written to a temporary file first and then moved into place, so
    the real file is never left half-written if the process stops mid-save.
    """
    directory = os.path.dirname(str(file_path)) or "."
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=directory, delete=False, suffix=".tmp"
        ) as temp_file:
            json.dump(data, temp_file, indent=4)
            temp_path = temp_file.name

        os.replace(temp_path, file_path)
        return True
    except OSError as error:
        log.error("Could not save %s: %s", file_path, error)
        return False


def read_lines(file_path):
    """Read a text file into a list of non-empty, stripped lines."""
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return [line.strip() for line in file if line.strip()]
    except FileNotFoundError:
        log.warning("File not found, using empty list: %s", file_path)
    except OSError as error:
        log.error("Could not read %s: %s", file_path, error)
    return []


def append_line(file_path, text):
    """Add one line to the end of a text file, creating it when needed."""
    try:
        with open(file_path, "a", encoding="utf-8") as file:
            file.write(f"{text}\n")
        return True
    except OSError as error:
        log.error("Could not write to %s: %s", file_path, error)
        return False
