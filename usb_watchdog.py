# 
# Daniel Johnson  djohnson@progman.us   PGP 0x3CACC85B
# https://github.com/Progman2k/USB_Watchdog
# Licensed under the GPL v3
# 
# This program manages a USB connected watchdog module
# Copyright (C) 2018 Daniel Johnson
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#    
#
# Some code for kernel module management taken from
#    https://stackoverflow.com/a/12543149
# This program is inspired by David Gouveia's work at the following URLs:
#    https://www.davidgouveia.net/2018/02/how-to-create-your-own-script-for-a-usb-watchdog/
#    https://github.com/zatarra/usb-watchdog

# We'll need this if running on Python v2.x
from __future__ import print_function

__version__ = "2018-05-11_01"
__author__ = "Daniel Johnson [djohnson@progman.us] PGP 0x3CACC85B"

#############################################################################

# Used to exit with errorcode on fatal errors
import sys
# Debug output
import logging

def FatalError(message=None):
    """ This displays a text message and forces the program to exit with an error. """
    felogger = logging.getLogger("FatalError")
    # Wrapping this in a 'try' to silence any exceptions we trigger here.
    # This is part of silently quitting when we trap CTRL+C
    try:
        if message:
            # I prefer this format on screen.
            print("\nFATAL ERROR: " + message, file=sys.stderr)
            # Now ensure the console streamhandler will reject this
            # by setting its level too high.
            logging.getLogger().handlers[0].setLevel(logging.CRITICAL)
            felogger.error(message)
        else:
            # Not blocking the console text here, because I consider
            # an undefined issue to be a big issue.
            felogger.error("No descriptive text provided")
        usbcleanup()
    except:
        pass
    sys.exit(1)

# With those modules loaded and function declared we can give a prettier
# error message if any other modules are missing.
try:
    import usb
    # Delays / sleeping between writes
    import time
    # Read local settings file
    if sys.version_info >= (3, 0):
        import configparser
    else:
        # Thankfully the only important difference was capitalization
        import ConfigParser as configparser
    # Access environment variables
    import os
    # Parse command line arguments
    import argparse
    # Identifying errors
    import errno
except Exception as e:
    FatalError("Could not load a required Python module:\n" + repr(e) + "\n\n")

#############################################################################

# From http://code.activestate.com/recipes/496969-convert-string-to-hex/#c1
# Quick way to convert a string to its hexadecimal representation.
# Note this does not prepend "0x".  Example:  toHex("Test") == '54657374'
toHex = lambda x:"".join([hex(ord(c))[2:].zfill(2) for c in x])

#############################################################################

# From https://www.pythoncentral.io/how-to-implement-an-enum-in-python/
def enum(*args):
    # Used to declare an 'enum' dynamically
    enums = dict(zip(args, range(len(args))))
    return type('Enum', (), enums)

#############################################################################

def SendAndReceive(eout, ein, dout):
    # Send a packet and return the USB device's reply as a string
    doutpad=dout.ljust(64,chr(0))
    logging.debug("TX  0x" + toHex(doutpad))
    eout.write(doutpad)
    # A very generous timeout value seems to avoid some very odd behaviors,
    # especially on Windows.
    ret = ein.read(64, 2000)
    din = ''.join([chr(x) for x in ret])
    logging.debug("RX  0x" + toHex(din))
    return din

#############################################################################

def SendAndCompare(eout, ein, dout):
    # Send a packet and expect the USB device to reply with the same packet.
    # If the reply differs that usually seems to indicate a problem.
    doutpad=dout.ljust(64,chr(0))
    din = SendAndReceive(eout, ein, doutpad)
    if doutpad != din:
      logging.warning("Watchdog's response was unexpected.\nTX 0x" + toHex(doutpad) + "\nRX 0x" + toHex(din) + "\n")
    return doutpad == din

#############################################################################

def DrainUSB(ein):
    # Read and discard anything waiting at the USB device.
    # Setting a short timeout period so we don't waste time.
    # Stopping at 256 reads just to prevent infinite loops.
    logging.debug("Trying to drain USB device input buffer")
    try:
        for i in range(0,256):
            tmp = ein.read(1024,10)
            logging.debug("Drained " + len(tmp) + " bytes from USB endpoint")
    except usb.USBError:
        logging.debug("Finished attempts to drain")
        pass

#############################################################################   

def usbinit(USBidVendor, USBidProduct, quiet=False):
    # Returns a tuple of Device, EndpointOut, EndpointIn
    # It is likely (but not certain) that the values we received in our
    # arguments are Strings.  Convert them to integers, which usb.core.find
    # requires.
    if type(USBidVendor) is str:
        USBidVendor = int(USBidVendor,16)
    if type(USBidProduct) is str:
        USBidProduct = int(USBidProduct,16)
    logging.debug('Looking for device with idVendor ' + hex(USBidVendor) + ', idProduct ' + hex(USBidProduct))
    dev = usb.core.find(idVendor=USBidVendor,idProduct=USBidProduct)

    if dev is None:
        raise usb.USBError('Device not found')
    else:
        # We use 'repr(dev)' to get just the ID and bus info rather than
        # the full details that str(dev) would output.
        logging.debug("Watchdog module found: "+repr(dev))

    reattach = False
    try:
        if dev.is_kernel_driver_active(0):
            reattach = True
            logging.debug('Detaching kernel driver')
            dev.detach_kernel_driver(0)
        else:
            logging.debug('Device not claimed by a kernel driver')
    except NotImplementedError:
        # Windows systems may not have a driver that claims it by default
        # Linux systems seem to attach the HID driver as a last resort
        pass

    #dev.reset()
    #time.sleep(0.5)

    # Assume it only has a single 'configuration' and enable it
    dev.set_configuration()
    cfg = dev.get_active_configuration()

    # Get an endpoint instance
    cfg = dev.get_active_configuration()
    intf = cfg[(0,0)]

    epout = usb.util.find_descriptor(
        intf,
        # match the first OUT endpoint
        custom_match = \
        lambda e: \
            usb.util.endpoint_direction(e.bEndpointAddress) == \
            usb.util.ENDPOINT_OUT)

    epin = usb.util.find_descriptor(
        intf,
        # match the first IN endpoint
        custom_match = \
        lambda e: \
            usb.util.endpoint_direction(e.bEndpointAddress) == \
            usb.util.ENDPOINT_IN)

    assert epout is not None
    assert epin is not None

    # Read from the USB device until its buffer is empty.
    # I have no idea if this is actually needed or not.
    DrainUSB(epin)
    return dev, epout, epin

#############################################################################   

def usbcleanup():
    # Clean up as best we can, ignoring _all_ errors but honoring Ctrl+C
    # (Keyboard Interrupt).  Uses the global 'dev'
    global dev
    try:
        if dev != None:
            usb.util.dispose_resources(dev)
    except KeyboardInterrupt:
        raise
    except:
        pass
    time.sleep(0.1)
    try:
        if dev != None:
            dev.reset()
    except KeyboardInterrupt:
        raise
    except:
        pass

#############################################################################
# Begin main code 
#############################################################################

def main():
    # We'll be referencing the existing globally-defined 'dev' variable
    global dev

    # In case we fail to read files for settings, set up defaults here.
    cfgtimer=180
    cfgusbidVendor="0x5131"
    cfgusbidProduct="0x2007"
    cfgquiet=False
    cfgdebug=False

    # Import settings from local configuration file(s) in this order,
    # where values from later files will take precedence over values from
    # earlier files:
    #   /etc/usbwatchdog.ini
    #   C:\usbwatchdog.ini
    #   ~/usbwatchdog.ini  ("~" will be replaced with user's home directory
    #                       on both Linux and Windows)
    # Sample file.  The section name (in square brackets) IS case-sensitive.
    # These are the default values if none are specified.
    # [USBWatchdog]
    # timer=180
    # USBidVendor=0x5131
    # USBidProduct=0x2007
    # quiet=false
    # debug=false
    config = configparser.ConfigParser()
    try:
        config.read(["/etc/usb_watchdog.ini", "C:\\usb_watchdog.ini", os.path.normpath(os.path.expanduser("~/usb_watchdog.ini"))])
        # A missing section or value will throw an error if we don't specify our 'fallback' values
        cfgtimer=config.get('USBWatchdog','timer', fallback=180)
        cfgusbidVendor=config.get('USBWatchdog','USBidVendor',fallback="0x5131")
        cfgusbidProduct=config.get('USBWatchdog','USBidProduct',fallback="0x2007")
        cfgquiet=config.get('USBWatchdog','quiet', fallback=False)
        cfgdebug=config.get('USBWatchdog','debug', fallback=False)
    except:
        pass

    # Import values from command line arguments.  Abbreviations are
    # disabled to avoid accidentally triggering the hidden debug flag.
    argparsedescription="Version " + __version__ + " by " + __author__ + "\nSoftware interface for a type of USB-connected hardware watchdog module.\nLicensed under GPL v3"
    argparseepilog="""
This program is inspired by David Gouveia's work at the following URLs:
  https://www.davidgouveia.net/2018/02/how-to-create-your-own-script-for-a-usb-watchdog/
  https://github.com/zatarra/usb-watchdog

This program only works with USB watchdog modules that present themselves as
an HID (Human Interface Device).  It does not support serial-over-USB devices.

If you don't specify a value this program will assume a 180 second (3 minute)
timer value.  Unless you have tested your computer's boot time (after an
unclear shutdown!) with a stop-watch I strongly advise that you not shorten
that value.

Actual heartbeat packets to the USB module are sent every second, with visual
confirmation by the blinking of the word "Heartbeating".  If that word stops
then so have our heartbeats.  Your USB module may also have an LED that blinks
as valid packets are received.
"""
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
        description=argparsedescription, add_help=False, epilog=argparseepilog)
    # Explicitly defining the help switch just to capitalize the leading 'S' in its text.
    parser.add_argument("-h","--help", action="help", help="Show this help message and exit")
    parser.add_argument("-v","--version", action="version", version=__version__, help="Show program's version number and exit")
    parser.add_argument("timer",  action="store", type=int, default=cfgtimer, nargs="?", help="Watchdog timer value in seconds")
    parser.add_argument("-q","--quiet", action="store_true", default=cfgquiet, help="Silences all output")
    parser.add_argument("-n","--nowarn", action="store_true", default=cfgquiet, help="Do not warn about timer values <120 seconds")
    parser.add_argument("-d","--debug", action="store_true", default=cfgdebug, help="Output verbose debugging information")
    parser.add_argument("-u", "--usbvendor", action="store", type=str, metavar="0x____", default=cfgusbidVendor, help="USB Vendor ID like 0x5131")
    parser.add_argument("-p", "--usbproduct", action="store", type=str, metavar="0x____", default=cfgusbidProduct, help="USB Product ID like 0x2007")
    cliargs = parser.parse_args()

    # Logging hierarchy, for reference
    #   CRITICAL   50
    #   ERROR      40
    #   WARNING    30
    #   INFO       20
    #   DEBUG      10
    #   NOTSET      0
    # We set the logger object to accept Info and above only...
    # (Old format string: '%(name)-8s %(levelname)-8s %(message)s' )
    logging.basicConfig(format='%(levelname)-8s %(message)s',level=logging.INFO)
    # ...then we set its auto-created StreamHandler to Debug and above only.
    logging.getLogger().handlers[0].setLevel(logging.DEBUG)
    # This has the effect of making the logger accept everything but debug by
    # default, but will allow on-screen debug output if enabled later.

    if cliargs.quiet:
        # Setting this to a value never used in the program
        logging.getLogger().setLevel(logging.CRITICAL)

    if cliargs.debug:
        # Enable Debug level (and up) at the root logger
        logging.getLogger().setLevel(logging.DEBUG)

    # Reduce the raw 'seconds' to the 10-second multiple we must send
    timer = int(int(cliargs.timer) / 10)
    if timer < 1:
        logging.error("Timer values under 10 seconds are invalid.\nUsing 180 seconds (3 minutes) instead.")
        timer=18
    if timer < 12 and not cliargs.nowarn:
        logging.warning("Timer values under 120 seconds (2 minutes) are unwise!")
    if timer > 127:
        logging.error("Timer values over 1270 seconds (~21 minutes) are invalid.\nUsing 1200 seconds (20 minutes) instead.")
        timer=18

    logging.debug("Timer value: " + str(timer*10) + " (human)   " + str(timer) + " (internal)   " + hex(timer) + " (internal, hex)")

    State = enum('STARTUP', 'DISCONNECTED', 'CONNECTED')
    laststatus=State.STARTUP
    dev = None
    while True:
        try:
            dev, epout, epin = usbinit(cliargs.usbvendor, cliargs.usbproduct, quiet=cliargs.quiet)
            laststatus=State.CONNECTED
            
            # The Windows client I observed would start by sending 128/0x80 and
            # receive 130/0x82.  Why does this not work for me here?  Using the
            # 'Compare' function to display the return packet during testing...
            # UPDATE: It seems to work fine under Linux, but fails (and creates
            # weird issues) with Python v3.5 under Windows.
            # So is it a Python/PyUSB version problem, or an OS sensitivity?
            # Since there is (so far) no clear benefit to sending 128/0x80
            # should I even bother?
            #SendAndCompare(epout, epin, chr(128))

            # Immediately ensure the timer is not about to expire.  2 minutes
            SendAndCompare(epout, epin, chr(12))
            time.sleep(0.25)

            # Start actual heartbeating with the user's selected value
            logging.info("Setting timer value to " + str(timer*10) + " seconds.")
            HBvisual=True
            while True:
                SendAndCompare(epout, epin, chr(timer))
                if HBvisual:
                    if not cliargs.quiet: print("\rHeartbeating!  ",end="")
                    HBvisual=False
                else:
                    if not cliargs.quiet: print("\r               ",end="")
                    HBvisual=True
                if sys.version_info < (3, 0):
                    sys.stdout.flush()
                time.sleep(1)
        except ValueError as e:
            logging.debug("Encountered ValueError:\n"+repr(e)+"\n")
        except usb.USBError as e:
            etype, evalue, etraceback = sys.exc_info()
            #logging.debug("USBError:\n  type: " + str(etype) + "\n  value: " + str(evalue) + "\n  traceback: " + str(etraceback))
            if evalue.errno == errno.EACCES:
                logging.error("Insufficient permissions to access the device.\nThis is an OS problem you must correct.")
            # Don't bother showing an error if we were still initializing
            if laststatus == State.CONNECTED:
                logging.error("USB communication error or device removed.")
                logging.debug("Encountered USBError:\n"+repr(e)+"\n")
        # Clean up as best we can and try again
        usbcleanup()
        # If our first effort to find the module failed we should give
        # some indication that we are, in fact, trying.
        if laststatus == State.STARTUP:
            logging.info("Waiting for watchdog module to be connected...")
        laststatus=State.DISCONNECTED
        time.sleep(2)


    # Test a range of inputs and show the reply from the module
    #print("Dec\tHex\tReply\tBinary")
    #for x in range(126,256):
        #ret=SendAndReceive(epout, epin, chr(x))
        #rethex=toHex(ret)
        #retbin=bin(int(rethex,16))[2:].zfill(16)
        #print(str(x)+"\t"+hex(x)[:4]+"\t0x"+rethex[:4])
        ##print(str(x)+"\t"+hex(x)+"\t0x"+rethex+"\t"+str(retbin))
        #time.sleep(0.2)

    logging.info("Closing down")

#############################################################################

# If we are being directly sourced and excuted, run main.
# If we were imported into another Python program, do nothing.
if __name__ == "__main__":
    try:
        # In order to help with cleanup of USB connections when quitting,
        # we are going to store the USB device reference as a global.  Here
        # we simply declare it with no value.
        dev=None
        main()
    except KeyboardInterrupt:
        print("\n")
        FatalError("User pressed CTRL+C, aborting...")
    #except Exception as e:
        #FatalError("Exception: " + repr(e))
