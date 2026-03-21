
<img width="1200" height="640" alt="Project-Image" src="https://github.com/user-attachments/assets/30421d25-9df7-4f5d-a61b-83e5f06f6bf2" />


# C64U-btn-HAT

A button HAT for the Raspberry Pi Zero W 2 + Commodore 64 Ultimate, providing 1-6 programmable buttons (recommended button configs are 3, 4, 5 & 6), using a PiicoDev Adapter for Raspberry Pi/PiicoDev Buttons for easy polling via the I2C bus.<br><br>

**What is this Project?**<br>
This project will give you programmable buttons for your **Commodore 64 Ultimate**, super convenient, easily toggle functions of your choice via a quick button press, no more fluffing around in menus! Some examples of the buttons are functions like menu, freeze/reset, lights on & off, speaker on & off, turbo boost and my all personal favourite buttons, party time and mount next disk! Dozens of pre-built functions, easily customisable and extensible, this project will let you do almost anything on your C64U, if paired with the C64-Bridge-Project, you can even send keystrokes to your C64U!<br><br>

> [!NOTE]
> Best used with the C64-Bridge-Project, but works super regardless! see https://github.com/brett-olsen/C64-Bridge-Project<br>

<br>

**C64U-btn-HAT Hardware**<br>
1 x Pi Zero 2 W  [(example)](https://core-electronics.com.au/raspberry-pi-zero-2-w-wireless-soldered-male-headers.html)<br>
1 x PiicoDev Adapter for Raspberry Pi https://core-electronics.com.au/piicodev-adapter-for-raspberry-pi.html<br>
n x PiicoDev Button https://core-electronics.com.au/piicodev-button.html (recommend configurations of 3, 4, 5 and 6 buttons)<br>
1 x OTG micro-USB shim  [(example)](https://core-electronics.com.au/tiny-otg-adapter-usb-micro-to-usb.html)<br>
1 x USB A 2.0 Male to Male cable (keep it short)<br>
1 x micro SD card (at least 4 GB)<br>
1 x Pi Zero 2 W Case (optional)  [(example)](https://core-electronics.com.au/slim-case-for-raspberry-pi-zero.html)<br>
1 x PiicoDev OLED Display Module (128x64) SSD1306 (optional) https://core-electronics.com.au/piicodev-oled-display-module-128x64-ssd1306.html
<br><br>
**Other**<br>
Optional : Access to a 3D printer, to print the button mount or buttons
<br><br>

# Getting it up & running

> [!NOTE]
> These instructions assume you already have the C64-Bridge-Project up and running, even if you don't want to use the C64-Bridge-Project you can follow the instructions to get your Raspberry Pi Zero up and running, instructions are located over at:<br>
> https://github.com/brett-olsen/C64-Bridge-Project/blob/main/README.md#getting-it-up--running

<br><br>
**1) Enable I2C**<br>
The PiicoDev buttons and display communicate over I2C, to enable I2C on your Raspberry Pi SSH into your PI, then either:

```
sudo raspi-config
```

Navigate to **Interface Options → I2C → Enable**.<br><br>
Or do it manually — open `/boot/firmware/config.txt` and add these two lines at the bottom:

```
dtparam=i2c_arm=on
dtparam=i2c_arm_baudrate=400000
```

<br>Then add your user to the `i2c` group and reboot:

```bash
sudo usermod -aG i2c "$USER"
sudo reboot
```
<br>
After reboot, verify I2C is working. You should see your connected devices listed (typically at address `0x3C` for the display and `0x10`–`0x13` for buttons):

```bash
sudo apt install -y i2c-tools
i2cdetect -y 1
```
<br><br>

**2) Install the C64U-btn-HAT Project Files**<br>
Firstly lets create a project folder, set the permissions and get everything ready for the project files:

```bash
sudo mkdir -p /opt/c64_button_daemon
sudo chown -R "$USER":"$USER" /opt/c64_button_daemon
cd /opt/c64_button_daemon
```
<br>
Now lets download the main daemon script, this controls the buttons, has all the wrapper functions, communicates with the C64U API's, etc:

```bash
curl -LO https://raw.githubusercontent.com/brett-olsen/C64U-btn-HAT/main/c64_button_daemon.py
```
<br>
With the main daemon downloaded, lets now download the libraries we need for the project, firstly the PiicoDev button support, then the optional libraries for the SSD1306 OLED display:

```bash
# Required: button HAT support
curl -LO https://raw.githubusercontent.com/CoreElectronics/CE-PiicoDev-Switch-MicroPython-Module/main/PiicoDev_Switch.py
curl -LO https://raw.githubusercontent.com/CoreElectronics/CE-PiicoDev-Unified/main/PiicoDev_Unified.py

# Optional: only needed if you have the SSD1306 OLED display
curl -LO https://raw.githubusercontent.com/CoreElectronics/CE-PiicoDev-SSD1306-MicroPython-Module/main/PiicoDev_SSD1306.py
curl -LO https://raw.githubusercontent.com/CoreElectronics/CE-PiicoDev-SSD1306-MicroPython-Module/main/font-pet-me-128.dat
```
<br>

Finally, lets verify your directory structure/files should now look something like this:

```
/opt/c64_button_daemon/
├── c64_button_daemon.py
├── PiicoDev_Switch.py
├── PiicoDev_Unified.py
├── PiicoDev_SSD1306.py      ← optional (display)
└── font-pet-me-128.dat      ← optional (display font)
```

<br><br>
**3) Configure & Test the Daemon + Buttons**<br>

Open the c64_button_daemon.py script and edit the **CONFIG** section near the top:

```bash
nano /opt/c64_button_daemon/c64_button_daemon.py
```
<br>
Firstly, set the IP Address of your Commodore C64 Ultimate:

```python
# Set the IP to the address of your C64 Ultimate
IP = "192.168.1.64"
```
<br>

If your wanting to send keystrokes to your Commodore C64 Ultimate, and have setup the bridge adapter as per the instructions (see https://github.com/brett-olsen/C64-Bridge-Project) then also configure the bridge variables:

```python
# Optional: C64 Keyboard Daemon (USB HID Bridge) settings.
# These can be overridden at runtime via environment variables without editing this file.
C64KBD_PI_HOST  = os.getenv("C64KBD_PI_HOST", "192.168.1.99")
C64KBD_PI_PORT  = int(os.getenv("C64KBD_PI_PORT", "9999"))
C64KBD_TOKEN    = os.getenv("C64KBD_TOKEN", "ILoveMyCommodoreC64")
```
<br>

Optionally you can tweak some of the daemon polling settings, for example reducing the POLL_MS value will reduce the CPU time of the daemon, but overall these defaults should be fine:
```python
# Daemon polling settings
POLL_MS = 150           # how often to poll buttons
HTTP_TIMEOUT_S = 3.0    # network timeout
RETRIES = 2             # retry count per press if request fails
RETRY_DELAY_S = 0.2     # retry delay
COMMAND_TIMEOUT_S = 60  # max seconds for local command threads
```
<br>

Lastly, another option before we move on to the actual button configuration, is the optional display settings, set to disabled is the default, but here you can enable/disable the display, setup refresh and, if you like choose a retro inspired screensaver:

```python
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
```
<br>

Finally, we can configure the buttons, there are two button related configurations that need checking, the button ID's and the button mappings (which functions the buttons execute). The button ID's are set via physical DIP switches (if using the PiicoDev Buttons), you can see the button DIP switch configuration in the first part of the BUTTON MAPPING area in the main c64_button_daemon.py file:
```python
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
```
<br>

Now you can set the button actions. The default is 3 buttons, the first being menu_button, second speaker_on_off and finally the third being lights_on_off. At the moment, I have tested this project with 3, 4 and 6 buttons, conceivably, you could use any number of buttons depending on the voltage demands. To disable a button, simply set Optional[ActionFn] = None, see the default button configuration below:

```python
# Default 3 button setup
BUTTON1ACTION: Optional[ActionFn] = menu_button
BUTTON2ACTION: Optional[ActionFn] = speaker_on_off
BUTTON3ACTION: Optional[ActionFn] = lights_on_off

# Extended additional 3 button actions (for a total of 6)
BUTTON4ACTION: Optional[ActionFn] = None
BUTTON5ACTION: Optional[ActionFn] = None
BUTTON6ACTION: Optional[ActionFn] = None
```
<br>

Here is a list of the button action examples you can use, there are a couple of composite and intelligent functions that I have built ranging from Friday retro fun time like the party_time function, to the incredibly useful intelligent function like next_disk and the handy function turbo_on_off. These functions can easily be extended, linked to new API calls, or tied to other services on the C64 Ultimate to do almost anything! I'll be adding more button functions when time permits, usually writing the functions is easy, just need a bit of time for testing =)
```python
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
```
<br><br>
I have tried to document the button functions as best I can, i'll add more comments & notes when time permits, a couple of clarifiers for specific button functions follows:
- machine_reset
  - a handy function, a soft reset but when a cartridge image is loaded and its applicable, this acts as a "freeze" button, works great with carts like the Action Replay series, etc
- mount_disk
  - just take note of the path, when browsing your C64 Ultimate, and you should be ok, the Ultimate has some quirks with long filenames, spaces should be automatically escaped, not sure about other special characters, but working examples for mount_disk are above
- next_disk
  - I love this function, it first tries to get a listing via FTP, so make sure these services are enabled, then if we can't determine the next disk, or we hit the FTP file length bug on the C64 Ultimate, we perform a "best guess" as to the next disk, I tested this on a variety of disk naming conventions, but let me know if you run into specific filenames that don't work
- turbo_on_off
  - this function is a toggle, its hardcoded at 64Mhz, feel free to adjust to suit, I'll think about making an additonal, seperate function which lets your rotate (n) number of CPU speeds =)
- lights_on_off
  - another toggle, I try not to over-write too many settings here, so it preserves some of the user preferences if possible, you can tweak this function to your needs
- speaker_on_off
  - same as the other toggles, you can tweak this to your needs also
- party_time
  - this is totally 100% for fun :D, the function will mount your fav demo, switch on the lights, switch on the speaker, and then manually type the load command on the keyboard, tweak this to your taste, it can take a path for the disk image you want to mount, party on! 
- BUTTON3COMMAND
  - this is an optional local command to be run on the Raspberry Pi, in my case, originally I had button 3 set to machine_poweroff and BUTTON3COMMAND set to "/usr/bin/sudo /usr/sbin/shutdown -h now", this is a little janky, and may not quite shutdown the Raspberry Pi cleanly, i'll review this when I get some time
<br><br>


If your interested, this is my Button Config that I personally use at the time of writing:
```python
# Default 3 button setup
BUTTON1ACTION: Optional[ActionFn] = menu_button
BUTTON2ACTION: Optional[ActionFn] = speaker_on_off
BUTTON3ACTION: Optional[ActionFn] = lights_on_off

# Extended additional 3 button actions (for a total of 6)
BUTTON4ACTION: Optional[ActionFn] = next_disk()
BUTTON5ACTION: Optional[ActionFn] = turbo_on_off
BUTTON6ACTION: Optional[ActionFn] = party_time("/USB1/DEMOSCENE/1337 - Fairlight/1337 - Fairlight - Disk A.d64")
```
<br><br>

**4) Manual Testing**<br>
Before we setup the python scripts as a service, lets first confirm that everything works, change to the project directory and manually execute the project file:

```bash
chmod +x /opt/c64_button_daemon/c64_button_daemon.py
cd /opt/c64_button_daemon
python3 c64_button_daemon.py
```
<br>
You should see some debug output lines, as follows:
<img width="1134" height="594" alt="Screenshot_20260321_181419" src="https://github.com/user-attachments/assets/169d67c5-5384-452f-b32f-b1267d5de1ea" />
<br>
Now you can test your button configurations, press the buttons and confirm they are all working how you expect, and you don't get any errors on the debug console, when done, you can press `Ctrl+C` to stop.
<br><br>

**5) Enabling the Service**<br>
Ok with all the hard work done, the config all working and tested we can enable this now as a daemon so it runs automatically on boot, firstly lets create the service file:

```bash
sudo nano /etc/systemd/system/c64_button_daemon.service
```

In our example, we created and setup the Raspberry Pi Zero with the user `c64`, you need to replace this with your username (run `whoami` if unsure):
```ini
[Unit]
Description=C64U-btn-HAT (PiicoDev Buttons -> C64 Ultimate API)
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=c64
WorkingDirectory=/opt/c64_button_daemon
ExecStart=/usr/bin/python3 /opt/c64_button_daemon/c64_button_daemon.py
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=1

[Install]
WantedBy=multi-user.target
```
<br>

Now that is done, we simply need to enabled and start the service, with the following command:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now c64_button_daemon.service
```
<br>

To check that the service is running, which is also handy for troubleshooting, you can issue the following command;
```bash
sudo systemctl status c64_button_daemon.service
```
<br>

---

***Congratulations! You have successfully setup the C64U-btn-HAT, I hope this eases some of the friction you might experience with the awesome, but very dense menus on your new Commodore C64 Ultimate =)***

---

<br>

**6) Troubleshooting & Useful Commands**<br>
View the live debug logs (follow):
```bash
sudo journalctl -u c64_button_daemon.service -f
```
<br>

View the last (n) log lines:
```bash
sudo journalctl -u c64_button_daemon.service -n 30 --no-pager
```
<br>

Restart and re-load configuration file changes:
```bash
sudo systemctl restart c64_button_daemon.service
```
<br>

Stop the C64U-btn-HAT daemon:
```bash
sudo systemctl stop c64_button_daemon.service
```
<br>

Check the I2C bus to confirm that the buttons and/or display are detected
```bash
i2cdetect -y 1
```
<br>



