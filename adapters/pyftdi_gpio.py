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


class PyFTDIGPIOAdapter(jtag):
    """ 
        A JTAG adapter for FTDI-based devices based on the python PyFTDI library and using GPIO mode.
        This primarily exists to compare against the original libftdi method which was GPIO only.
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

        self._state = 0  # SW cache of the GPIO output lines
        
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

    @property
    def max_byte_sizes(self):
        """Return the 3-tuple of maximum bytes from (TMS, TDI (output) and TDO (input))

           :return: 3-tuple of write, read buffer sizes in bytes
           :rtype: tuple(int, int)
        """

        # This is limited by Python which is almost unlimited, so set it to reasonable values
        return (2048, 2048, 2048)

    #def jtag_general(self, tms_stream, tdi_stream):
    def send_data(self, tms_stream, tdi_stream):
        """
            Performs a general-purpose JTAG communication.

            tms_stream -- The values to be transmitted over the Test Mode Select (TMS) line.
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

        # Apply a falling edge of the clock
        self.set_tck(False, commit=False) # wait to commit all output changes together

        # ... and adjust our output values.
        self.set_tms(tms, commit=False) # wait to commit all output changes together)
        self.set_tdi(tdi, commit=True)  # Now commit all three output changes simulataneously

        #If requested, wait.
        if clock_delays:
            time.sleep(clock_delay);

        #Apply a rising edge, and sample the input.
        self.set_tck(True);
        tdo = self.get_tdo()

        #If requested, wait.
        if clock_delays:
            time.sleep(clock_delay);

        if (self.verbosity_level >= 4):
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

    def _set_bit(self, line, on, commit=True):
        """ Convenience function so papilio_one.py had to change minimimally """
        self._set_gpio(line, on, commit)
    

    def _get_bit(self, line):
        """ Convenience function so papilio_one.py had to change minimimally """
        return self._get_gpio(line)

    #
    # NOTE _set_gpio(), _get_gpio() and _commit_state() all come from
    # the GPIO test code from the PyFTDI distribution. Modified
    # slightly so that _commit_state is optionally called. Original
    # copyright statement follows:    
    #
    # Copyright (c) 2016-2017, Emmanuel Blot <emmanuel.blot@free.fr>
    # All rights reserved.
    #
    # Redistribution and use in source and binary forms, with or without
    # modification, are permitted provided that the following conditions are met:
    #     * Redistributions of source code must retain the above copyright
    #       notice, this list of conditions and the following disclaimer.
    #     * Redistributions in binary form must reproduce the above copyright
    #       notice, this list of conditions and the following disclaimer in the
    #       documentation and/or other materials provided with the distribution.
    #     * Neither the name of the Neotion nor the names of its contributors may
    #       be used to endorse or promote products derived from this software
    #       without specific prior written permission.
    #
    # THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
    # AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
    # IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
    # ARE DISCLAIMED. IN NO EVENT SHALL NEOTION BE LIABLE FOR ANY DIRECT, INDIRECT,
    # INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
    # LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
    # OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
    # LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
    # NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
    # EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
    
    def _set_gpio(self, line, on, commit=True):
        """Set the level of a GPIO output pin.
        
        :param line: specify which GPIO to modify.
        :param on: a boolean value, True for high-level, False for low-level
        """
        if on:
            state = self._state | (1 << line)
        else:
            state = self._state & ~(1 << line)

        if commit:
            self._commit_state(state)
        else:
            self._state = state

    def _get_gpio(self, line):
        """Retrieve the level of a GPIO input pin

           :param line: specify which GPIO to read out.
           :return: True for high-level, False for low-level
        """
        value = self._gpio.read_port()
        return bool(value & (1 << line))

    def _commit_state(self, state):
        """Update GPIO outputs
        """
        self._gpio.write_port(state)
        # do not update cache on error
        self._state = state

