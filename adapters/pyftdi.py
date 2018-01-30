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
# The above copyright is for the ftdi.py code that this is based on. Changes
# are Copyright 2018 S. Goadhouse <sgoadhouse@virginia.edu>
#
#------------------------------------------------------------------------------

import bitstring
from bitstring import BitStream
from adapters.jtag import jtag

import usb
import sys
import struct
import time

import logging
#@@@#from os import environ
from pyftdi.jtag import JtagController, JtagError
#@@@#from pyftdi.bits import BitSequence

class PyFTDIAdapter(jtag):
    """ 
        A JTAG adapter for FTDI-based devices based on the python PyFTDI library and using MPSSE mode.
    """

    def __init__(self, device):
        """
            Create a new FTDI JTAG connection.

            device -- The PyFTDI device to connect to.
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

            tms_stream -- The values to be transmitted over the Test Mode Select (TMS) line.
            tdi_stream -- The values to be transmitted to the target device.
        """
        
        #Create a new bitstream object to store the result of the transmission.
        tdo_stream = BitStream()

        # Although the PyFTDI MPSSE mode is expected to be a
        # significant performance improvement over GPIO mode, it does
        # have an unfortunate complexity with how the TMS signal is
        # handled.
        #
        # The shift: VCD command sends a TMS bit vector and a TDI bit
        # vector of the same size so that each bit of TMS corresponds
        # to each bit of TDI. However, TMS is only needed which
        # changing the JTAG TAP state machine. So the FTDI MPSSE
        # registers only accept up to 7 consecutive settings of TMS
        # with a single TDI bit output for each TMS output.
        #
        # So this will have to be handled by searching for when TMS is
        # a '1', breaking up the bitstring and sending in pieces to
        # the JtagController so that TMS gets handled properly.
        #
        # Also, all of the Jtag functions are written with bits
        # handled through the BitSequence object which appears to make
        # the right-most bit in an array the lsb. This is opposite to
        # the open source bitstring, which is used here and in lots of
        # places. It has the lsb at the left-most bit in the array. So
        # instead of bit swapping again for BitSequence, simply
        # rewrite the worker functions from JtagController to use
        # bitstring and to use different command opcodes to handle
        # bitstrings properly.
        
        
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


    ## This is modified from the one in JtagController object in
    ## PyFTDI. It is modified to handle bitstrings and to use the read
    ## command to read TDI bits during TMS activity.
    def write_tms(self, tms, tdi):
        """ Control the TMS signal with a single bit of TDI """
        if not isinstance(tms, BitStream):
            raise JtagError('Expect TMS to be a BitStream')
        length = len(tms)
        if not (0 < length < 8):
            raise JtagError('Invalid TMS length')
        out = tms + BitArray(8-length) # pad to be a full byte
        # apply TDI to be bit 7 - this TDI will be the same for every clock out of the TMS sequence
        out[7] = tdi
        
        # print("TMS", tms, (self._last is not None) and 'w/ Last' or '')
        cmd = array('B', (Ftdi.WRITE_BITS_TMS_NVE, length-1, out.tobyte()))
        self.device._stack_cmd(cmd)
        self.device.sync()


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


