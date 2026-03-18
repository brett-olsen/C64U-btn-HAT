
<img width="1200" height="640" alt="Project-Image" src="https://github.com/user-attachments/assets/30421d25-9df7-4f5d-a61b-83e5f06f6bf2" />


# C64U-btn-HAT

A button HAT for the Raspberry Pi Zero W 2 + Commodore 64 Ultimate, providing 3, 4 or 6 programmable buttons, using a PiicoDev Adapter for Raspberry Pi/PiicoDev Buttons for easy polling via the I2C bus.<br><br>

**What is this Project?**<br>
This project will give you programable buttons for your **Commodore 64 Ultimate**, super convienient, easily toggle functions of your choice via a quick button press, no more fluffing around in menus! Some examples of the buttons are functions like menu, freeze/reset, lights on & off, speaker on & off, turbo boost and my all personal favourite buttons, party time and mount next disk! Dozens of pre-built functions, easily customisable and extensible, this project will let you do almost anything on your C64U, if paired with the C64-Bridge-Project, you can even send keystrokes to your C64U!<br><br>

> [!NOTE]
> Best used with the C64-Bridge-Project, see https://github.com/brett-olsen/C64-Bridge-Project<br>

<br>

**C64U-btn-HAT Hardware**<br>
1 x Pi Zero 2 W  [(example)](https://core-electronics.com.au/raspberry-pi-zero-2-w-wireless-soldered-male-headers.html)<br>
1 x PiicoDev Adapter for Raspberry Pi https://core-electronics.com.au/piicodev-adapter-for-raspberry-pi.html<br>
n x PiicoDev Button https://core-electronics.com.au/piicodev-button.html (recommend configurations of 3, 4 and 6 buttons)<br>
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
> These instructions assume you already have the C64-Bridge-Project up and running, detailed instructions are located over at:<br>
> https://github.com/brett-olsen/C64-Bridge-Project/blob/main/README.md#getting-it-up--running

<br><br>
**1) Enable I2C**<br>
The PiicoDev buttons and display communicate over I2C, to enable I2CC on your Raspberry PI SSH into your PI, then either:

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
Firstly lets create a project folder, set the permisssions and get everything ready for the project files:

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
With the main daemon downloaded, lets now download the libraries we need for the project, firstly the PiccoDev button support, then the optional libraries for the SSD1306 OLED display:

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
If your wanting to send keystrokes to your Commmodore C64 Ultimate, and have setup the bridge adapter as per the instractions (see https://github.com/brett-olsen/C64-Bridge-Project) then also configure the bridge variables:

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

Finally, we can configure the buttons, there are two button related configurations that need checking, the button ID's and the button mappings (which functions the buttons execcute). The button ID's are set via physical DIP switches (if using the PiicoDev Buttons), you can see the button DIP switch configuration in the first part of the BUTTON MAPPING area in the main c64_button_daemon.py file:
```python
# ==================================================================================================================================
# BUTTON MAPPINGS
#
# Up to 6 buttons are supported (limited by the number of unique 4-bit DIP switch addresses).
# Set each BUTTON(n)_ID to the [sw3,sw2,sw1,sw0] DIP switch position on your physical hardware.
# Set BUTTON(n)ACTION to any action function from the library above, or None to disable that button.
# TODO: Document the exact DIP switch address scheme in the README with a wiring diagram.
# TODO: Confirm the real upper limit on daisy-chained PiicoDev buttons and update this comment (assuming some sort of voltage limit)
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

Finally, you can set the button actions. The default is 3 buttons, the first being menu_button, second speaker_on_off and finally the third being lights_on_off. At the moment, I have tested this project with 3, 4 and 6 buttons, conciveably, you could use any number of buttons depending on the voltage demands. To disable a button, simply set Optional[ActionFn] = None, see the default button configuration below:

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


<br><br>
**4) Configure thing**<br>

