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

import usb
import bitstring
from bitstring      import BitStream
from adapters.jtag  import jtag
from adapters.ftdi  import FTDIAdapter
from pylibftdi      import BitBangDevice


class PapilioOne(FTDIAdapter):
    """ 
        A JTAG adapter for Papilio One devices.
    """

    #VID/PID constants.
    VENDOR_ID  = 0x0403
    PRODUCT_ID = 0x0610
   
    #Port-number constants.
    TCK_PORT = 0
    TDI_PORT = 1
    TDO_PORT = 2
    TMS_PORT = 3
   

    def __init__(self, serial_number=None):
        """
            Create a new instance of the Papilio One.

            serial_number -- The serial number of the board to connect to, or None to use
                             the first available bitbangable FTDI. Use caution with this one!
        """
        
        device = BitBangDevice(serial_number)
        self.set_up_jtag_port(device);

        #Initiatialize the core JTAG subsystem.
        super().__init__(device)


    def set_up_jtag_port(self, device):
        device.direction |=  (1 << self.TCK_PORT);
        device.direction |=  (1 << self.TDI_PORT);
        device.direction |=  (1 << self.TMS_PORT);
        device.direction &= ~(1 << self.TDO_PORT);

    
    def set_tms(self, value):
        """
            Specifies the value of the TMS port. Used by the parent class.
        """
        self._set_bit(self.TMS_PORT, value);


    def set_tdi(self, value):
        """
            Specifies the value of the TDI port. Used by the parent class.
        """
        self._set_bit(self.TDI_PORT, value);


    def set_tck(self, value):
        """
            Specifies the value of the TCK port. Used by the parent class.
        """
        self._set_bit(self.TCK_PORT, value);


    def get_tdo(self):
        """
            Reads the current value of the TDO port. Used by the parent class.
        """
        return self._get_bit(self.TDO_PORT)
        

# General name of class for server
jtag_adapter = PapilioOne
