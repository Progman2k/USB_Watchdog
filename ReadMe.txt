Daniel Johnson  djohnson@progman.us   PGP 0x3CACC85B
https://github.com/Progman2k/USB_Watchdog
Licensed under the GPL v3

/-------------\
| Quick start |
\-------------/
Ensure you have Python v2.7+ or v3.x installed with the "pyusb" module.  You
may need to add this module with "pip install pyusb" or by using a
distribution-specific command like "yum install pyusb".

Run "python usb_watchdog.py" and connect your watchdog module.  Once it has
been found you will see the work "Heartbeating!" blinking in the console to
confirm successful communication.  Depending on the module you are using,
you may also see a blinking LED on it.

/---------------\
| Which module? |
\---------------/
All development and testing was done with a Yikeshu KMG001, with the
silkscreened mark "USB_WDG_V3.1" near the USB connector and three Chinese
symbols near the button.  I bought the 3-pack from this link:
  https://www.amazon.com/gp/product/B078SRLNXP/

When connected it reports Vendor 0x5131 and Product 0x2007 and presents
itself as an HID, not a serial device.  The software CD contained a
Windows-only driver and program with nothing that identified the
manufacturer/author.

Hopefully even if you get a different 'version' it will be close enough that
this program will work without major changes.

/----------\
| Protocol |
\----------/
For details on the protocol used see "protocol.zip" in this repository, which
contains packet captures from the Windows client and my observations.

/----------\
| Settings |
\----------/
The timer length, VendorID, and ProductID can be set in an INI-style
configuration file or as command-line arguments.  If you don't specify them
reasonable defaults are used (3 minutes, 0x5131, and 0x2007 respectively).

usage: usb_watchdog.py [-h] [-v] [-q] [-n] [-d] [-u 0x____] [-p 0x____] [timer]
  timer                            Watchdog timer value in seconds
  -h, --help                       Show this help message and exit
  -v, --version                    Show program's version number and exit
  -q, --quiet                      Silences all output
  -n, --nowarn                     Do not warn about timer values <120 seconds
  -d, --debug                      Output verbose debugging information
  -u 0x____, --usbvendor 0x____    USB Vendor ID like 0x5131
  -p 0x____, --usbproduct 0x____   USB Product ID like 0x2007

The program looks for the INI file in these locations:
  /etc/usb_watchdog.ini
  C:\usb_watchdog.ini
  ~/usb_watchdog.ini   (on both Linux and Windows, this is your home directory)

/-----------------------------------------\
| A word of WARNING about the Timer value |
\-----------------------------------------/
The module itself operates on multiples of 10 seconds.  If the timer expires
and the watchdog reboots, the timer RESTARTS without waiting for communication
with this program.  Thus if your computer does not POST, boot, check its
disks, and start this program within your specified time the watchdog timer
will expire AGAIN and trigger another reboot.  If you had also connected the
Power button pins then this second reboot may be sent as "holding down the
button".

If you don't specify a value this program will assume a 180 second (3 minute)
timer value.  Unless you have tested your computer's boot time (after an
unclear shutdown!) with a stop-watch I strongly advise that you not shorten
that value.
