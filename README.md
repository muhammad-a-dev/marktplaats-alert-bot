# Marktplaats Alert Bot — Discord Bot for Marktplaats.nl Deal Alerts

**Get a Discord message the second a new listing appears on [Marktplaats.nl](https://www.marktplaats.nl).**

Marktplaats is the biggest second-hand marketplace in the Netherlands. Good deals
sell in minutes, so the person who sees a listing first usually wins it. This bot
watches Marktplaats for you and sends a direct message the moment something
matches what you are looking for — the right product, the right area, the right
price.

Built with **Python** and **discord.py**.

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-2.3%2B-5865F2?logo=discord&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)

---

## What you get

This is what lands in your Discord DMs:

```
PRODUCT: iPhone 15 Pro 128GB - Titanium, top staat

Price: 425.0

Price Type: FIXED

DESCRIPTION: Te koop aangeboden: iPhone 15 Pro in zeer goede staat...

SELLER NAME: jandevries

SELLER URL: https://www.marktplaats.nl/u/jandevries/20319447/

URL: https://www.marktplaats.nl/m2439093231
```

No refreshing the site. No missed deals.

---

## Features

- **Instant Discord alerts** — a DM the moment a matching listing goes live
- **Smart search filters** — product, postcode, distance in km, minimum and maximum price
- **Auction support** — reads the current bid on auction listings, not just the asking price
- **Seller age filter** — only hear about sellers whose account is old enough to trust
- **Keyword blacklist** — automatically skip phone cases, broken units, iCloud-locked devices and anything else you don't want
- **Seller blacklist** — block sellers you have had trouble with
- **No duplicates** — every listing is only ever sent once, per user
- **No first-run flood** — a brand new search records what is already on the site instead of dumping the whole day into your DMs
- **Multi-user** — runs for many customers at once, each with their own searches
- **Licence code system** — admins hand out codes, users activate themselves
- **Self-healing** — crashed workers restart on their own
- **Proxy health alerts** — admins get a DM when the connection breaks, and another when it recovers

---

## How it works

The project runs as two programs that share one data file. A small supervisor
keeps both of them alive.

```
                    run.py  (supervisor)
                          │
            ┌─────────────┴─────────────┐
            │                           │
        bot.py                      scraper.py
   Discord control panel        searches Marktplaats
            │                           │
            └────────► users.json ◄─────┘
```

The scraper repeats one simple cycle:

1. Read every user and every saved search
2. Ask the Marktplaats search API for **today's** listings near that user
3. Run each listing through the filters
4. Send a Discord DM for whatever is left
5. Remember it, so it is never sent twice

---

## How a listing is filtered

A listing has to pass **every** check before it becomes an alert:

| # | Check | Why |
|---|-------|-----|
| 1 | Not already sent | No duplicate DMs |
| 2 | Seller not blacklisted | Skip bad sellers |
| 3 | No banned words in the title | Skip cases, broken units, iCloud locks |
| 4 | At least 75% title match | "iPhone 13 Pro" should not match a Samsung |
| 5 | No hidden reserve price | Those auctions waste your time |
| 6 | Price inside your range | Only real deals |
| 7 | Seller account old enough | Avoid brand new throwaway accounts |
| 8 | Current bid inside your range | For auctions, the bid matters, not the asking price |

Checks 7 and 8 need the full listing page, so it is only downloaded when one of
them is actually switched on. Everything else runs off the search API alone,
which keeps the bot fast and light.

---

## Tech stack

| Part | Choice |
|------|--------|
| Language | Python 3.9+ |
| Discord | discord.py 2.x — slash commands, buttons, modals, dropdowns |
| HTTP | requests, with retries, timeouts and rotating proxy support |
| Data | Plain JSON and text files — no database to set up |
| Process control | subprocess supervisor with auto-restart |
| Logging | Rotating log files, one per worker |

---

## Getting started

**1. Clone and install**

```bash
git clone https://github.com/muhammad-a-dev/marktplaats-alert-bot.git
cd marktplaats-alert-bot
pip install -r requirements.txt
```

**2. Create your Discord bot**

- Go to the [Discord Developer Portal](https://discord.com/developers/applications) → **New Application**
- Open the **Bot** tab → **Reset Token** → copy it
- Go to **OAuth2 → URL Generator**
  - Scopes: `bot` and `applications.commands`
  - Permissions: `Manage Roles` and `Send Messages`
- Open the generated link and invite the bot to your server
- In your server, create a role called **`Paid Access`** and drag the bot's own role **above** it

**3. Set up your files**

Every file in `userFiles/` ships as a `.example`. Copy each one and drop the
`.example` from the name:

| Copy this | To this | Put inside |
|-----------|---------|------------|
| `token.txt.example` | `token.txt` | Your Discord bot token |
| `proxy.txt.example` | `proxy.txt` | Your proxy URL (optional but recommended) |
| `admins.txt.example` | `admins.txt` | Discord usernames allowed to use `/admin` |
| `alert-admins.txt.example` | `alert-admins.txt` | Discord IDs to warn about proxy problems |
| `users.example.json` | `users.json` | Start with `[]` for a fresh install |
| `excluded-keywords.txt.example` | `excluded-keywords.txt` | Words that disqualify a listing |
| `excluded-users.txt.example` | `excluded-users.txt` | Seller IDs to ignore |

**4. Run it**

```bash
python run.py     # starts the bot and the scraper together
```

On Windows you can just double-click **`run.bat`** — it checks Python, installs
what is missing and starts everything.

---

## Using the bot

### For admins — `/admin`

| Button | What it does |
|--------|--------------|
| Add User | Creates a user and shows their new licence code |
| Show All Users | Lists everyone and whether they are activated |
| Delete User | Removes a user and all their searches |
| Blacklist Seller | Adds a seller ID to the ignore list |

### For users — `/start`

Press **User**, enter your licence code, and you are in. Then:

| Button | What it does |
|--------|--------------|
| Add Search | Save a new product to watch |
| Show All Searches | See everything you are watching |
| Delete Search | Stop watching something |

**What a search looks like**

| Field | Required | Example |
|-------|----------|---------|
| Product | yes | `iPhone 15 Pro` |
| Location (zipcode) | yes | `1011AB` |
| Distance range (km) | no | `80` |
| Price range (min-max) | no | `200-450` |
| Minimum seller age (years) | no | `2` |

---

## Project structure

```
marktplaats-alert-bot/
├── run.py            Supervisor — starts and restarts both workers
├── run.bat           One-click launcher for Windows
├── bot.py            Discord control panel (slash commands, buttons, modals)
├── scraper.py        The search, filter and alert loop
├── marktplaats.py    All requests to Marktplaats
├── discord_dm.py     Sends direct messages through the Discord API
├── storage.py        Safe reading and writing of the data files
├── utils.py          Small shared helpers
├── config.py         Every setting in one place
└── userFiles/        Your data and settings
```

Every setting lives in `config.py` — search limits, delays, retry counts, the
title match threshold, log size and more. You never have to edit the bot or the
scraper to tune it.

---

## Built to keep running

Unattended bots break at 3am. This one is built for that:

- A crashed worker restarts within seconds
- Every worker restarts every 20 minutes as a safety net
- Failed requests retry 3 times, then skip and move on — one bad search never stops the rest
- A failed DM is retried on the next cycle instead of being lost
- Missing or damaged data files are treated as empty, with a warning, instead of crashing
- Repeated connection failures trigger a Discord alert to the admins
- Logs rotate at 5 MB so they never fill the disk

There is also a **dry run mode**: flip one setting and the scraper does everything
except send the messages, printing what it *would* have sent. Perfect for testing
against real data without messaging anyone.

---

## Notes

This bot only reads public listing pages and Marktplaats' own public search API,
the same data any visitor sees in a browser. Please use it responsibly and keep
the request delays sensible.

Search results are in Dutch, since Marktplaats is a Dutch marketplace.

---

## Credits

**Built by Muhammad Ali**

- GitHub: [@muhammad-a-dev](https://github.com/muhammad-a-dev)

If this project helped you, a ⭐ on the repo is always appreciated.

Released under the [MIT License](LICENSE) — free to use, change and learn from.

---

<sub>**Keywords:** marktplaats bot · marktplaats alert · marktplaats scraper · marktplaats notifier ·
discord alert bot · discord bot python · marktplaats deal finder · tweedehands alert ·
second hand marketplace monitor · price monitoring bot · listing notifier ·
python web scraper · discord.py bot · marktplaats api · reselling tool · deal sniping bot</sub>
