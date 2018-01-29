#------------------------------------------------------------------------------
# Copyright 2018 S. Goadhouse <sgoadhouse@virginia.edu>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#------------------------------------------------------------------------------

#@@@#import usb
import bitstring
from bitstring      import BitStream
from adapters.jtag  import jtag
from adapters.pyftdi_gpio  import PyFTDIGPIOAdapter

import logging
from os import environ
#@@@#from pyftdi.jtag import JtagEngine
#@@@#from pyftdi.bits import BitSequence
from pyftdi.gpio import GpioController, GpioException

# package.py
import atexit

class FT4232H_GPIO(PyFTDIGPIOAdapter):
    """ 
        A JTAG adapter using a FTDI FT4232H-based interface but bit-banging through GPIO interface.
        This exists only to compare against original libftdi GPIO method before coding the MPSSE method.
    """

    #VID/PID constants.
    #@@@#VENDOR_ID  = 0x0403
    #@@@#PRODUCT_ID = 0x0610
   
    #Port-number constants.
    TCK_PORT = 0
    TDI_PORT = 1
    TDO_PORT = 2
    TMS_PORT = 3

    DEFAULT_FREQ = int(1e6)
    FTDI_URL = 'ftdi://ftdi:4232h/1'

    def __init__(self, serial_number=None):
        """
            Create a new instance of the FT4232H.

            @@@ Add ability to set which port to use

            @@@ serial_number -- The serial number of the board to connect to, or None to use
                             the first available bitbangable FTDI. Use caution with this one!
        """

        # set up outputs (1=Output, 0=Input)
        out_pins = (1 << self.TCK_PORT) 
        out_pins |= (1 << self.TDI_PORT) 
        out_pins |= (1 << self.TMS_PORT) 
        
        self._gpio = GpioController()
        url = environ.get('FTDI_DEVICE', self.FTDI_URL)
        self._gpio.open_from_url(url, direction=out_pins)

        atexit.register(self.cleanup)
        
        #Initiatialize the core JTAG subsystem.
        super().__init__(self._gpio)


    def cleanup(self):
        print("Running cleanup...")
        self._gpio.close()
        

    def set_tck_period(self, period):
        """
            Handle the settck virtual cable command which requests a certain TCK period. Return the actual period.
        """

        #@@@# Modify to actually change frequency using PyFTDI functions.
        
        ## Actual Period depends on many factors since this tries to simply go as fast as it can. So nothing to set. Respond that it goes at 100 Hz or 10e6 ns
        return int(1e9//self.DEFAULT_FREQ)
        

    def set_tms(self, value):
        """
            Specifies the value of the TMS port. Used by the parent class.
        """
        self._set_gpio(self.TMS_PORT, value);


    def set_tdi(self, value):
        """
            Specifies the value of the TDI port. Used by the parent class.
        """
        self._set_gpio(self.TDI_PORT, value);


    def set_tck(self, value):
        """
            Specifies the value of the TCK port. Used by the parent class.
        """
        self._set_gpio(self.TCK_PORT, value);


    def get_tdo(self):
        """
            Reads the current value of the TDO port. Used by the parent class.
        """
        return self._get_gpio(self.TDO_PORT)

# General name of class for server
jtag_adapter = FT4232H_GPIO
