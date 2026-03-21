#!/usr/bin/env python3
#  ██████╗ ██████╗ ██╗  ██╗██╗   ██╗      ██████╗ ████████╗███╗   ██╗      ██╗  ██╗ █████╗ ████████╗
# ██╔════╝██╔════╝ ██║  ██║██║   ██║      ██╔══██╗╚══██╔══╝████╗  ██║      ██║  ██║██╔══██╗╚══██╔══╝
# ██║     ███████╗ ███████║██║   ██║█████╗██████╔╝   ██║   ██╔██╗ ██║█████╗███████║███████║   ██║
# ██║     ██╔═══██╗╚════██║██║   ██║╚════╝██╔══██╗   ██║   ██║╚██╗██║╚════╝██╔══██║██╔══██║   ██║
# ╚██████╗╚██████╔╝     ██║╚██████╔╝      ██████╔╝   ██║   ██║ ╚████║      ██║  ██║██║  ██║   ██║
#  ╚═════╝ ╚═════╝      ╚═╝ ╚═════╝       ╚═════╝    ╚═╝   ╚═╝  ╚═══╝      ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝
#
# ----------------------------------------------------------------------------------------------------------------------
# C64U-btn-HAT: A simple button HAT for the Raspberry Pi Zero W 2, using PiicoDev/PiicoDev Buttons
# (best used with the C64-Bridge-Project, see https://github.com/brett-olsen/C64-Bridge-Project)
#
# https://github.com/brett-olsen/C64U-btn-HAT
# Version 0.4
# Created by Brett Olsen - 2026
# ----------------------------------------------------------------------------------------------------------------------
import time
import json
import os
import re
import socket
import ftplib
import logging
import urllib.request
import urllib.error
from urllib.parse import urlencode, quote
import threading
import subprocess
from dataclasses import dataclass
from typing import Callable, Optional, List, Tuple, Dict, Union
from PiicoDev_Switch import PiicoDev_Switch
from PiicoDev_Unified import sleep_ms

# ======================================================================================================================
# C64U-btn-HAT CONFIG (edit these)
# ======================================================================================================================

# Set the IP to the address of your C64 Ultimate
IP = "192.168.1.64"

# Optional: if you've set a Network Password on the Ultimate, set it here.
C64U_PASSWORD = ""  # e.g. "mysecret" (leave blank if not used)

# Optional: C64 Keyboard Daemon (USB HID Bridge) settings.
# These can be overridden at runtime via environment variables without editing this file.
C64KBD_PI_HOST  = os.getenv("C64KBD_PI_HOST", "192.168.1.99")
C64KBD_PI_PORT  = int(os.getenv("C64KBD_PI_PORT", "9999"))
C64KBD_TOKEN    = os.getenv("C64KBD_TOKEN", "ILoveMyCommodoreC64")

# Button3 can run an optional local shell command (runs async in a background thread).
# This is independent of the REST API action — both fire when the button is pressed.
# Examples:
#   BUTTON3COMMAND = ""                                         # disabled (safe default for new installs)
#   BUTTON3COMMAND = "aplay /opt/sounds/beep.wav"               # play a sound
#   BUTTON3COMMAND = "logger 'Button3 pressed'"                 # write to syslog
#   BUTTON3COMMAND = "/usr/bin/sudo /usr/sbin/shutdown -h now"  # shutdown the Pi
BUTTON3COMMAND = ""  # set to "" to disable; see examples above

# Flash the onboard POWER LED on the pressed button
FLASH_LED_ON_PRESS = True
LED_ON_MS = 200
LED_OFF_MS = 400

# Daemon polling settings
POLL_MS = 150           # how often to poll buttons
HTTP_TIMEOUT_S = 3.0    # network timeout
RETRIES = 2             # retry count per press if request fails
RETRY_DELAY_S = 0.2     # retry delay
COMMAND_TIMEOUT_S = 60  # max seconds for local command threads


# ---- SSD1306 Display settings -------------------------------------------------------------------
# Requires PiicoDev_SSD1306.py and font-pet-me-128.dat in the same directory as this script.
# Set DISPLAY_ENABLED = False to run without a display attached (all display calls become no-ops).
DISPLAY_ENABLED         = False # True = use SSD1306 OLED display | False = disable
DISPLAY_RESULT_S        = 3     # seconds to show button result before returning to idle screen
DISPLAY_IDLE_REFRESH_S  = 10    # seconds between idle screen clock refreshes (uptime counter)

# ---- Screensaver settings -----------------------------------------------------------------------
# SCREENSAVER_MODE options:
#   "off"     — screensaver disabled, idle screen stays on permanently
#   "blank"   — screen goes dark (best for OLED longevity)
#   "pacman"  — Pac-Man chomps across the screen eating pellets
#   "c64logo" — Commodore C= logo bounces around the screen (DVD-style)
SCREENSAVER_MODE    = "c64logo"  # "off" | "blank" | "pacman" | "c64logo"
SCREENSAVER_DELAY_S = 600       # seconds idle before screensaver activates (default: 10 minutes)
SCREENSAVER_FPS     = 8         # animation frames per second (capped by POLL_MS in practice)
# ======================================================================================================================


# ======================================================================================================================
# BUTTON ACTION LIBRARY
# ======================================================================================================================
#
# these functions can be easily extended or enhanced, you can see the API documentation at:
# https://1541u-documentation.readthedocs.io/en/latest/api/api_calls.html
# ======================================================================================================================

@dataclass(frozen=True)
class ActionRequest:
    """
    For actions that need something other than a simple PUT /v1/...
    Example: POST /v1/configs with a JSON body.
    """
    method: str
    path: str
    json_body: Optional[dict] = None
    debug_name: str = ""  # optional for nicer logs


@dataclass(frozen=True)
class KeystrokeRequest:
    """
    For actions that send text to the C64 Keyboard Daemon (USB HID bridge) over TCP.
    """
    host: str
    port: int
    token: str
    text: str
    debug_name: str = ""


ActionSpec = Union[str, ActionRequest, KeystrokeRequest]
ActionFn = Callable[[], ActionSpec]


class LastDiskInfo(Exception):
    """
    Raised by next_disk() when the currently mounted disk is already the last
    in the series.  Treated as informational (not an error) by the main loop —
    shown with the disk icon and a friendly message rather than the error screen.

    Attributes
    ----------
    current : int   current disk position (1-based)
    total   : int   total number of disks in the series
    """
    def __init__(self, current: int, total: int) -> None:
        self.current = current
        self.total   = total
        super().__init__(f"Last disk ({current}/{total})")

# ---- Basic system functions ------------------------------------------------------------------------
def menu_button() -> str:
    """Enter/exit Ultimate menu (same as pressing the Menu button)."""
    return "/v1/machine:menu_button"


def machine_reset() -> str:
    """Reset the machine."""
    return "/v1/machine:reset"


def machine_poweroff() -> str:
    """Power off (U64-only; response may not return)."""
    return "/v1/machine:poweroff"


def machine_reboot() -> str:
    """Reboot the machine (re-init cartridge config + reset)."""
    return "/v1/machine:reboot"


def machine_pause() -> str:
    """Pause the machine (DMA line low)."""
    return "/v1/machine:pause"


def machine_resume() -> str:
    """Resume the machine."""
    return "/v1/machine:resume"


# ---- Drive helpers -------------------------------------------------------------------------------
def drive_reset(drive: str = "a") -> ActionFn:
    drive = str(drive).lower()

    def _action() -> str:
        return f"/v1/drives/{drive}:reset"

    _action.__name__ = f"drive_{drive}_reset"
    return _action


def drive_remove(drive: str = "a") -> ActionFn:
    drive = str(drive).lower()

    def _action() -> str:
        return f"/v1/drives/{drive}:remove"

    _action.__name__ = f"drive_{drive}_remove"
    return _action


def drive_on(drive: str = "a") -> ActionFn:
    drive = str(drive).lower()

    def _action() -> str:
        return f"/v1/drives/{drive}:on"

    _action.__name__ = f"drive_{drive}_on"
    return _action


def drive_off(drive: str = "a") -> ActionFn:
    drive = str(drive).lower()

    def _action() -> str:
        return f"/v1/drives/{drive}:off"

    _action.__name__ = f"drive_{drive}_off"
    return _action


# ---- Runners / Mount helpers --------------------------------------------------------------------
# SID play:
#   PUT /v1/runners:sidplay?file=<path>&songnr=<n>
# Run cartridge:
#   PUT /v1/runners:run_crt?file=<path>
# Mount disk:
#   PUT /v1/drives/<drive>:mount?image=<path>[&type=d64|g64|d71|g71|d81][&mode=readwrite|readonly|unlinked]
#
# Note: In the official docs, <drive> is typically "a" or "b" (and sometimes "softiec").
# Some tools refer to bus IDs like 8/9; if your firmware supports that, you can pass "8" or "9".
# --------------------------------------------------------------------------------------------------


def sid_play(file: str, song_nr: int = 0) -> ActionFn:
    """
    Return an action that plays a SID file already present on the Ultimate filesystem.

    file:    path to SID on Ultimate filesystem (e.g. "/Music/Tunes/song.sid")
    song_nr: optional song number (>0)
    """
    def _action() -> str:
        params = {"file": file}
        if int(song_nr) > 0:
            params["songnr"] = str(int(song_nr))
        return "/v1/runners:sidplay?" + urlencode(params, safe="/", quote_via=quote)

    _action.__name__ = "sid_play"
    return _action


def run_cart(file: str) -> ActionFn:
    """
    Return an action that starts a .CRT cartridge file already present on the Ultimate filesystem.
    """
    def _action() -> str:
        params = {"file": file}
        return "/v1/runners:run_crt?" + urlencode(params, safe="/", quote_via=quote)

    _action.__name__ = "run_cart"
    return _action


def mount_disk(drive: str, image: str, image_type: str = "", mode: str = "") -> ActionFn:
    """
    Return an action that mounts an existing disk image onto a drive.

    drive:      typically "a" or "b" (and sometimes "softiec")
    image:      path to image file on Ultimate filesystem
    image_type: optional: d64, g64, d71, g71, d81
    mode:       optional: readwrite, readonly, unlinked
    """
    d = str(drive).lower()

    def _action() -> str:
        params = {"image": image}
        if str(image_type).strip():
            params["type"] = str(image_type).strip()
        if str(mode).strip():
            params["mode"] = str(mode).strip()
        return f"/v1/drives/{d}:mount?" + urlencode(params, safe="/", quote_via=quote)

    _action.__name__ = f"mount_disk_{d}"
    return _action


# ---- Next disk (auto-advance through a multi-disk series) ----------------------------------------
#
# Regex for detecting disk numbering in C64 image filenames.
# Handles all common naming conventions found in the wild:
#
#   Numeric IDs              Letter IDs
#   ─────────────────────    ──────────────────────────────
#   "Game - Disk 1.d64"      "1337 - Fairlight - Disk A.d64"
#   "Game - Disk 2.d64"      "Game (Disk B).d64"
#   "Game (Disk 1).d64"      "Another Game (Disk-A).d64"
#   "Game (Disk-1).d64"      "Baron - ... - Disk B.D64"
#
# Group 1: base name (everything before the disk indicator, trailing spaces/dashes stripped)
# Group 2: disk identifier  — single letter (A-Z) OR one-or-more digits (1, 2, 10 …)
#
_DISK_RE = re.compile(
    r'^(.*?)'               # Group 1: base name (non-greedy)
    r'[\s\-\(]+'            # separator before "Disk" keyword (1+ required)
    r'[Dd]isk'              # literal "Disk" keyword (case-insensitive)
    r'[\s\-]*'              # gap between "Disk" and ID — OPTIONAL (handles "Disk1" AND "Disk 1")
    r'([A-Za-z]|\d+)'       # Group 2: single letter OR one-or-more digits
    r'\s*\)?\s*$',          # optional closing paren + trailing whitespace
    re.IGNORECASE,
)

# Image extensions that count as disk images
_DISK_EXTENSIONS = frozenset({'.d64', '.g64', '.d71', '.g71', '.d81'})


def _parse_disk_id(filename: str) -> Optional[Tuple[str, str]]:
    """
    Parse a disk image filename and return (normalised_base, disk_id) or None.

    The returned disk_id is always uppercased.  The base has trailing dashes /
    spaces stripped so it can be compared across files in the same series.

    Examples
    --------
    '1337 - Fairlight - Disk A.d64'              -> ('1337 - Fairlight',                   'A')
    'Baron - The Real Estate Simulation - Disk 1.D64' -> ('Baron - The Real Estate Simulation', '1')
    'Game Name (Disk 1).d64'                     -> ('Game Name',                          '1')
    'Another Game (Disk-A).d64'                  -> ('Another Game',                       'A')
    """
    name = os.path.splitext(filename)[0]
    m = _DISK_RE.match(name)
    if not m:
        return None
    base    = m.group(1).rstrip(' -(').strip()
    disk_id = m.group(2).upper()
    return base, disk_id


def next_disk(drive: str = "a") -> ActionFn:
    """
    Return an action that automatically finds and mounts the next disk in
    the currently mounted image's series.

    Discovery process
    -----------------
    1. GET /v1/drives  — finds which image + path is mounted on *drive*.
    2. FTP NLST        — lists all files in that directory from the Ultimate.
    3. Filter + sort   — keep files that share the same base name and disk pattern;
                         sort by numeric value (1,2,3…) or alpha (A,B,C…).
    4. Advance         — mount the image one step ahead of the current one.

    The action raises ValueError (shown on the OLED via show_error) when:
      - No disk is currently mounted.
      - The filename has no recognisable "Disk N / Disk A" pattern.
      - No sibling disks are found in the directory.
      - The currently mounted disk is already the last in the series.
    """
    d = str(drive).lower()

    def _action() -> str:
        # ── Step 1: query the Ultimate for the currently mounted image ──────────
        drives_url = f"http://{IP}/v1/drives"
        logging.info("next_disk: GET %s", drives_url)
        headers = _build_headers()
        req     = urllib.request.Request(drives_url, method="GET")
        for k, v in headers.items():
            req.add_header(k, v)

        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
                raw_body = resp.read()
                drive_data = json.loads(raw_body)
                logging.info("next_disk: /v1/drives response: %s", raw_body.decode("utf-8", errors="replace"))
        except Exception as exc:
            logging.error("next_disk: failed to reach /v1/drives: %s", exc)
            raise RuntimeError(f"C64U unreachable: {exc}") from exc

        # Response: {"drives": [{"a": {...}}, ...]}
        drive_info: Optional[dict] = None
        for entry in drive_data.get("drives", []):
            if d in entry:
                drive_info = entry[d]
                break

        if drive_info is None:
            logging.error("next_disk: drive %s not in API response", d.upper())
            raise ValueError(f"Drive {d.upper()} not found")
        if not drive_info.get("enabled", False):
            logging.error("next_disk: drive %s is disabled", d.upper())
            raise ValueError(f"Drive {d.upper()} disabled")

        image_file = (drive_info.get("image_file") or "").strip()
        image_path = (drive_info.get("image_path") or "").strip()

        if not image_file:
            logging.error("next_disk: drive %s has no disk mounted (image_file=%r image_path=%r)",
                          d.upper(), image_file, image_path)
            raise ValueError("No disk mounted")

        # The Ultimate returns the drive state differently depending on how the
        # disk was mounted:
        #
        #   Mounted via Ultimate UI / original state:
        #     image_file = "Neon - Triad - Disk1.d64"          ← bare filename
        #     image_path = "/USB1/DEMOSCENE/Neon - Triad/"     ← directory
        #
        #   Mounted via our REST API PUT (programmatic):
        #     image_file = "/USB1/DEMOSCENE/Neon - Triad/Neon - Triad - Disk2.d64"  ← full path
        #     image_path = ""                                   ← empty!
        #
        # Normalise both cases into (image_dir, image_basename) before proceeding.
        if not image_path and image_file.startswith('/'):
            # Full path in image_file — split it ourselves
            image_path = os.path.dirname(image_file)   # "/USB1/DEMOSCENE/Neon - Triad"
            image_file = os.path.basename(image_file)  # "Neon - Triad - Disk2.d64"
            logging.info("next_disk: normalised full-path response → file=%r  path=%r",
                         image_file, image_path)
        elif not image_path:
            logging.error("next_disk: drive %s image_path is empty and image_file is not a full path "
                          "(image_file=%r)", d.upper(), image_file)
            raise ValueError("No disk mounted")

        logging.info("next_disk: drive=%s  file=%r  path=%r", d.upper(), image_file, image_path)

        # ── Step 2: parse the disk ID out of the current filename ────────────────
        parsed = _parse_disk_id(image_file)
        if parsed is None:
            logging.error("next_disk: cannot parse a disk number from filename %r", image_file)
            raise ValueError(f"No disk# in: {image_file[:14]}")

        current_base, current_id = parsed
        logging.info("next_disk: parsed base=%r  id=%r", current_base, current_id)

        # ── Step 3: FTP-list the directory to enumerate the full series ──────────
        #
        # FTP directory listing strategy:
        #
        # Primary:  CWD then bare NLST (no path argument).
        #   - Avoids the FTP space-delimiter problem (NLST with a path containing
        #     spaces would be misparsed on the control channel).
        #   - Works for most filenames.
        #
        # Fallback: CWD then bare LIST (full metadata lines).
        #   - The Ultimate's FTP server occasionally truncates NLST responses for
        #     very long filenames or paths containing '+' characters, returning the
        #     directory name instead of the full filename.
        #   - LIST is never truncated because the filename is the last field on
        #     each line and the FTP library reads it verbatim.
        #   - We detect this silently: if NLST returns no disk-image extensions,
        #     we retry with LIST and log a warning so it's visible in journalctl.
        #
        # LIST line format (RFC 3659 / Unix ls -l):
        #   perms links owner group size month day time-or-year filename
        #   e.g.: -rw-r--r--  1 root root 174080 Jan  1  2000 Game - Disk 1.d64
        #   The filename starts after the 8th whitespace-delimited token.

        ftp_dir = image_path.rstrip('/')
        logging.info("next_disk: FTP connecting to %s:21", IP)
        ftp_timeout = max(8, int(HTTP_TIMEOUT_S * 2))
        ftp = ftplib.FTP()
        try:
            ftp.connect(IP, 21, timeout=ftp_timeout)
            ftp.login()
            logging.info("next_disk: FTP login OK, cwd → %r", ftp_dir)

            try:
                ftp.cwd(ftp_dir)
            except ftplib.all_errors as cwd_err:
                logging.error("next_disk: FTP CWD %r failed: %s", ftp_dir, cwd_err)
                raise RuntimeError(f"FTP CWD failed: {cwd_err}") from cwd_err

            # ── Primary: NLST ──────────────────────────────────────────────────
            logging.info("next_disk: FTP NLST")
            try:
                nlst_raw: List[str] = ftp.nlst()
            except ftplib.all_errors as nlst_err:
                logging.error("next_disk: FTP NLST failed: %s", nlst_err)
                nlst_raw = []

            # Normalise: strip paths, keep bare filenames
            nlst_files = [os.path.basename(f.strip()) for f in nlst_raw if f.strip()]
            has_disk_images = any(
                os.path.splitext(fn)[1].lower() in _DISK_EXTENSIONS
                for fn in nlst_files
            )

            if has_disk_images:
                all_files = nlst_files
                logging.info("next_disk: NLST → %d file(s): %s", len(all_files), all_files)
            else:
                # ── Fallback: LIST ─────────────────────────────────────────────
                # NLST returned no disk images — likely truncated by the server
                # (observed with long filenames containing '+' on the Ultimate).
                # Parse filenames from the full LIST output instead.
                logging.warning(
                    "next_disk: NLST returned no disk images (%s) — falling back to LIST",
                    nlst_files,
                )
                list_lines: List[str] = []
                try:
                    ftp.retrlines("LIST", list_lines.append)
                except ftplib.all_errors as list_err:
                    logging.error("next_disk: FTP LIST failed: %s", list_err)
                    raise RuntimeError(f"FTP LIST failed: {list_err}") from list_err

                # Parse filename = everything after the 8 fixed metadata tokens
                # (perms links owner group size month day time-or-year FILENAME)
                import re as _re
                _LIST_RE = _re.compile(
                    r'^\S+\s+'    # permissions
                    r'\d+\s+'     # links
                    r'\S+\s+'     # owner
                    r'\S+\s+'     # group
                    r'\d+\s+'     # size
                    r'\w+\s+'     # month
                    r'\d+\s+'     # day
                    r'\S+\s+'     # time or year
                    r'(.+)$'      # FILENAME (everything after — preserves + and spaces)
                )
                all_files = []
                for line in list_lines:
                    m = _LIST_RE.match(line.rstrip())
                    if m:
                        fn = m.group(1).strip()
                        all_files.append(fn)
                        logging.info("next_disk: LIST parsed: %r", fn)
                    else:
                        logging.info("next_disk: LIST skipped unparseable line: %r", line[:80])

                logging.info("next_disk: LIST → %d file(s): %s", len(all_files), all_files)

            ftp.quit()
        except RuntimeError:
            raise
        except Exception as exc:
            logging.error("next_disk: FTP error: %s", exc)
            raise RuntimeError(f"FTP error: {exc}") from exc
        finally:
            try:
                ftp.close()
            except Exception:
                pass

        if not all_files:
            logging.error("next_disk: FTP listing returned no files for %r", ftp_dir)
            raise RuntimeError(f"FTP empty listing for: {ftp_dir[-20:]}")

        # ── Step 4: collect sibling disk images that share the same base name ────
        series: List[Tuple[str, str]] = []    # [(disk_id, filename), …]
        for fn in all_files:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in _DISK_EXTENSIONS:
                logging.info("next_disk:   skip (not a disk image): %r", fn)
                continue
            fp = _parse_disk_id(fn)
            if fp is None:
                logging.info("next_disk:   skip (no disk# pattern): %r", fn)
                continue
            fn_base, fn_id = fp
            if fn_base.lower() == current_base.lower():
                series.append((fn_id, fn))
                logging.info("next_disk:   match  id=%-3s  %r", fn_id, fn)
            else:
                logging.info("next_disk:   skip (different base %r): %r", fn_base, fn)

        if not series:
            # ── Blind-increment fallback ──────────────────────────────────────
            # FTP listing could not find sibling disk images — the Ultimate's
            # FTP server truncates filenames beyond a certain length or when the
            # path contains special characters like '+'.  Since we already have
            # the current filename parsed into (base, id), we reconstruct the
            # next filename by incrementing the disk ID directly and attempt the
            # PUT.  A 404 response from the server means the file doesn't exist
            # (we're already on the last disk); main() turns that into a friendly
            # "LAST DISK" message rather than an error screen. TLDR guess it =D

            logging.warning(
                "next_disk: FTP series empty — using blind-increment fallback "
                "(FTP server likely truncated filenames; base=%r id=%r)",
                current_base, current_id,
            )

            # Compute the next ID (numeric: "1"→"2"; alpha: "A"→"B")
            if current_id.isdigit():
                next_id_str = str(int(current_id) + 1)
            elif len(current_id) == 1 and current_id.isalpha():
                next_char = chr(ord(current_id.upper()) + 1)
                if next_char > 'Z':
                    logging.info("next_disk: already at last alpha disk (%s)", current_id)
                    raise LastDiskInfo(current=1, total=1)
                next_id_str = next_char
            else:
                logging.error("next_disk: cannot increment disk ID %r", current_id)
                raise ValueError(f"Cannot increment disk ID: {current_id!r}")

            # Replace the disk ID in the original filename, preserving all
            # surrounding formatting (spaces, dashes, parentheses, extension).
            blind_next_fn = re.sub(
                r'([\s\-\(]+[Dd]isk[\s\-]*)' + re.escape(current_id) + r'(\s*\)?\s*\.)',
                lambda m: m.group(1) + next_id_str + m.group(2),
                image_file,
                count=1,
            )
            if blind_next_fn == image_file:
                # Pattern didn't match — can't reconstruct safely
                logging.error("next_disk: blind-increment could not rewrite %r", image_file)
                raise ValueError(f"No series found: {current_base[:12]}")

            next_full_path = image_path.rstrip('/') + '/' + blind_next_fn
            params   = {"image": next_full_path}
            put_path = f"/v1/drives/{d}:mount?" + urlencode(params, safe="/", quote_via=quote)
            put_url  = f"http://{IP}{put_path}"
            logging.info("next_disk: blind-increment → %r", blind_next_fn)
            logging.info("next_disk: PUT URL (blind) → %s", put_url)
            return put_path

        # Sort: integer order for numeric IDs, alphabetical for letter IDs
        all_numeric = all(sid.isdigit() for sid, _ in series)
        series.sort(key=(lambda x: int(x[0])) if all_numeric else (lambda x: x[0].upper()))
        logging.info("next_disk: series order: %s", [sid for sid, _ in series])

        # ── Step 5: find current position and advance by one ─────────────────────
        ids_upper = [sid.upper() for sid, _ in series]
        try:
            cur_idx = ids_upper.index(current_id.upper())
        except ValueError:
            logging.error("next_disk: current id %r not found in series %s", current_id, ids_upper)
            raise ValueError(f"Disk {current_id} not in series")

        total = len(series)
        logging.info("next_disk: current position %d/%d (id=%s)", cur_idx + 1, total, current_id)

        if cur_idx >= total - 1:
            # Raise LastDiskInfo (informational, not an error) so main() can
            # show a friendly "last disk" message instead of the error screen.
            logging.info("next_disk: already on last disk (%d/%d)", total, total)
            raise LastDiskInfo(current=total, total=total)

        next_id, next_fn = series[cur_idx + 1]
        # Reconstruct the full path — use the original image_path (preserves trailing slash
        # or lack thereof exactly as the Ultimate expects it) joined with the filename.
        next_full_path = image_path.rstrip('/') + '/' + next_fn

        # Build the PUT query string — urlencode encodes spaces as %20 via quote()
        params   = {"image": next_full_path}
        put_path = f"/v1/drives/{d}:mount?" + urlencode(params, safe="/", quote_via=quote)
        put_url  = f"http://{IP}{put_path}"

        logging.info("next_disk: mounting %d/%d  file=%r", cur_idx + 2, total, next_fn)
        logging.info("next_disk: PUT URL → %s", put_url)

        return put_path

    _action.__name__ = "next_disk"
    return _action


# ---- Keystrokes (C64 Keyboard Daemon) ----------------------------------------------------------
# Example (single-line):
#   BUTTON4ACTION: Optional[ActionFn] = send_keystrokes("run\n")
#
# Example (multi-line program; each line ends with Enter):
#   BUTTON4ACTION: Optional[ActionFn] = send_keystrokes(
#       '10 print "i love my commodore";\n'
#       '20 goto 10\n'
#       'run\n'
#   )
#

def send_keystrokes(
    text: str,
    *,
    host: Optional[str] = None,
    port: Optional[int] = None,
    token: Optional[str] = None,
    ensure_trailing_newline: bool = True,
) -> ActionFn:
    """
    Return an action that sends keystrokes to the C64 Keyboard Daemon over TCP.
    """
    def _action() -> KeystrokeRequest:
        t = text
        if ensure_trailing_newline and not t.endswith("\n"):
            t = t + "\n"

        return KeystrokeRequest(
            host=(host or C64KBD_PI_HOST),
            port=int(port or C64KBD_PI_PORT),
            token=(token or C64KBD_TOKEN),
            text=t,
            debug_name="send_keystrokes",
        )

    _action.__name__ = "send_keystrokes"
    return _action


# ---- Turbo toggle (U64 Specific Settings) --------------------------------------------------------
# Uses your provided curl patterns:
# Turbo ON:
#   POST /v1/configs  {"U64 Specific Settings":{"Turbo Control":"Manual","CPU Speed":"64"}}
# Turbo OFF:
#   POST /v1/configs  {"U64 Specific Settings":{"Turbo Control":"Off","CPU Speed":" 1"}}
_turbo_lock = threading.Lock()
_turbo_enabled = False  # first press => ON, second press => OFF (resets to OFF on daemon restart)


def turbo_on_off() -> ActionRequest:
    """
    Toggle U64 Turbo settings:
      - first press: turbo ON  (Turbo Control=Manual, CPU Speed=64)
      - second press: turbo OFF (Turbo Control=Off, CPU Speed=" 1")
    """
    global _turbo_enabled
    with _turbo_lock:
        _turbo_enabled = not _turbo_enabled
        enabled = _turbo_enabled

    if enabled:
        payload = {"U64 Specific Settings": {"Turbo Control": "Manual", "CPU Speed": "64"}}
        return ActionRequest(method="POST", path="/v1/configs", json_body=payload, debug_name="turbo_on")
    else:
        payload = {"U64 Specific Settings": {"Turbo Control": "Off", "CPU Speed": " 1"}}
        return ActionRequest(method="POST", path="/v1/configs", json_body=payload, debug_name="turbo_off")


# ---- Lights toggle (LED Strip Settings + Keyboard Lighting) --------------------------------------
# ON uses your current "SID Music" configs; OFF sets LedStrip Mode="Off" for both categories.
# TODO: The ON payload below is hardcoded to specific LED settings (SID Music mode, Amber strip,
#       Royal Blue keyboard). Users should customise these values to match their own Ultimate
#       LED configuration. Consider reading the current config first via GET /v1/configs and
#       restoring it on toggle-off, rather than hardcoding an ON state.

_lights_lock = threading.Lock()
_lights_enabled = False  # first press => ON, second press => OFF (resets on daemon restart)


def lights_on_off() -> ActionRequest:
    """
    Toggle U64 lighting:
      - ON: restore the 'SID Music' configs you posted for BOTH:
            "LED Strip Settings" and "Keyboard Lighting"
      - OFF: set "LedStrip Mode" -> "Off" for BOTH categories
    """
    global _lights_enabled
    with _lights_lock:
        _lights_enabled = not _lights_enabled
        enabled = _lights_enabled

    if enabled:
        payload = {
            "LED Strip Settings": {
                "LedStrip Mode": "SID Music",
                "LedStrip Pattern": "SingleColor",
                "LedStrip SID Select": "UltiSID1-A",
                "Strip Intensity": 25,
                "Fixed Color": "Amber",
                "Color tint": "Pure",
            },
            "Keyboard Lighting": {
                "LedStrip Mode": "SID Music",
                "LedStrip Pattern": "Single Color",
                "LedStrip SID Select": "UltiSID1-A",
                "Strip Intensity": 6,
                "Fixed Color": "Royal Blue",
                "Color tint": "Pure",
            },
        }
        return ActionRequest(method="POST", path="/v1/configs", json_body=payload, debug_name="lights_on")
    else:
        payload = {
            "LED Strip Settings": {"LedStrip Mode": "Off"},
            "Keyboard Lighting": {"LedStrip Mode": "Off"},
        }
        return ActionRequest(method="POST", path="/v1/configs", json_body=payload, debug_name="lights_off")


_speaker_lock    = threading.Lock()
_speaker_enabled = True   # first press => OFF, second press => ON (assumes speaker starts on)


def speaker_on_off() -> ActionRequest:
    """
    Toggle the U64 speaker output:
      - ON:  set "Speaker Mixer" → "Speaker Enable" → "Enabled"
      - OFF: set "Speaker Mixer" → "Speaker Enable" → "Disabled"

    State resets to ON (enabled=True) on daemon restart — matching the
    U64's default power-on state so the first button press turns it off.
    """
    global _speaker_enabled
    with _speaker_lock:
        _speaker_enabled = not _speaker_enabled
        enabled = _speaker_enabled

    state = "Enabled" if enabled else "Disabled"
    payload = {"Speaker Mixer": {"Speaker Enable": state}}
    debug   = "speaker_on" if enabled else "speaker_off"
    return ActionRequest(method="POST", path="/v1/configs", json_body=payload, debug_name=debug)


def party_time(disk: str) -> ActionFn:
    """
    Factory: returns a one-button show-starter action for any disk image.

    disk: full path to the disk image on the Ultimate filesystem, exactly
          as shown in the C64 Ultimate file browser
          e.g. "/USB1/DEMOSCENE/1337 - Fairlight/1337 - Fairlight - Disk A.d64"

    The returned action runs these steps in a background thread so the OLED
    shows feedback immediately and the main loop is never blocked:

      1. Lights ON      — POST /v1/configs (LED Strip + Keyboard Lighting)
      2. Speaker ON     — POST /v1/configs (Speaker Mixer, all channels at party levels)
      3. Mount disk     — PUT /v1/drives/a:mount  (the disk path you supplied)
      4. Wait 2 s       — let the drive spin up and the C64 see the disk
      5. Keystroke      — LOAD "*",8,1 + Enter  (via C64 Keyboard Daemon)
      6. Wait 5 s       — let the load complete
      7. Keystroke      — RUN + Enter

    Requires the C64 Keyboard Daemon (see C64KBD_PI_HOST / C64KBD_PI_PORT).
    Each step is logged so failures are visible in journalctl.

    Usage:
      BUTTON3ACTION = party_time("/USB1/DEMOSCENE/1337 - Fairlight/1337 - Fairlight - Disk A.d64")
      BUTTON4ACTION = party_time("/USB1/GAMES/Turrican II - Disk 1.d64")
    """

    def _sequence() -> None:
        """Runs the full sequence in a background thread."""
        global _lights_enabled, _speaker_enabled

        headers = _build_headers()

        def post_config(payload: dict, label: str) -> bool:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            h    = dict(headers)
            h["Content-Type"] = "application/json"
            url  = f"http://{IP}/v1/configs"
            code = request_with_retries(url, method="POST", headers=h, body=body)
            ok   = 200 <= code < 300
            logging.info("party_time: %s → %s", label, code)
            return ok

        def put_path(path: str, label: str) -> bool:
            url  = f"http://{IP}{path}"
            code = request_with_retries(url, method="PUT", headers=dict(headers))
            ok   = 200 <= code < 300
            logging.info("party_time: %s → %s", label, code)
            return ok

        def send_keys(text: str, label: str) -> bool:
            req  = KeystrokeRequest(
                host=C64KBD_PI_HOST, port=C64KBD_PI_PORT,
                token=C64KBD_TOKEN, text=text, debug_name=label,
            )
            code = keystrokes_with_retries(req)
            ok   = code == 200
            logging.info("party_time: %s → %s", label, code)
            return ok

        logging.info("party_time: sequence starting (disk=%r)", disk)

        # ── Step 1: Lights ON ─────────────────────────────────────────────────
        lights_payload = {
            "LED Strip Settings": {
                "LedStrip Mode": "SID Music",
                "LedStrip Pattern": "SingleColor",
                "LedStrip SID Select": "UltiSID1-A",
                "Strip Intensity": 25,
                "Fixed Color": "Amber",
                "Color tint": "Pure",
            },
            "Keyboard Lighting": {
                "LedStrip Mode": "SID Music",
                "LedStrip Pattern": "Single Color",
                "LedStrip SID Select": "UltiSID1-A",
                "Strip Intensity": 6,
                "Fixed Color": "Royal Blue",
                "Color tint": "Pure",
            },
        }
        if post_config(lights_payload, "lights ON"):
            _lights_enabled = True   # keep toggle state in sync

        # ── Step 2: Speaker ON (party volume levels) ──────────────────────────
        speaker_payload = {
            "Speaker Mixer": {
                "Speaker Enable": "Enabled",
                "Vol UltiSid 1":  "-10 dB",
                "Vol UltiSid 2":  "-10 dB",
                "Vol Socket 1":   "-10 dB",
                "Vol Socket 2":   "-10 dB",
                "Vol Sampler L":  "-10 dB",
                "Vol Sampler R":  "-10 dB",
                "Vol Drive 1":    "-15 dB",
                "Vol Drive 2":    "-15 dB",
                "Vol Tape Read":  "-36 dB",
                "Vol Tape Write": "-36 dB",
            }
        }
        if post_config(speaker_payload, "speaker ON"):
            _speaker_enabled = True  # keep toggle state in sync

        # ── Step 3: Mount disk (path supplied at config time) ─────────────────
        # urlencode encodes spaces as %20 while preserving slashes.
        mount_qs = urlencode({"image": disk}, quote_via=quote)
        put_path(f"/v1/drives/a:mount?{mount_qs}", f"mount {disk!r}")

        # ── Step 4: Wait for drive to spin up ─────────────────────────────────
        logging.info("party_time: waiting 2 s for disk to spin up...")
        time.sleep(2)

        # ── Step 5: LOAD "*",8,1 + Enter ─────────────────────────────────────
        send_keys('load "*",8,1\n', 'load "*",8,1')

        # ── Step 6: Wait for LOAD to complete ─────────────────────────────────
        logging.info("party_time: waiting 5 s for LOAD to complete...")
        time.sleep(5)

        # ── Step 7: RUN + Enter ───────────────────────────────────────────────
        send_keys("run\n", "run")

        logging.info("party_time: sequence complete!")

    def _action() -> ActionRequest:
        t = threading.Thread(target=_sequence, daemon=True, name="party-time")
        t.start()
        # Return a sentinel immediately so the OLED shows feedback while the
        # thread runs in the background.
        return ActionRequest(
            method="POST",
            path="/v1/configs",
            json_body=None,
            debug_name="party_time",
        )

    _action.__name__ = "party_time"
    return _action


# ==================================================================================================================================
# BUTTON MAPPINGS
#
# Up to 6 buttons are supported (limited by the number of unique 4-bit DIP switch addresses).
# Set each BUTTON(n)_ID to the [sw3,sw2,sw1,sw0] DIP switch position on your physical hardware.
# Set BUTTON(n)ACTION to any action function from the library above, or None to disable that button.
#
# PiicoDev Buttons
#  [ON         RE]
#  [─────────────]
#  [─] [─] [─] [─]
#  [*] [ ] [ ] [ ]
#  [ ] [*] [*] [*]
#  [─] [-] [-] [-]
#  [1   2   3   4]
#  [─────────────]
# DIP Switches match the below button ID configuration
# ==================================================================================================================================

BUTTON1_ID = [1, 0, 0, 0]
BUTTON2_ID = [0, 1, 0, 0]
BUTTON3_ID = [0, 0, 1, 0]
BUTTON4_ID = [0, 0, 0, 1]
BUTTON5_ID = [0, 0, 1, 1]
BUTTON6_ID = [0, 1, 1, 1]

# Default 3 button setup
BUTTON1ACTION: Optional[ActionFn] = menu_button
BUTTON2ACTION: Optional[ActionFn] = speaker_on_off
BUTTON3ACTION: Optional[ActionFn] = lights_on_off

# Extended additional 3 button actions (for a total of 6)
BUTTON4ACTION: Optional[ActionFn] = None
BUTTON5ACTION: Optional[ActionFn] = None
BUTTON6ACTION: Optional[ActionFn] = None

# ======================================================================================================================
#   BUTTON ACTION EXAMPLES — copy/paste any line as a BUTTON(n)ACTION assignment above.
#
#   Full API reference: https://1541u-documentation.readthedocs.io/en/latest/api/api_calls.html
#
# ---- Disabling a button(s) -------------------------------------------------------------------
#   BUTTON4ACTION: Optional[ActionFn] = None
#   BUTTON5ACTION: Optional[ActionFn] = None
#   BUTTON6ACTION: Optional[ActionFn] = None
#
# ---- Basic machine control -------------------------------------------------------------------
#   BUTTON1ACTION: Optional[ActionFn] = menu_button          # open/close the Ultimate menu (same as the physical button)
#   BUTTON2ACTION: Optional[ActionFn] = machine_reset        # soft-reset the C64
#   BUTTON3ACTION: Optional[ActionFn] = machine_poweroff     # power off the C64 (U64 only — no HTTP response returned)
#   BUTTON4ACTION: Optional[ActionFn] = machine_reboot       # re-initialise cartridge config then reset
#   BUTTON5ACTION: Optional[ActionFn] = machine_pause        # pause the C64 (holds DMA line low)
#   BUTTON6ACTION: Optional[ActionFn] = machine_resume       # resume after a pause
#
# ---- Drive helpers ---------------------------------------------------------------------------
#   BUTTON4ACTION: Optional[ActionFn] = drive_reset("a")     # reset drive A (IEC bus ID 8 by default)
#   BUTTON4ACTION: Optional[ActionFn] = drive_reset("b")     # reset drive B (IEC bus ID 9)
#   BUTTON4ACTION: Optional[ActionFn] = drive_remove("a")    # eject / unmount whatever is in drive A
#   BUTTON4ACTION: Optional[ActionFn] = drive_on("a")        # power drive A on
#   BUTTON4ACTION: Optional[ActionFn] = drive_off("a")       # power drive A off
#
# ---- Mount a disk image ----------------------------------------------------------------------
#   Paths are as shown in the C64 Ultimate file browser (USB1 = first USB stick, etc.)
#
#   BUTTON5ACTION: Optional[ActionFn] = mount_disk("a", "/USB1/DEMOSCENE/Fairlight/Disk A.d64")
#   BUTTON5ACTION: Optional[ActionFn] = mount_disk("a", "/USB1/GAMES/Katakis.d64", mode="readonly")
#   BUTTON5ACTION: Optional[ActionFn] = mount_disk("b", "/USB1/GAMES/Turrican II - Disk 2.d64", image_type="d64")
#   # valid image_type values: d64, g64, d71, g71, d81
#   # valid mode values:       readwrite (default), readonly, unlinked
#
# ---- Auto-advance to the next disk in a series -----------------------------------------------
#   Queries /v1/drives for the currently mounted image, FTP-lists its directory,
#   then mounts the next disk in sequence (numeric 1→2 or alpha A→B).
#   Shows an OLED error if no disk is mounted. Shows a friendly "LAST DISK n/n"
#   message (not an error) if the current disk is already the last in the series.
#
#   BUTTON4ACTION: Optional[ActionFn] = next_disk()          # advance drive A to next disk in series
#   BUTTON4ACTION: Optional[ActionFn] = next_disk("b")       # advance drive B to next disk in series
#
# ---- Play a SID file -------------------------------------------------------------------------
#   BUTTON4ACTION: Optional[ActionFn] = sid_play("/USB1/MUSIC/SID/Game Music/1942.sid")
#   BUTTON4ACTION: Optional[ActionFn] = sid_play("/USB1/MUSIC/SID/HVSC/D/Drax/Acid.sid", song_nr=2)  # start at sub-tune 2
#
# ---- Run a cartridge image -------------------------------------------------------------------
#   BUTTON4ACTION: Optional[ActionFn] = run_cart("/USB1/UTIL/Action Replay v6.0 Professional (1989)(Datel).crt")
#   BUTTON4ACTION: Optional[ActionFn] = run_cart("/USB1/CARTS/EasyFlash 3.crt")
#
# ---- Toggle turbo mode (U64 only) ------------------------------------------------------------
#   BUTTON5ACTION: Optional[ActionFn] = turbo_on_off         # first press = ON (64x speed), second press = OFF
#
# ---- Toggle LED lighting (U64 only) ----------------------------------------------------------
#   BUTTON3ACTION: Optional[ActionFn] = lights_on_off        # toggles LED strip + keyboard lighting on/off
#   NOTE: Edit the ON payload inside lights_on_off() to match your preferred LED settings.
#
# ---- Toggle speaker output (U64 only) ---------------------------------------------------------
#   BUTTON2ACTION: Optional[ActionFn] = speaker_on_off       # first press = OFF, second press = ON (speaker enable/disable)
#
# ---- Party time! (requires C64 Keyboard Daemon) -----------------------------------------------
#   party_time is a factory function — call it with the disk image path you want to launch:
#
#   BUTTON3ACTION: Optional[ActionFn] = party_time("/USB1/DEMOSCENE/1337 - Fairlight/1337 - Fairlight - Disk A.d64")
#   BUTTON4ACTION: Optional[ActionFn] = party_time("/USB1/GAMES/Turrican II - Disk 1.d64")
#   BUTTON5ACTION: Optional[ActionFn] = party_time("/USB1/DEMOS/Edge of Disgrace - Disk 1.d64")
#
#   Sequence: lights ON → speaker ON (party levels) → mount disk → wait 2s →
#             LOAD "*",8,1 → wait 5s → RUN
#   NOTE: Runs all steps in a background thread; OLED shows result immediately.
#   NOTE: Edit the lights/speaker payloads inside party_time() to match your LED and volume preferences.
#
# ---- Send keystrokes via the C64 Keyboard Daemon (USB HID bridge) ----------------------------
#   Requires the keyboard daemon running on another Pi (see C64KBD_PI_HOST config above).
#
#   BUTTON5ACTION: Optional[ActionFn] = send_keystrokes("run\n")                       # type RUN and press Enter
#   BUTTON5ACTION: Optional[ActionFn] = send_keystrokes('load"*",8,1\nrun\n')         # load first program and run
#   BUTTON6ACTION: Optional[ActionFn] = send_keystrokes(                               # type a short BASIC program
#       '10 print "i love my commodore";\n'
#       '20 goto 10\n'
#       'run\n'
#   )
# ======================================================================================================================

# ======================================================================================================================
# INTERNALS
# ======================================================================================================================

# ---- SSD1306 Display ---------------------------------------------------------------------------------
#
# Screen layout (128×64px, 8px-tall font = 16 chars wide, 8 rows tall):
#
#   IDLE screen:
#   y= 0  [ C64U-btn-HAT  ]   title bar
#   y= 9  [───────────────]   separator
#   y=12  [B1 MENU  B2 RST]   button map row 1  (2 columns)
#   y=22  [B3 PWROFF B4   ]   button map row 2
#   y=32  [B5       B6    ]   button map row 3
#   y=44  [up 0d 00:00:00 ]   uptime
#   y=54  [C64:x.x.x.x    ]   footer (target IP)
#
#   PRESS / RESULT screen:
#   y= 0  [ C64U-btn-HAT  ]   title bar
#   y= 9  [───────────────]   separator
#   y=12  [* Btn1  PRESSED]   icon + button label
#   y=22  [  menu_button  ]   action name (truncated)
#   y=32  [  Sending...   ]   status / result
#   y=42  [  OK [200]     ]   result code
#   y=54  [C64:x.x.x.x    ]   footer
#
# Icons: 8×8 bitmaps drawn to the left of text using framebuf pixel() calls.
#        Each icon is 8 pixels wide; text starts at x=10 leaving a 2px gap.
#
# States: startup → ready/idle → (press → sending → result) → idle
# ----------------------------------------------------------------------------------------------------

class Display:
    """
    Enhanced wrapper around the PiicoDev SSD1306 OLED display.

    Features:
      - 8x8 pixel icons per action category drawn using raw framebuf primitives
      - Rich idle screen with a 2-column button map and live uptime counter
      - Toggle-state-aware result messages (e.g. TURBO: ON, LIGHTS: OFF)
      - Graceful no-op fallback if DISPLAY_ENABLED=False or hardware is missing

    If DISPLAY_ENABLED is False, or the hardware fails to initialise, every
    method becomes a silent no-op so the daemon runs unchanged without a display.
    """

    # ---- Layout constants --------------------------------------------------------
    _W      = 128   # screen width in pixels
    _H      = 64    # screen height in pixels
    _Y_TTL  = 0     # title bar y
    _Y_SEP  = 9     # horizontal separator y
    _Y_L1   = 12    # content line 1 y
    _Y_L2   = 22    # content line 2 y
    _Y_L3   = 32    # content line 3 y
    _Y_L4   = 42    # content line 4 y
    _Y_FTR  = 56    # footer y  (pushed to very bottom)
    _MAXC   = 16    # max chars per line at 8px/char × 128px width
    _IX     = 0     # icon x origin
    _TX     = 10    # text x when an icon is present (icon=8px + 2px gap)

    # ---- 8×8 icon bitmaps (row-major, MSB-left) ----------------------------------
    # Each entry is a list of 8 bytes, one per row, drawn top→bottom.
    # Bit 7 of each byte = leftmost pixel of that row.
    # Designed to be readable at 128×64 with an 8px font.
    _ICONS: Dict[str, List[int]] = {
        # Menu / Ultimate logo: simple "≡" hamburger lines
        "menu":     [0b00000000,
                     0b01111110,
                     0b00000000,
                     0b01111110,
                     0b00000000,
                     0b01111110,
                     0b00000000,
                     0b00000000],
        # Reset: circular arrow suggestion (top arc + tail)
        "reset":    [0b00111100,
                     0b01000010,
                     0b10000001,
                     0b10000101,
                     0b10000111,
                     0b01000000,
                     0b00111000,
                     0b00000000],
        # Power off: circle with a gap at the top + vertical line
        "power":    [0b00011000,
                     0b00011000,
                     0b01100110,
                     0b10000001,
                     0b10000001,
                     0b10000001,
                     0b01100110,
                     0b00111100],
        # Reboot: two curved arrows (simplified as two arcs)
        "reboot":   [0b00111100,
                     0b01000010,
                     0b10000101,
                     0b00000111,
                     0b11100000,
                     0b10100010,
                     0b01000010,
                     0b00111100],
        # Pause: two vertical bars  ▌▐
        "pause":    [0b00000000,
                     0b01100110,
                     0b01100110,
                     0b01100110,
                     0b01100110,
                     0b01100110,
                     0b01100110,
                     0b00000000],
        # Resume / play: solid right-pointing triangle  ▶
        "resume":   [0b10000000,
                     0b11000000,
                     0b11100000,
                     0b11110000,
                     0b11100000,
                     0b11000000,
                     0b10000000,
                     0b00000000],
        # Drive / disk: floppy disk outline with notch
        "disk":     [0b11111110,
                     0b10111110,
                     0b10111110,
                     0b10000010,
                     0b10111010,
                     0b10111010,
                     0b10111010,
                     0b11111110],
        # SID / music note: single eighth note ♪
        "music":    [0b00111110,
                     0b00100010,
                     0b00100010,
                     0b00100010,
                     0b01100010,
                     0b11100110,
                     0b01000100,
                     0b00000000],
        # Cartridge: rectangle with a small notch at the bottom (PCB edge connector)
        "cart":     [0b11111110,
                     0b10000010,
                     0b10000010,
                     0b10000010,
                     0b10000010,
                     0b10100010,  # small notch / teeth
                     0b10100010,
                     0b11111110],
        # Keyboard: rectangle with rows of dots inside (keys)
        "keys":     [0b11111110,
                     0b10101010,
                     0b11111110,
                     0b10101010,
                     0b11111110,
                     0b10000010,
                     0b10000010,
                     0b11111110],
        # Turbo / lightning bolt: zig-zag
        "turbo":    [0b00011110,
                     0b00111000,
                     0b01110000,
                     0b11111110,
                     0b00011100,
                     0b00111000,
                     0b01110000,
                     0b11000000],
        # Lights / bulb: circle with a flat base and two lines (filament)
        "lights":   [0b00111100,
                     0b01111110,
                     0b11011011,
                     0b11011011,
                     0b01111110,
                     0b01111110,
                     0b00111100,
                     0b00011000],
        # Error / bang: exclamation mark inside a diamond
        "error":    [0b00011000,
                     0b00111100,
                     0b01111110,
                     0b01111110,
                     0b00011000,
                     0b00011000,
                     0b00000000,
                     0b00011000],
        # OK / tick: a simple checkmark
        "ok":       [0b00000000,
                     0b00000001,
                     0b00000011,
                     0b00000110,
                     0b01001100,
                     0b01111000,
                     0b00110000,
                     0b00000000],
        # Shutdown / power off with downward arrow
        "shutdown": [0b00011000,
                     0b00011000,
                     0b01100110,
                     0b10000001,
                     0b10000001,
                     0b01000010,
                     0b00111100,
                     0b00011000],
    }

    # Map action function name keywords → icon key
    _ACTION_ICON: Dict[str, str] = {
        "menu_button":    "menu",
        "machine_reset":  "reset",
        "machine_poweroff": "power",
        "machine_reboot": "reboot",
        "machine_pause":  "pause",
        "machine_resume": "resume",
        "drive_":         "disk",    # prefix match
        "mount_disk":     "disk",
        "sid_play":       "music",
        "run_cart":       "cart",
        "send_keystrokes":"keys",
        "turbo_on_off":   "turbo",
        "lights_on_off":  "lights",
        "speaker_on_off": "lights",    # reuse lights icon (closest match)
        "next_disk":      "disk",
        "party_time":     "music",   # music icon = party!
    }

    # Short human-readable labels for the idle button map (max 5 chars to fit 2-col layout)
    _ACTION_LABEL: Dict[str, str] = {
        "menu_button":      "MENU",
        "machine_reset":    "RESET",
        "machine_poweroff": "POWER",
        "machine_reboot":   "REBT",
        "machine_pause":    "PAUSE",
        "machine_resume":   "RESME",
        "sid_play":         "SID",
        "run_cart":         "CART",
        "mount_disk_a":     "DSK-A",
        "mount_disk_b":     "DSK-B",
        "send_keystrokes":  "KEYS",
        "turbo_on_off":     "TURBO",
        "lights_on_off":    "LITES",
        "speaker_on_off":   "SPKR",
        "drive_a_reset":    "D-RST",
        "drive_b_reset":    "D-RST",
        "drive_a_remove":   "D-EJT",
        "drive_b_remove":   "D-EJT",
        "drive_a_on":       "D-ON",
        "drive_b_on":       "D-ON",
        "drive_a_off":      "D-OFF",
        "drive_b_off":      "D-OFF",
        "next_disk":        "NXT >",
        "party_time":       "PARTY",
    }

    def __init__(self, enabled: bool) -> None:
        # ---- Initialise ALL instance variables first -------------------------
        # This must happen before any early return or try/except so that every
        # attribute always exists, regardless of whether the display is enabled
        # or the hardware fails to initialise.  A missing attribute causes an
        # AttributeError crash in the main loop (e.g. screensaver_active).
        self._ok       = False
        self._d        = None
        self._start_ts = time.monotonic()

        # Screensaver state
        self._ss_active       = False
        self._ss_next_frame   = 0.0

        # Pac-Man screensaver state
        self._pm_x            = 6
        self._pm_y            = 30
        self._pm_dx           = 2
        self._pm_frame        = 0
        self._pm_pellets: set = set(range(14, 120, 10))

        # C64 logo screensaver state
        self._lg_x            = 22
        self._lg_y            = 8
        self._lg_vx           = 2
        self._lg_vy           = 1


        # ---------------------------------------------------------------------

        if not enabled:
            logging.info("Display: disabled in config")
            return
        try:
            from PiicoDev_SSD1306 import create_PiicoDev_SSD1306
            self._d = create_PiicoDev_SSD1306()
            if hasattr(self._d, "load_font"):
                try:
                    self._d.load_font("font-pet-me-128.dat")
                    logging.info("Display: font-pet-me-128.dat loaded")
                except Exception as fe:
                    logging.warning("Display: font file error: %s", fe)
            else:
                logging.info("Display: load_font not supported by this library build "
                             "(PiicoDev Linux variant) — using default 8x8 font")
            self._ok = True
            logging.info("Display: SSD1306 ready")
        except Exception as e:
            logging.warning("Display: init failed, running without display: %s", e)

    @property
    def ok(self) -> bool:
        return self._ok

    # ---- Helpers -----------------------------------------------------------------

    @staticmethod
    def _t(s: str, n: int = 16) -> str:
        """Truncate string to n characters."""
        return str(s)[:n]

    def _icon(self, name: str) -> None:
        """
        Draw an 8×8 icon at (_IX, _Y_L1) using raw pixel calls.
        Falls back silently if the icon name is not in _ICONS.
        """
        rows = self._ICONS.get(name)
        if not rows:
            return
        d = self._d
        for row_idx, byte in enumerate(rows):
            y = self._Y_L1 + row_idx
            for col in range(8):
                if byte & (0x80 >> col):
                    d.pixel(self._IX + col, y, 1)

    def _icon_for_action(self, action_name: str) -> str:
        """Return the icon key for a given action function name, or '' if none."""
        # Exact match first
        if action_name in self._ACTION_ICON:
            return self._ACTION_ICON[action_name]
        # Prefix match (e.g. "drive_a_reset" matches "drive_")
        for prefix, icon in self._ACTION_ICON.items():
            if action_name.startswith(prefix):
                return icon
        return ""

    def _label_for_action(self, action_name: str) -> str:
        """Return a short display label (max ~5 chars) for the idle button map."""
        if action_name in self._ACTION_LABEL:
            return self._ACTION_LABEL[action_name]
        # Prefix match for drive_ variants
        for prefix, label in self._ACTION_LABEL.items():
            if action_name.startswith(prefix):
                return label
        # Fall back to first 5 chars of the raw name, uppercased
        return action_name[:5].upper()

    def _uptime_str(self) -> str:
        """Return a compact uptime string: 'up 0d 00:00:00'."""
        secs  = int(time.monotonic() - self._start_ts)
        days  = secs // 86400
        secs -= days * 86400
        hh    = secs // 3600
        secs -= hh * 3600
        mm    = secs // 60
        ss    = secs % 60
        return f"up {days}d {hh:02d}:{mm:02d}:{ss:02d}"

    def _chrome(self) -> None:
        """Draw the shared title bar + separator + footer onto the current frame."""
        d = self._d
        d.text(self._t("C64U-btn-HAT"), 0, self._Y_TTL, 1)
        d.hline(0, self._Y_SEP, self._W, 1)
        d.text(self._t(f"C64:{IP}"), 0, self._Y_FTR, 1)

    def _render(self, l1: str = "", l2: str = "", l3: str = "", l4: str = "",
                icon: str = "") -> None:
        """
        Clear screen, draw chrome, optional icon at Y_L1, and up to 4 text lines.
        Text lines are offset right by _TX when an icon is present.
        All display updates for press/result/error/shutdown states go through here.
        """
        if not self._ok:
            return
        try:
            d = self._d
            d.fill(0)
            self._chrome()
            tx = self._TX if icon else 0
            if icon:
                self._icon(icon)
            if l1: d.text(self._t(l1, self._MAXC - (1 if icon else 0)), tx, self._Y_L1, 1)
            if l2: d.text(self._t(l2), tx, self._Y_L2, 1)
            if l3: d.text(self._t(l3), tx, self._Y_L3, 1)
            if l4: d.text(self._t(l4), tx, self._Y_L4, 1)
            d.show()
        except Exception as e:
            logging.warning("Display: render error: %s", e)

    def _render_idle(self, bindings: list) -> None:
        """
        Draw the rich idle screen:
          - 2-column button map (up to 3 rows × 2 cols = 6 buttons)
          - uptime counter on line 4
        Layout per cell: "B1 LABEL " — "B" + digit + space + label (5 chars) = 8 chars per col
        Two columns fit in 16 chars: [B1 LABEL  B4 LABEL]
        """
        if not self._ok:
            return
        try:
            d = self._d
            d.fill(0)
            self._chrome()

            # Build a dict of button number → short label for quick lookup
            btn_labels: Dict[int, str] = {}
            for b in bindings:
                # Extract button number from name e.g. "Button1" → 1
                try:
                    n = int(b.name.replace("Button", ""))
                    btn_labels[n] = self._label_for_action(b.action.__name__)
                except ValueError:
                    pass

            # Render 3 rows × 2 cols
            row_y  = [self._Y_L1, self._Y_L2, self._Y_L3]
            pairs  = [(1, 4), (2, 5), (3, 6)]
            for (left_n, right_n), y in zip(pairs, row_y):
                left_lbl  = btn_labels.get(left_n,  "----")
                right_lbl = btn_labels.get(right_n, "    ")
                # Left column: "B1 LABEL " (8 chars)
                left_cell  = f"B{left_n} {left_lbl:<5}"[:8]
                # Right column: "B4 LABEL" (8 chars)
                right_cell = f"B{right_n} {right_lbl:<5}"[:8] if right_n in btn_labels else ""
                d.text(left_cell, 0, y, 1)
                if right_cell:
                    d.text(right_cell, 64, y, 1)

            # Uptime on line 4
            d.text(self._t(self._uptime_str()), 0, self._Y_L4, 1)
            d.show()
        except Exception as e:
            logging.warning("Display: render idle error: %s", e)

    # ---- Public screen states ----------------------------------------------------

    def show_startup(self, stage: str = "Initialising..") -> None:
        """
        Splash shown while the daemon is booting.
        Call with different stage strings as init progresses:
          show_startup("Initialising..")
          show_startup("Loading buttons")
          show_startup("Connecting..")
        """
        self._render(stage)

    def show_ready(self, bindings: list) -> None:
        """Rich idle screen with button map and uptime — shown while waiting for presses."""
        self._render_idle(bindings)

    def show_button_press(self, btn_name: str, action_name: str) -> None:
        """
        Shown immediately on button detection, BEFORE the network request.
        Gives instant visual feedback even over a slow/absent network.
        """
        icon = self._icon_for_action(action_name)
        # Shorten "Button1" → "B1"
        short = btn_name.replace("Button", "B")
        self._render(f"{short} PRESSED", action_name, "Sending...", icon=icon)

    def show_result(self, btn_name: str, action_name: str, code: int,
                    toggle_label: str = "") -> None:
        """
        Shown after an action completes.

        toggle_label: optional override for toggle actions, e.g. "TURBO: ON",
                      "LIGHTS: OFF" — displayed instead of the HTTP code line.
        """
        icon = self._icon_for_action(action_name)
        short = btn_name.replace("Button", "B")

        if toggle_label:
            status = toggle_label
        elif 200 <= code < 300:
            status = f"OK  [{code}]"
        elif code == 0:
            status = "!! FAILED"
        else:
            status = f"ERR [{code}]"

        self._render(f"{short} PRESSED", action_name, status, icon=icon)

    def show_error(self, btn_name: str, msg: str) -> None:
        """Shown when the action function raises an exception before any request is sent."""
        short = btn_name.replace("Button", "B")
        self._render(f"{short} ERROR", self._t(msg), icon="error")

    def show_shutdown(self) -> None:
        """Shown when a shutdown/poweroff local command fires — stays on screen permanently."""
        self._render("Shutting down..", "Goodbye!", icon="shutdown")

    # ---- Screensaver ---------------------------------------------------------

    @property
    def screensaver_active(self) -> bool:
        return self._ss_active

    def screensaver_enter(self, mode: str) -> None:
        """Switch to screensaver mode. Clears screen immediately."""
        if not self._ok:
            return
        self._ss_active = True
        self._ss_next_frame = 0.0  # draw first frame immediately
        logging.info("Display: screensaver ON (%s)", mode)
        if mode == "blank":
            try:
                self._d.fill(0)
                self._d.show()
            except Exception as e:
                logging.warning("Display: screensaver blank error: %s", e)

    def screensaver_exit(self, bindings: list) -> None:
        """Wake from screensaver — restore the idle screen."""
        if not self._ok:
            return
        self._ss_active = False
        logging.info("Display: screensaver OFF")
        self._render_idle(bindings)

    def screensaver_step(self, mode: str) -> None:
        """
        Advance one animation frame of the active screensaver.
        Call this every main-loop iteration while screensaver is active.
        Honours SCREENSAVER_FPS — skips rendering if called faster than the target rate.
        """
        if not self._ok or not self._ss_active:
            return
        if mode == "blank":
            return  # already blank, nothing to animate

        now = time.monotonic()
        if now < self._ss_next_frame:
            return  # not time for next frame yet
        self._ss_next_frame = now + 1.0 / max(1, SCREENSAVER_FPS)

        try:
            if mode == "pacman":
                self._ss_pacman_frame()
            elif mode == "c64logo":
                self._ss_c64logo_frame()

        except Exception as e:
            logging.warning("Display: screensaver step error: %s", e)

    # ---- Pac-Man screensaver -------------------------------------------------
    #
    # Layout (128×64):
    #   Pac-Man travels horizontally at y=30, radius=5.
    #   Pellets are 2×2 dots at the same y row, spaced every 10px.
    #   Mouth opens/closes every 4 frames. Bounces at left/right edges.
    #   Ghost added for extra fun — travels at a different speed.
    #
    # Pac-Man radius: 5px → diameter 11px.
    # Pellet spacing: every 10px from x=14 to x=119 → 11 pellets.
    # Scores shown in top-right corner (pellets eaten this wave).
    # ------------------------------------------------------------------

    _PM_R = 5            # Pac-Man radius in pixels

    def _ss_pacman_draw_pacman(self, cx: int, cy: int, dx: int, mouth_open: bool) -> None:
        """Draw a filled circle with a mouth wedge cut out."""
        d   = self._d
        r   = self._PM_R
        # tan(40°) ≈ 0.839 — mouth half-angle
        TAN_MOUTH = 0.839

        for dy in range(-r, r + 1):
            hw = int((r * r - dy * dy) ** 0.5)
            x0 = cx - hw
            x1 = cx + hw

            if not mouth_open:
                d.hline(x0, cy + dy, x1 - x0 + 1, 1)
                continue

            # Mouth wedge: pixels within ±40° of travel direction are erased
            # |dy| / |dx_from_cx| < TAN_MOUTH  →  |dx_from_cx| > |dy| / TAN_MOUTH
            cut = int(abs(dy) / TAN_MOUTH) if dy != 0 else 0

            if dx >= 0:
                # Facing right — mouth eats from cx+cut onwards
                mouth_start = cx + cut
                if mouth_start <= x1:
                    # Draw left solid segment
                    seg_w = max(0, mouth_start - x0)
                    if seg_w > 0:
                        d.hline(x0, cy + dy, seg_w, 1)
                else:
                    d.hline(x0, cy + dy, x1 - x0 + 1, 1)
            else:
                # Facing left — mouth eats from cx-cut backwards
                mouth_end = cx - cut
                if mouth_end >= x0:
                    seg_w = max(0, x1 - mouth_end)
                    if seg_w > 0:
                        d.hline(mouth_end + 1, cy + dy, seg_w, 1)
                else:
                    d.hline(x0, cy + dy, x1 - x0 + 1, 1)

    def _ss_pacman_frame(self) -> None:
        """Render one Pac-Man animation frame."""
        d   = self._d
        r   = self._PM_R
        W   = self._W      # 128
        H   = self._H      # 64

        d.fill(0)

        # ---- Move Pac-Man ---------------------------------------------------
        self._pm_x += self._pm_dx
        # Bounce off edges (keep body fully on screen)
        if self._pm_x + r >= W - 1:
            self._pm_x  = W - 1 - r
            self._pm_dx = -abs(self._pm_dx)
        elif self._pm_x - r <= 0:
            self._pm_x  = r + 1
            self._pm_dx = abs(self._pm_dx)

        self._pm_frame += 1

        # ---- Eat pellets within range ---------------------------------------
        eaten = {px for px in self._pm_pellets if abs(px - self._pm_x) <= r + 2}
        self._pm_pellets -= eaten
        if not self._pm_pellets:
            # All eaten — respawn and briefly pause mouth
            self._pm_pellets = set(range(14, 120, 10))

        # ---- Draw pellets ---------------------------------------------------
        py = self._pm_y
        for px in self._pm_pellets:
            if abs(px - self._pm_x) > r:      # don't draw under Pac-Man
                d.fill_rect(px - 1, py - 1, 2, 2, 1)

        # ---- Draw Pac-Man ---------------------------------------------------
        mouth_open = (self._pm_frame // 4) % 2 == 0
        self._ss_pacman_draw_pacman(self._pm_x, self._pm_y, self._pm_dx, mouth_open)

        # ---- Score (pellets remaining) in top-right -------------------------
        score_str = str(len(self._pm_pellets))
        d.text(score_str, W - len(score_str) * 8, 0, 1)

        # ---- "PAC-MAN" label bottom-left ------------------------------------
        d.text("PAC-MAN", 0, H - 8, 1)

        d.show()

    # ---- C64 logo screensaver -----------------------------------------------
    #
    # Draws the Commodore C= logo procedurally and bounces it DVD-style.
    #
    # Construction:
    #   - Outer ring (r_out=8) with inner hole (r_in=5) forms the C body
    #   - Right-side opening (~±55°) creates the C mouth
    #   - Two thick parallelogram bars sit IN the mouth opening, extending
    #     slightly beyond the outer ring to the right (as in the real logo)
    #   - Each bar is 3 rows tall; the right edge steps by 1px per row,
    #     creating the angled/chevron shape of the real Commodore logo
    #
    # Real logo: bars are in the upper/lower quadrants of the opening,
    # NOT inside the inner hole. They taper toward the right like ">>".
    #
    # Bounding box: 20x17px (ring=17px wide, bars overhang 3px on right).
    # Bounce area: x=[0..107], y=[0..46].
    # ------------------------------------------------------------------

    _LG_R_OUT = 8    # outer radius of the Commodore ring
    _LG_R_IN  = 5    # inner radius (hole — makes it a ring)
    _LG_W     = 20   # bounding box width (ring 17px + 3px bar overhang)
    _LG_H     = 17   # bounding box height

    def _ss_c64logo_draw(self, ox: int, oy: int) -> None:
        """
        Draw the Commodore C= logo with bounding-box top-left at (ox, oy).

        The two bars are thick angled parallelograms in the C opening gap:
          - 3 rows tall each, positioned in the upper and lower quadrants
          - Left edge at cx+3 (clear of ring body), right edge extends to
            cx+11 at the widest row (3px past the outer ring, like the real logo)
          - Right edge steps by 1px per row creating the diagonal angle

          Top bar  (wide at top, tapering toward bottom) looks like: \
          Bottom bar (narrow at top, widening toward bottom) looks like: /
          Together they form the ">>" chevron of the Commodore C= logo.
        """
        d      = self._d
        r_out  = self._LG_R_OUT
        r_in   = self._LG_R_IN
        cx     = ox + r_out     # circle centre x  (= ox+8)
        cy     = oy + r_out     # circle centre y  (= oy+8)

        # 1. Draw filled outer circle
        for dy in range(-r_out, r_out + 1):
            hw = int((r_out * r_out - dy * dy) ** 0.5)
            d.hline(cx - hw, cy + dy, hw * 2 + 1, 1)

        # 2. Cut out inner hole to form the ring
        for dy in range(-r_in, r_in + 1):
            hw = int((r_in * r_in - dy * dy) ** 0.5)
            d.hline(cx - hw, cy + dy, hw * 2 + 1, 0)

        # 3. Cut out right-side opening (~±55°) to create the C shape
        TAN_OPEN = 1.428   # tan(55°)
        for dy in range(-r_out, r_out + 1):
            hw = int((r_out * r_out - dy * dy) ** 0.5)
            if dy == 0:
                open_x = cx + 1
            else:
                open_x = cx + max(1, int(abs(dy) / TAN_OPEN))
            x_end = cx + hw
            if open_x <= x_end:
                d.hline(open_x, cy + dy, x_end - open_x + 1, 0)

        # 4. Draw the two thick angled bars in the opening gap.
        #
        #    Both bars share the same left edge (cx+3, inside the opening).
        #    The right edge steps by 1px per row to create the diagonal angle.
        #
        #    Top bar — wide at top (dy=-5), tapering as it approaches centre:
        #      dy=-5 :  cx+3 .. cx+11  →  9px wide  (widest)
        #      dy=-4 :  cx+3 .. cx+10  →  8px wide
        #      dy=-3 :  cx+3 .. cx+9   →  7px wide  (narrowest)
        #
        #    Bottom bar — narrow at top, widening away from centre:
        #      dy=+3 :  cx+3 .. cx+9   →  7px wide  (narrowest)
        #      dy=+4 :  cx+3 .. cx+10  →  8px wide
        #      dy=+5 :  cx+3 .. cx+11  →  9px wide  (widest)
        #
        BAR_X0 = cx + 3   # left edge of both bars

        # Top bar
        for step, dy in enumerate([-5, -4, -3]):
            x1 = cx + 11 - step       # 11, 10, 9
            w  = x1 - BAR_X0 + 1
            if w > 0:
                d.hline(BAR_X0, cy + dy, w, 1)

        # Bottom bar (mirror of top)
        for step, dy in enumerate([3, 4, 5]):
            x1 = cx + 9 + step        # 9, 10, 11
            w  = x1 - BAR_X0 + 1
            if w > 0:
                d.hline(BAR_X0, cy + dy, w, 1)

    def _ss_c64logo_frame(self) -> None:
        """Render one C64 logo bounce frame."""
        d  = self._d
        W  = self._W          # 128
        H  = self._H          # 64
        lw = self._LG_W       # 20
        lh = self._LG_H       # 17

        d.fill(0)

        # ---- Move logo ------------------------------------------------------
        self._lg_x += self._lg_vx
        self._lg_y += self._lg_vy

        # Bounce off right/left walls
        if self._lg_x + lw >= W:
            self._lg_x  = W - lw - 1
            self._lg_vx = -abs(self._lg_vx)
        elif self._lg_x <= 0:
            self._lg_x  = 0
            self._lg_vx = abs(self._lg_vx)

        # Bounce off bottom/top walls
        if self._lg_y + lh >= H:
            self._lg_y  = H - lh - 1
            self._lg_vy = -abs(self._lg_vy)
        elif self._lg_y <= 0:
            self._lg_y  = 0
            self._lg_vy = abs(self._lg_vy)

        # ---- Draw logo + label ----------------------------------------------
        self._ss_c64logo_draw(self._lg_x, self._lg_y)

        # "-=COMMODORE64U=-" text — placed away from logo if possible
        label_y = 56 if self._lg_y < 40 else 0
        d.text("-=COMMODORE64U=-", 0, label_y, 1)

        d.show()



_local_cmd_lock = threading.Lock()
_local_cmd_seq  = 0


@dataclass(frozen=True)
class ButtonBinding:
    name: str
    switch_id: List[int]
    action: ActionFn
    local_command: str = ""  # optional per-button local command


def _build_headers() -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if C64U_PASSWORD.strip():
        headers["X-Password"] = C64U_PASSWORD.strip()
    return headers


def http_request(
    url: str,
    method: str,
    headers: Optional[Dict[str, str]] = None,
    body: Optional[bytes] = None
) -> int:
    req = urllib.request.Request(url, data=body, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            resp.read()
            return resp.getcode()
    except urllib.error.HTTPError as e:
        try:
            e.read()
        except Exception:
            pass
        return e.code
    except Exception as exc:
        # Log the full URL and exception so failures are visible in journalctl.
        # Previously this was a silent "return 0" — the most common cause of
        # a mysterious "-> 0" in the press log.
        logging.warning("http_request: %s %s FAILED [%s] %s",
                        method, url, type(exc).__name__, exc)
        return 0


def request_with_retries(
    url: str,
    method: str,
    headers: Optional[Dict[str, str]] = None,
    body: Optional[bytes] = None
) -> int:
    for attempt in range(RETRIES + 1):
        logging.info("http_request attempt %d/%d: %s %s", attempt + 1, RETRIES + 1, method, url)
        code = http_request(url, method=method, headers=headers, body=body)
        if code != 0:
            return code
        if attempt < RETRIES:
            time.sleep(RETRY_DELAY_S)
    return 0


def send_keystrokes_tcp(req: KeystrokeRequest) -> int:
    """
    Send a single KeystrokeRequest to the keyboard daemon.
    Returns 200 on success, 0 on failure (to integrate with retry logic).
    """
    msg = {
        "token": req.token,
        "op": "type",
        "text": req.text,
    }
    data = (json.dumps(msg) + "\n").encode("utf-8")

    try:
        with socket.create_connection((req.host, int(req.port)), timeout=3) as s:
            s.sendall(data)

            # read one line reply (best-effort)
            s.settimeout(15)
            buf = b""
            while b"\n" not in buf:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk

        return 200
    except Exception:
        return 0


def keystrokes_with_retries(req: KeystrokeRequest) -> int:
    for attempt in range(RETRIES + 1):
        code = send_keystrokes_tcp(req)
        if code != 0:
            return code
        if attempt < RETRIES:
            time.sleep(RETRY_DELAY_S)
    return 0


def flash_led(btn: PiicoDev_Switch, pulses: int = 1, on_ms: int = LED_ON_MS, off_ms: int = LED_OFF_MS) -> None:
    """
    Flash the PiicoDev Button POWER LED in a visible way (OFF -> ON).
    Restores previous LED state afterwards.
    """
    if pulses <= 0:
        return

    # Read prior state (best-effort)
    try:
        prev = bool(btn.led)
    except Exception:
        prev = True  # default: these are usually ON

    try:
        for _ in range(int(pulses)):
            # Force a visible change first (turn OFF)
            try:
                btn.led = False
            except Exception:
                pass
            sleep_ms(int(off_ms))

            # Then ON
            try:
                btn.led = True
            except Exception:
                pass
            sleep_ms(int(on_ms))
    finally:
        # Restore previous LED state
        try:
            btn.led = prev
        except Exception:
            pass


def _run_local_command(cmd: str, seq: int, label: str) -> None:
    if not cmd.strip():
        return

    logging.info("%s command #%d starting: %s", label, seq, cmd)
    try:
        res = subprocess.run(
            ["bash", "-lc", cmd],
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_S,
        )

        if res.stdout.strip():
            logging.info("%s command #%d stdout: %s", label, seq, res.stdout.strip())
        if res.stderr.strip():
            logging.warning("%s command #%d stderr: %s", label, seq, res.stderr.strip())

        logging.info("%s command #%d finished with return code %d", label, seq, res.returncode)

    except subprocess.TimeoutExpired:
        logging.warning("%s command #%d timed out after %ss", label, seq, COMMAND_TIMEOUT_S)
    except Exception as e:
        logging.exception("%s command #%d failed: %s", label, seq, e)


def run_local_command_async(cmd: str, label: str) -> None:
    global _local_cmd_seq
    if not cmd.strip():
        return

    with _local_cmd_lock:
        _local_cmd_seq += 1
        seq = _local_cmd_seq

    t = threading.Thread(
        target=_run_local_command,
        args=(cmd, seq, label),
        daemon=True,
        name=f"{label}-cmd-{seq}",
    )
    t.start()


def _validate_id(switch_id: List[int]) -> None:
    if not isinstance(switch_id, list) or len(switch_id) != 4:
        raise ValueError(f"PiicoDev Switch id must be a list of 4 ints, got: {switch_id}")
    for v in switch_id:
        if v not in (0, 1):
            raise ValueError(f"PiicoDev Switch id values must be 0/1, got: {switch_id}")


# These are the factory functions that MUST be called with () to produce an ActionFn.
# Assigning them bare (e.g. BUTTON2ACTION = next_disk) is the most common config mistake:
# the factory itself becomes the "action", its call at press-time returns _action (another
# callable), which str()-ifies into a garbage URL that fails silently.
_FACTORY_FUNCTIONS = frozenset({
    next_disk, mount_disk, drive_reset, drive_remove, drive_on, drive_off,
    sid_play, run_cart, send_keystrokes, party_time,
})


def get_configured_bindings() -> List[ButtonBinding]:
    bindings: List[ButtonBinding] = []

    config: List[Tuple[str, List[int], Optional[ActionFn], str]] = [
        ("Button1", BUTTON1_ID, BUTTON1ACTION, ""),
        ("Button2", BUTTON2_ID, BUTTON2ACTION, ""),
        ("Button3", BUTTON3_ID, BUTTON3ACTION, BUTTON3COMMAND),
        ("Button4", BUTTON4_ID, BUTTON4ACTION, ""),
        ("Button5", BUTTON5_ID, BUTTON5ACTION, ""),
        ("Button6", BUTTON6_ID, BUTTON6ACTION, ""),
    ]

    for name, sid, action, local_cmd in config:
        if action is None:
            continue
        _validate_id(sid)
        if not callable(action):
            raise TypeError(f"{name} action must be a function (callable), got: {action!r}")

        # Catch the common mistake of assigning a factory without calling it.
        # e.g.  BUTTON2ACTION = next_disk        ← WRONG  (returns another callable)
        #       BUTTON2ACTION: Optional[ActionFn] = next_disk()       ← correct (returns the _action closure)
        if action in _FACTORY_FUNCTIONS:
            raise TypeError(
                f"{name}: '{action.__name__}' is a factory function and must be called with "
                f"parentheses, e.g.  BUTTON_ACTION = {action.__name__}()  "
                f"(see the BUTTON ACTION EXAMPLES section)"
            )

        bindings.append(ButtonBinding(name=name, switch_id=sid, action=action, local_command=local_cmd))

    return bindings


def init_buttons(bindings: List[ButtonBinding]) -> List[Tuple[ButtonBinding, PiicoDev_Switch]]:
    runtime: List[Tuple[ButtonBinding, PiicoDev_Switch]] = []
    for b in bindings:
        sw = PiicoDev_Switch(id=b.switch_id, suppress_warnings=True)
        runtime.append((b, sw))
    return runtime


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s"
    )
    logging.info("c64_button_daemon starting")
    logging.info("Target IP: %s", IP)

    # ---- Display init -------------------------------------------------------
    display = Display(DISPLAY_ENABLED)
    display.show_startup("Initialising..")
    # -------------------------------------------------------------------------

    base_headers = _build_headers()
    if base_headers.get("X-Password"):
        logging.info("Using X-Password header (Ultimate Network Password enabled)")

    bindings = get_configured_bindings()
    logging.info("Configured buttons: %s", ", ".join([f"{b.name}→{b.action.__name__}" for b in bindings]))

    # Keep trying until I2C/buttons are ready
    display.show_startup("Loading buttons")
    while True:
        try:
            buttons = init_buttons(bindings)
            break
        except Exception as e:
            logging.warning("Button init failed (I2C not ready yet?): %s", e)
            time.sleep(2)

    # Clear any latched was_pressed events that accumulated during boot.
    # was_pressed is a hardware latch — reading it clears it automatically.
    # Two passes ensures anything that fired between passes is also flushed.
    for _ in range(2):
        for _, btn in buttons:
            try:
                btn.was_pressed   # read-and-clear the hardware latch
            except Exception:
                pass
        time.sleep(0.05)
    logging.info("Ready. Waiting for button presses...")
    if SCREENSAVER_MODE != "off":
        logging.info("Screensaver: %s, activates after %ds idle", SCREENSAVER_MODE, SCREENSAVER_DELAY_S)
    display.show_ready(bindings)

    # Tracks when to revert the display back to the idle/ready screen.
    # 0.0 means "already on idle screen, nothing to revert".
    display_idle_at:    float = 0.0
    # Tracks when to next refresh the idle screen's uptime clock.
    display_refresh_at: float = time.monotonic() + DISPLAY_IDLE_REFRESH_S
    # Tracks the last time any button was pressed (for screensaver timeout).
    last_activity_at:   float = time.monotonic()

    while True:
        now = time.monotonic()

        # ---- Screensaver animation step -------------------------------------
        # Uses elif so idle-screen refresh is skipped while screensaver runs,
        # but execution ALWAYS falls through to the button loop below so that
        # any button press can wake the screen.
        idle_secs = now - last_activity_at
        if SCREENSAVER_MODE != "off" and idle_secs >= SCREENSAVER_DELAY_S:
            if not display.screensaver_active:
                display.screensaver_enter(SCREENSAVER_MODE)
            display.screensaver_step(SCREENSAVER_MODE)

        # ---- Idle display revert + uptime refresh (skipped during screensaver)
        elif 0 < display_idle_at <= now:
            # Result/error timer expired — return to idle
            display.show_ready(bindings)
            display_idle_at    = 0.0
            display_refresh_at = now + DISPLAY_IDLE_REFRESH_S

        elif display_idle_at == 0.0 and now >= display_refresh_at:
            # Already on idle screen — just tick the uptime clock
            display.show_ready(bindings)
            display_refresh_at = now + DISPLAY_IDLE_REFRESH_S
        # ---------------------------------------------------------------------

        for binding, btn in buttons:
            # was_pressed is a hardware latch on the PiicoDev_Switch firmware:
            # it returns True exactly once per physical press then auto-clears.
            # This is far more reliable than press_count, which does NOT
            # auto-clear on Linux and causes phantom repeated fires.
            try:
                pressed = btn.was_pressed
            except Exception as e:
                logging.warning("%s: error reading was_pressed: %s", binding.name, e)
                continue

            if not pressed:
                continue

            presses = 1  # was_pressed is boolean — always treat as one press

            # Any button press counts as activity — reset screensaver timer
            last_activity_at = time.monotonic()

            # If screensaver was active, wake the display first
            if display.screensaver_active:
                display.screensaver_exit(bindings)
                display_idle_at    = 0.0
                display_refresh_at = time.monotonic() + DISPLAY_IDLE_REFRESH_S
                # Wake-only: don't execute the action on the first press after screensaver.
                # Comment out the next two lines to make button press both wake AND fire.
                logging.info("Screensaver woken by %s", binding.name)
                continue

            # LED feedback — run in a thread so the 600ms blink never
            # blocks the main loop (and can't cause phantom double-fires).
            if FLASH_LED_ON_PRESS:
                threading.Thread(
                    target=flash_led,
                    args=(btn,),
                    kwargs={"pulses": int(presses)},
                    daemon=True,
                    name=f"led-{binding.name}",
                ).start()

            # Show immediate feedback BEFORE the network request
            display.show_button_press(binding.name, binding.action.__name__)

            # Resolve action spec (may also toggle internal state, e.g. turbo/lights)
            try:
                spec = binding.action()
            except LastDiskInfo as e:
                # Not a failure — the user is already on the last disk.
                # Show it as an informational result (disk icon, no error colour).
                logging.info("%s: %s", binding.name, e)
                display.show_result(
                    binding.name,
                    "next_disk",
                    200,
                    toggle_label=f"LAST DISK {e.current}/{e.total}",
                )
                display_idle_at = time.monotonic() + DISPLAY_RESULT_S
                continue
            except Exception as e:
                logging.error("%s action '%s' failed: %s", binding.name, binding.action.__name__, e)
                display.show_error(binding.name, str(e))
                display_idle_at = time.monotonic() + DISPLAY_RESULT_S
                continue

            # Build request parameters from the resolved spec type
            if isinstance(spec, ActionRequest):
                method     = spec.method.upper()
                path       = spec.path
                debug_name = spec.debug_name or binding.action.__name__
                headers    = dict(base_headers)
                body       = None
                if spec.json_body is not None:
                    body = json.dumps(spec.json_body, separators=(",", ":")).encode("utf-8")
                    headers["Content-Type"] = "application/json"

            elif isinstance(spec, KeystrokeRequest):
                method     = "TCP"
                path       = ""
                debug_name = spec.debug_name or binding.action.__name__
                headers    = dict(base_headers)
                body       = None

            else:
                method     = "PUT"
                path       = str(spec)
                debug_name = binding.action.__name__
                headers    = dict(base_headers)
                body       = None

            url = f"http://{IP}{path}"

            # Execute once per registered press; track last result code for display
            last_code = 0
            for _ in range(int(presses)):
                if method == "TCP":
                    code = keystrokes_with_retries(spec)
                else:
                    code = request_with_retries(url, method=method, headers=headers, body=body)
                last_code = code
                logging.info("%s press -> %s %s -> %s", binding.name, method, debug_name, code)

                # Optional local command (async, e.g. Pi shutdown on Button3)
                if binding.local_command.strip():
                    run_local_command_async(binding.local_command, label=binding.name)

            # Build a toggle-state label for functions that have internal on/off state
            toggle_label = ""
            aname = binding.action.__name__
            if aname == "turbo_on_off":
                toggle_label = "TURBO: ON  >>>" if _turbo_enabled else "TURBO: OFF"
            elif aname == "lights_on_off":
                toggle_label = "LIGHTS: ON  *" if _lights_enabled else "LIGHTS: OFF"
            elif aname == "speaker_on_off":
                toggle_label = "SPEAKER: ON" if _speaker_enabled else "SPEAKER: OFF"
            elif aname == "party_time":
                toggle_label = "PARTY TIME! :)"
            elif aname == "next_disk" and last_code == 404:
                # 404 from next_disk means the blind-increment fallback tried a
                # filename that doesn't exist — we're already on the last disk.
                # Show a friendly informational message instead of "ERR [404]".
                logging.info("%s: next_disk blind-increment got 404 — last disk", binding.name)
                toggle_label = "LAST DISK"
                last_code = 200  # treat as success for display colouring

            # Show result on display after all presses are processed
            display.show_result(binding.name, debug_name, last_code, toggle_label=toggle_label)
            display_idle_at = time.monotonic() + DISPLAY_RESULT_S

            # Special case: if the local command looks like a system shutdown,
            # switch to the shutdown screen and don't revert to idle.
            lc = binding.local_command.lower()
            if binding.local_command.strip() and any(
                kw in lc for kw in ("shutdown", "poweroff", "halt", "reboot")
            ):
                display.show_shutdown()
                display_idle_at = 0.0  # stay on shutdown screen

        sleep_ms(POLL_MS)


if __name__ == "__main__":
    main()
