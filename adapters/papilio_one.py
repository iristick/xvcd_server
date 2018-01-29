#------------------------------------------------------------------------------
# Copyright 2014 Kyle J. Temkin <ktemkin@binghamton.edu>
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
#
#------------------------------------------------------------------------------
# Original copyright is above and still holds. Core of this file is
# the same but it was ported to use PyFTDI python libraries instead of
# libftdi. Code port is Copyright 2018 S. Goadhouse <sgoadhouse@virginia.edu>
#------------------------------------------------------------------------------

import logging
from os import environ
import atexit

from bitstring      import BitStream
from adapters.jtag  import jtag
from adapters.pyftdi_gpio  import PyFTDIGPIOAdapter

from pyftdi.gpio import GpioController, GpioException


class PapilioOne(PyFTDIGPIOAdapter):
    """ 
        A JTAG adapter for Papilio One devices ported to use PyFTDI python library instead of libftdi.
    """

    #VID/PID constants.
    VENDOR_ID  = 0x0403
    PRODUCT_ID = 0x0610
   
    #Port-number constants.
    TCK_PORT = 0
    TDI_PORT = 1
    TDO_PORT = 2
    TMS_PORT = 3

    DEFAULT_FREQ = int(1e6)
    FTDI_URL = 'ftdi://0x{:04x}:0x{:04x}/1'.format(VENDOR_ID, PRODUCT_ID)

    def __init__(self, serial_number=None):
        """
            Create a new instance of the Papilio One.

            serial_number -- The serial number of the board to connect to, or None to use
                             the first available bitbangable FTDI. Use caution with this one!
                             NOTE: This is IGNORED.
        """

	# Instead of using BitBangDevice(), use GpioController() from PyFTDI
        self._gpio = GpioController()

        # If FTDI_DEVICE environment variable, use it instead of self.FTDI_URL
        url = environ.get('FTDI_DEVICE', self.FTDI_URL)

        # Open the PyFTDI URL with outputs set as per set_up_jtag_port()
        self._gpio.open_from_url(url, direction=self.set_up_jtag_port())

        atexit.register(self.cleanup)
        
        #Initiatialize the core JTAG subsystem.
        super().__init__(self._gpio)


    def cleanup(self):
        print("Running PyFTDI GPIO cleanup...")
        self._gpio.close()
        

    def set_tck_period(self, period):
        """
            Handle the settck virtual cable command which requests a certain TCK period. Return the actual period.
        """

        #@@@# Modify to actually change frequency using PyFTDI functions.
        
        ## Actual Period depends on many factors since this tries to simply go as fast as it can. So nothing to set. Respond that it goes at 100 Hz or 10e6 ns
        return int(1e9//self.DEFAULT_FREQ)
        
    def set_up_jtag_port(self):
        direction = 0
        direction |=  (1 << self.TCK_PORT);
        direction |=  (1 << self.TDI_PORT);
        direction |=  (1 << self.TMS_PORT);
        direction &= ~(1 << self.TDO_PORT);
        return direction
    
    def set_tms(self, value, commit=True):
        """
            Specifies the value of the TMS port. Used by the parent class.
        """
        self._set_bit(self.TMS_PORT, value, commit);


    def set_tdi(self, value, commit=True):
        """
            Specifies the value of the TDI port. Used by the parent class.
        """
        self._set_bit(self.TDI_PORT, value, commit);


    def set_tck(self, value, commit=True):
        """
            Specifies the value of the TCK port. Used by the parent class.
        """
        self._set_bit(self.TCK_PORT, value, commit);


    def get_tdo(self):
        """
            Reads the current value of the TDO port. Used by the parent class.
        """
        return self._get_bit(self.TDO_PORT)


# General name of class for server
jtag_adapter = PapilioOne
