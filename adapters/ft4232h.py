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

from os import environ
import atexit

from bitstring              import BitStream
from adapters.jtag          import jtag
from adapters.pyftdi        import PyFTDIAdapter

from adapters.pyftdi_jtagc  import JtagController, JtagError


class FT4232H(PyFTDIAdapter):
    """ 
        A JTAG adapter using a FTDI FT4232H-based interface in MPSSE mode.
    """

    MAX_FREQ = 1.0e6
    FTDI_URL = 'ftdi://ftdi:4232h/1'

    def __init__(self, debug=False):
        """
            Create a new instance of the FT4232H.

            @@@ Add ability to set which port to use

        """

        ## Getting USB Timeout errors, try 10000 ms for both
        self._jtag = JtagController(trst=False, frequency=self.MAX_FREQ, debug=debug, usb_read_timeout=10000, usb_write_timeout=10000)
		
        # If FTDI_DEVICE environment variable, use it instead of self.FTDI_URL
        url = environ.get('FTDI_DEVICE', self.FTDI_URL)
		
        # Open the PyFTDI URL configured for MPSSE JTAG
        self._jtag.configure(url)
        #@@@#device.reset()
		
        atexit.register(self.cleanup)
        
        #Initiatialize the core JTAG subsystem.
        super().__init__(self._jtag)


    def cleanup(self):
        print("Running PyFTDI JTAG cleanup...")
        self._jtag.close()
        

    def set_frequency(self, frequency):
        """
            Set the TCK Frequency
        """

        frequency = min(frequency, self.MAX_FREQ)
        actualFreq = self._jtag.set_frequency(frequency)

        return actualFreq

    def set_tck_period(self, period):
        """
            Handle the settck virtual cable command which requests a certain TCK period. Return the actual period.
        """

        return int(1e9/self.set_frequency(1e9/period))


# General name of class for server
jtag_adapter = FT4232H
