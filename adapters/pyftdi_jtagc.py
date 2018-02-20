# Copyright (c) 2010-2016, Emmanuel Blot <emmanuel.blot@free.fr>
# Copyright (c) 2016, Emmanuel Bouaziz <ebouaziz@free.fr>
# All rights reserved.
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

#------------------------------------------------------------------------------
# The above copyright is for the jtag.py code from the PyFTDI python
# library that this is heavily based on. Changes are Copyright 2018
# S. Goadhouse <sgoadhouse@virginia.edu>
#
# There are several reasons for creating a custom JtagController and
# not using the one that is a part of the PyFTDI library.
#
# 1. PyFTDI does not yet fully support its JTAG interface and its API
#    is not documented. So it is possible that this unreleased JTAG
#    API may change in the future. In order to make the interface to
#    the FTDI MPSSE registers stable, I will create my own
#    JtagController.
#
# 2. The original Jtag code fomr PyFTDI used the supplied BitSequence
#    python library for bit handling. The original xvcd_server code
#    uses the bitstring library. The two have different bit
#    orderings. Although I astechically prefer BitSequence bit
#    ordering (right-most is lsb), the xvcd_server code already uses
#    bitstring with its left-most bit is lsb bit ordering. Also
#    bitstring is used by other python projects. So some of the code
#    changes here are to port to using bitstring.
#
# 3. xvcd_server has a very simplisitic interface to JTAG. The engine
#    is handled by Xilinx software and simply tells xvcd_server what
#    bits to shift in. Because of thes elower level needs, being able
#    to custom hone code for my needs made sense.
#
#------------------------------------------------------------------------------

import time
from os import environ
from sys import modules, stdout
from array import array
from pyftdi.ftdi import Ftdi
from pyftdi import FtdiLogger
from threading import Lock
import logging

from bitstring import BitStream, BitArray, Bits

class JtagError(Exception):
    """Generic JTAG error"""

class JtagController:
    """JTAG master of an FTDI device"""

    TCK_BIT = 0x01   # FTDI output
    TDI_BIT = 0x02   # FTDI output
    TDO_BIT = 0x04   # FTDI input
    TMS_BIT = 0x08   # FTDI output
    TRST_BIT = 0x10  # FTDI output, not available on 2232 JTAG debugger
    JTAG_MASK = 0x1f

    # FTDI write and read FIFO byte lengths
    FTDI_WRITE_PIPE_LEN = 0
    FTDI_READ_PIPE_LEN = 0
    
    FTDI_WR_BUFFER_MAX_LEN = 0 # maximum byte length of write data to FTDI
    FTDI_RD_BUFFER_MAX_LEN = 0 # maximum byte length of read data from FTDI
    
    # Private API
    def __init__(self, trst=False, frequency=3.0E6, usb_read_timeout=5000, usb_write_timeout=5000, debug=False):
        """
        trst uses the nTRST optional JTAG line to hard-reset the TAP
          controller
        """
        self._ftdi = Ftdi()
        self._lock = Lock()
        self._ftdi.timeouts = (usb_read_timeout, usb_write_timeout)
        self._trst = trst
        self._frequency = frequency
        self._ftdi_opened = False
        self._immediate = bytes((Ftdi.SEND_IMMEDIATE,))
        self.direction = (JtagController.TCK_BIT |
                          JtagController.TDI_BIT |
                          JtagController.TMS_BIT |
                          (self._trst and JtagController.TRST_BIT or 0))
        # all JTAG outputs are low - Additionally, setting this upper
        # bits as outputs and then having a specific initial value
        # gets the PYNQ-Z1 board working
        self.direction |= 0x90
        self.initialout = 0xe0  
        #@@@#self.initialout = self.direction
        self._last = None  # Last deferred TDO bit
        self._write_buff = array('B')
        self._debug = debug
        
    # Public API
    def configure(self, url):
        """Configure the FTDI interface as a JTAG controller"""
        print('Configure with Freq: {}'.format(self._frequency))

        if (self._debug):
            FtdiLogger.log.addHandler(logging.StreamHandler(stdout))
            #@@@#level = environ.get('FTDI_LOGLEVEL', 'info').upper()
            level = 'DEBUG'
            try:
                loglevel = getattr(logging, level)
            except AttributeError:
                raise ValueError('Invalid log level: %s', level)
            FtdiLogger.set_level(loglevel)

        print('Opening MPSSE:  direction ("1" is out): 0x{:02x}  Initial Output: 0x{:02x}'.format(self.direction, self.initialout))

        with self._lock:
            self._ftdi.open_mpsse_from_url(
                url, direction=self.direction, frequency=self._frequency, debug=self._debug, latency=12) # @@@@@
            self._ftdi_opened = True

            # FTDI requires to initialize all GPIOs before MPSSE kicks in
            cmd = array('B', (Ftdi.SET_BITS_LOW, self.initialout, self.direction))
            self._ftdi.write_data(cmd)

            # Read the FIFO sizes and save them
            (self.FTDI_WRITE_PIPE_LEN, self.FTDI_READ_PIPE_LEN) = self._ftdi.fifo_sizes

            # Set the FTDI read/write chunksizes to be the same as the FTDI FIFO lengths
            self._ftdi.write_data_set_chunksize(self.FTDI_WRITE_PIPE_LEN)
            self._ftdi.read_data_set_chunksize(self.FTDI_READ_PIPE_LEN)

            # "-3" on self.FTDI_WRITE_PIPE_LEN accounts for the command
            # byte plus 2 length bytes which must also fit in the WRITE
            # FIFO.
            self.FTDI_WR_BUFFER_MAX_LEN = self.FTDI_WRITE_PIPE_LEN-3

            # "-2" on self.FTDI_READ_PIPE_LEN accounts for the two status
            # bytes, even though they are not returned by the FTDI
            # read_bytes function. They are still taking up space in the
            # FTDI's READ FIFO.
            self.FTDI_RD_BUFFER_MAX_LEN = self.FTDI_READ_PIPE_LEN-2


    def close(self):
        if self._ftdi_opened:
            self._ftdi.close()
            self._ftdi_opened = False

    def set_frequency(self, frequency):
        # Configure clock
        self._frequency = frequency

        print('FTDI USB Timeouts: read={} write={}'.format(self._ftdi.timeouts[0], self._ftdi.timeouts[1]))
        print('FTDI USB Fifo Len: read={} write={}'.format(self.FTDI_READ_PIPE_LEN, self.FTDI_WRITE_PIPE_LEN))

        return self._ftdi.set_frequency(self._frequency)

    @property
    def max_byte_sizes(self):
        """Return the 3-tuple of maximum bytes from (TMS, TDI (output) and TDO (input))

           :return: 3-tuple of write, read buffer sizes in bytes
           :rtype: tuple(int, int)
        """
        ## Make the TMS buffer size the same as TDI which is the WRITE
        ## Buffer size. Since only send the TMS bits that are '1',
        ## essentially, this size doe snot really matter since Python
        ## will handle it.
        return (self.FTDI_WR_BUFFER_MAX_LEN, self.FTDI_WR_BUFFER_MAX_LEN, self.FTDI_RD_BUFFER_MAX_LEN)

    def purge(self):
        self._ftdi.purge_buffers()

    ## Write out the data and clear the internal buffer for more data
    def sync(self):
        if not self._ftdi:
            raise JtagError("FTDI controller terminated")
        if self._write_buff:
            try:
                with self._lock:
                    self._write_buff.extend(self._immediate)
                    self._ftdi.write_data(self._write_buff)
                    self._write_buff = array('B')
            except usb.core.USBError:
                pass            # FTDI should be catching the error

    # Concatenate cmd bytes. If cmd > Write FIFO size, write data and
    # clear cmd array so more bytes can be added (which will need to
    # be sent with a sync() outside of this function)
    def _stack_cmd(self, cmd):
        if not isinstance(cmd, array):
            raise TypeError('Expect a byte array')
        if not self._ftdi:
            raise JtagError("FTDI controller terminated")
        # Currrent buffer + new command + send_immediate
        if (len(self._write_buff)+len(cmd)+1) >= self.FTDI_WRITE_PIPE_LEN:
            self.sync()
        self._write_buff.extend(cmd)


    def write_tms_tdi_read_tdo(self, tms, tdi):
        """Write out TMS bits while holding TDI constant and reading back in TDO"""
        if not (isinstance(tms, BitStream) or isinstance(tms, BitArray)):
            raise JtagError('Expect a BitStream or BitArray')
        length = len(tms)
        if not (0 < length < 8):
            raise JtagError('Invalid TMS length')
        tms.reverse()           # must reverse bits since only lsb write seems to be supported
        tms.prepend(8-len(tms)) # prepend 0's to be 8 bits long

        # left-most bit will be for TDI
        if isinstance(tdi, BitStream) or isinstance(tdi, BitArray):
            tms[0] = tdi[0]
        elif isinstance(tdi, bool):
            tms[0] = tdi            
        else:
            raise JtagError('Incorrect type for tdi - must be BitStream, BitArray or bool')
        
        # apply the last TDI bit
        #@@@if self._last is not None:
        #@@@    out[7] = self._last
        # print("TMS", tms, (self._last is not None) and 'w/ Last' or '')
        # reset last bit
        #@@@self._last = None

        ## Send the byte to the FTDI
        cmd = array('B', (Ftdi.RW_BITS_TMS_PVE_NVE, length-1, tms.uint))
        self._stack_cmd(cmd)
        self.sync()

        ## Read the response from FTDI
        data = self._ftdi.read_data_bytes(1, 4)
        if (len(data) != 1):
            raise JtagError('Not all data read! Expected {} bytes but only read {} bytes'.format(1,len(data)))

        tdo = BitArray(data)

        # FTDI handles returned LSB bit data by putting the first bit
        # in bit 7 and shifting to the right with every new bit. So
        # the first bit clocked will be in the lowest bit number, but
        # which bit number it will be in depends on how many bits
        # clocked. [It is kinda stupid, if you ask me. I think the bit
        # order should be the same as tehe bit written, but they
        # aren't.]
        tdo = tdo[:length]
        
        # return to bitstring bit ordering with left-most bit the lsb
        tdo.reverse()
        return tdo

    def write_tdi_read_tdo(self, out, use_last=False):
        """ Output a sequence of bits to TDI while reading the TDO input bits. Automatically break any byte writes based on adapter FIFO sizes. """

        if not (isinstance(out, BitStream) or isinstance(out, BitArray)):
            raise JtagError('Expect a BitStream or BitArray')

        ## @@@ Not used at the moment
        #if use_last:
        #    #(out, self._last) = (out[:-1], bool(out[-1]))
        #    self._last = out[-1]

        byte_count = out.len//8
        pos = 8*byte_count
        bit_count = out.len-pos

        # Separate into BYTE and BIT commands
        tdo = BitArray()
        if byte_count:
            ## Since TDO bit length will be equal to TDI bit length,
            ## set max_rw_bits to the minimum of the TDI or TDO bit
            ## sizes.
            max_rw_bits = min(self.max_byte_sizes[1:3])*8

            # Start head and tail at the beginning bit index
            head = 0
            tail = 0

            #@@@while(tdo.len//8 < byte_count):
            while(head < pos):
                # Set tail to either be the maximum bytes to
                # read/write or the final bit, pos, whichever is
                # smaller. These are bit indexes.
                tail = min((head+max_rw_bits),pos)
                tdo += self._write_read_bytes(out[head:tail])
                head = tail

        if bit_count:
            # Do not have to deal with bit length here because already know bit_count is b/w 0 and 7
            tdo += self._write_read_bits(out[pos:])

        return tdo

    def _write_read_bits(self, out):
        """Output bits on TDI while reading TDO bits in"""

        # a bitstring.BitStream() has first bit in left-most array position (ie. msb first)
        length = out.len
        byte = BitArray(out)    # copy out so can modify it
        byte.append(8-length)   # pad 0's to be 8 bits long

        # Check number of bits.
        if not (0 < length <= 8):
            raise JtagError('Wrong number of bits: {}'.format(length))

        #@@@#print('out: ', out, 'length: ', length, 'byte: ', byte, 'byte as uint: ', byte.uint)
        
        # length of 0 for 1 bit, length of 7 for 8 bits, etc.
        cmd = array('B', (Ftdi.RW_BITS_PVE_NVE_MSB, length-1, byte.uint))

        #@@@#print('cmd: ', cmd)
        
        self._stack_cmd(cmd)
        self.sync()
        
        data = self._ftdi.read_data_bytes(1, 4)
        if (len(data) != 1):
            raise JtagError('Not all data read! Expected {} bytes but only read {} bytes'.format(1,len(data)))

        tdo = BitArray(data)

        # Only pass back the same number of bits as clocked
        # out. Although MSB, a MSB bit read left shifts the bits
        # starting at bit 0. So it is right shifted MSB from reads by
        # left shifted MSB on bit writes. (Go Fugure?)
        tdo = tdo[8-length:]
        return tdo

    def _write_read_bytes(self, out):
        """Output bytes on TDI while reading TDO bits in"""

        # a bitstring.BitStream() has first bit in left-most array position (ie. msb first)
        bytes_ = out.bytes
        
        olen = len(bytes_)
        #print("WRITE {} BYTES: 0x{}".format(olen, bytes_.hex()))
        #print("WRITE {} BYTES".format(olen))

        # Check number of bits.
        #
        # If this function was a write-only function, could smartly
        # handle writing more bytes than will fit into the write FIFO
        # by sending them in waves. However, this function writes and
        # reads the same number of bytes. So the byte length of the
        # out vector must be less than the size of both the Write and
        # Read FIFO.
        #
        # What's more, when writing, also need to write a command byte
        # and two length bytes. So account for them as well so that
        # the entire write will fit in the Write FIFO. This makes it
        # so that there is a USB read for every USB write. May not be
        # completely necessary but seems to be a little more
        # efficient.
        #
        if olen > self.FTDI_RD_BUFFER_MAX_LEN:
            raise JtagError("Byte length of Read data ({}) is larger than Read buffer ({})".format(olen, self.FTDI_RD_BUFFER_MAX_LEN))
        if olen > self.FTDI_WR_BUFFER_MAX_LEN:
            raise JtagError("Byte length of Write data ({}) is larger then Write Buffer ({})".format(olen, self.FTDI_WR_BUFFER_MAX_LEN))

        # The byte length to pass to the MPSSE is -1 the actual length, LSB first
        cmd = array('B', (Ftdi.RW_BYTES_PVE_NVE_MSB, (olen-1) & 0xff,
                          ((olen-1) >> 8) & 0xff))
        cmd.extend(bytes_)
        self._stack_cmd(cmd)
        self.sync()

        data = self._ftdi.read_data_bytes(olen, 4)
        if (len(data) != olen):
            raise JtagError('Not all data read! Expected {} bytes but only read {} bytes'.format(olen,len(data)))

        #print("READ {} BYTES:  0x{}".format(len(data), data.tobytes().hex()))
        #print("READ {} BYTES".format(len(data)))

        return BitArray(data)


