
<img width="1200" height="640" alt="Project-Image" src="https://github.com/user-attachments/assets/30421d25-9df7-4f5d-a61b-83e5f06f6bf2" />


# C64U-btn-HAT

A button HAT for the Raspberry Pi Zero W 2 + Commodore 64 Ultimate, providing 3,4 or 6 programmable buttons, using a PiicoDev Adapter for Raspberry Pi/PiicoDev Buttons for easy polling via the I2C bus.<br><br>

**What is this Project?**<br>
This project will give you programable buttons for your **Commodore 64 Ultimate**, super convienient, easily toggle functions of your choice via a quick button press, no more fluffing around in menus! My personal fav buttons are menu, freeze/reset, lights on & off, speaker on & off, turbo boost and my favourite buttons, party time and load next disk! Dozens of pre-built functions, easily customisable and extensible, this project will let you do almost anything on your C64U, if paired with the C64-Bridge-Project, you can even send keystrokes to your C64U!<br><br>

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

# Getting it up & running<br><br>

> [!NOTE]
> These instructions assume you already have the C64-Bridge-Project up and running, detailed instructions at:<br>
> https://github.com/brett-olsen/C64-Bridge-Project/blob/main/README.md#getting-it-up--running

<br><br>
**1) Enable I2C**<br>
The PiicoDev buttons and display communicate over I2C, to enable I2CC on your Raspberry PI, either:

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

<br><br>
**3) Configure thing**<br>

<br><br>
**4) Configure thing**<br>

