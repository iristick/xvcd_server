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

import bitstring
from bitstring import BitStream
from adapters.jtag import jtag

from pylibftdi import BitBangDevice


import usb
import sys
import struct
import time

class FTDIAdapter(jtag):
    """ 
        A JTAG adapter for FTDI-based devices.
    """

    def __init__(self, device):
        """
            Create a new FTDI JTAG connection.

            device -- The pylibfti BitBangDevice to connect to.
        """
        
        #Initiatialize the core JTAG subsystem.
        super().__init__()

        #... and store the newly created device.
        self.device = device

        #Create a copy of the instruction register for this device.
        #self.ir = bitstring.BitStream('0b000000')

    def set_verbosity(self, level):
        """
            Sets the verbosity level, as per the command line.
        """
        self.verbosity_level = level


    def set_tck_period(self, period):
        """
            Handle the settck virtual cable command which requests a certain TCK period. Return the actual period.
        """

        ## Actual Period depends on many factors since this tries to simply go as fast as it can. So nothing to set. Respond that it goes at 100 Hz or 10e6 ns
        return int(10e6)


    #def jtag_general(self, tms_stream, tdi_stream):
    def send_data(self, tms_stream, tdi_stream):
        """
            Performs a general-purpose JTAG communication.

            tms_stream -- The values to be transmitted over the Test Most Select (TMS) line.
            tdi_stream -- The values to be transmitted to the target device.
        """
        
        #Create a new bitstream object to store the result of the transmission.
        tdo_stream = BitStream()

        #For each simulatenous pair of bits in the transmission...
        for (tms, tdi) in zip(tms_stream, tdi_stream):

            #...perform the core transmission...
            tdo = self.tick(tms, tdi)

            #... and add the result to our resultant stream.
            tdo_stream += BitStream(bool=tdo)

            #Track where we are the JTAG state machine, in case TMS changes.
            self.track_tms(tms)

        #... return the values returned over TDO.
        return tdo_stream


    def tick(self, tms, tdi, clock_delays = 0):
        """
            Sets the values of the TMS and TDI lines for a single cycle of JTAG communication,
            and samples TDO at the appropriate time.

            tms: The value of TMS.
            tdi: The value of TDI.
        """

        #Apply a falling edge of the clock.
        self.set_tck(0)

        #... and adjust our output values.
        self.set_tms(tms)
        self.set_tdi(tdi)

        #If requested, wait.
        if clock_delays:
            time.sleep(clock_delay);

        #Apply a rising edge, and sample the input.
        self.set_tck(1);
        tdo = self.get_tdo()

        #If requested, wait.
        if clock_delays:
            time.sleep(clock_delay);

        if (self.verbosity_level >= 3):
            print("{0}, {1}, {2}".format(1 if tdi else 0, 1 if tdo else 0, 1 if tms else 0))

        #Return the value of TDO.
        return tdo


    def set_program(self, value):
        """
            Set the value of the program pin. This will need to be designed on
            a frontend basis, where supported.
        """
        pass

    def reset(self):
        """
            Reset the target device, where supported.
        """
        pass


    def _set_bit(self, bit_number, value=1):
        """
            Sets a single bit of the FTDI bit-bang port.

            bit_number: The bit number of the port to set.
            value: The value to set-- should be 0 or 1 (or equivalent truth values).
        """
        if value:
            self.device.port |=  (1 << bit_number)
        else:
            self.device.port &= ~(1 << bit_number)


    def _get_bit(self, bit_number):
        """
            Reads a given bit of the FTI bit-bang port.

            bit_number: The bit number of the port to read.
        """
        return 1 if (self.device.port & (1 << bit_number)) else 0


