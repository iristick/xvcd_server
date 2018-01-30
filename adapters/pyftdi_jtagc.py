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
from array import array
from pyftdi.ftdi import Ftdi

#@@@# Will go away once the port is complete
from pyftdi.bits import BitSequence

from bitstring import BitStream, BitArray

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
    FTDI_PIPE_LEN = 512

    MAX_WRITE_BYTES = 65536     # a property of the FTDI MPSSE but not defined in PyFTDI
    RW_BITS_PVE_NVE_MSB = 0x33  # MPSSE command not defined in PyFTDI
    RW_BITS_NVE_PVE_MSB = 0x36  # MPSSE command not defined in PyFTDI
    
    # Private API
    def __init__(self, trst=False, frequency=3.0E6):
        """
        trst uses the nTRST optional JTAG line to hard-reset the TAP
          controller
        """
        self._ftdi = Ftdi()
        self._trst = trst
        self._frequency = frequency
        self.direction = (JtagController.TCK_BIT |
                          JtagController.TDI_BIT |
                          JtagController.TMS_BIT |
                          (self._trst and JtagController.TRST_BIT or 0))
        self._last = None  # Last deferred TDO bit
        self._write_buff = array('B')

    # Public API
    def configure(self, url):
        """Configure the FTDI interface as a JTAG controller"""
        self._ftdi.open_mpsse_from_url(
            url, direction=self.direction, frequency=self._frequency)
        # FTDI requires to initialize all GPIOs before MPSSE kicks in
        cmd = array('B', (Ftdi.SET_BITS_LOW, 0x0, self.direction))
        self._ftdi.write_data(cmd)

    def close(self):
        if self._ftdi:
            self._ftdi.close()
            self._ftdi = None

    def purge(self):
        self._ftdi.purge_buffers()

    def reset(self, sync=False):
        """Reset the attached TAP controller.
           sync sends the command immediately (no caching)
        """
        # we can either send a TRST HW signal or perform 5 cycles with TMS=1
        # to move the remote TAP controller back to 'test_logic_reset' state
        # do both for now
        if not self._ftdi:
            raise JtagError("FTDI controller terminated")
        if self._trst:
            # nTRST
            value = 0
            cmd = array('B', (Ftdi.SET_BITS_LOW, value, self.direction))
            self._ftdi.write_data(cmd)
            time.sleep(0.1)
            # nTRST should be left to the high state
            value = JtagController.TRST_BIT
            cmd = array('B', (Ftdi.SET_BITS_LOW, value, self.direction))
            self._ftdi.write_data(cmd)
            time.sleep(0.1)
        # TAP reset (even with HW reset, could be removed though)
        self.write_tms(BitSequence('11111'))
        if sync:
            self.sync()

    def sync(self):
        if not self._ftdi:
            raise JtagError("FTDI controller terminated")
        if self._write_buff:
            self._ftdi.write_data(self._write_buff)
            self._write_buff = array('B')

    def write_tms(self, tms):
        """Change the TAP controller state"""
        if not isinstance(tms, BitSequence):
            raise JtagError('Expect a BitSequence')
        length = len(tms)
        if not (0 < length < 8):
            raise JtagError('Invalid TMS length')
        out = BitSequence(tms, length=8)
        # apply the last TDO bit
        if self._last is not None:
            out[7] = self._last
        # print("TMS", tms, (self._last is not None) and 'w/ Last' or '')
        # reset last bit
        self._last = None
        cmd = array('B', (Ftdi.WRITE_BITS_TMS_NVE, length-1, out.tobyte()))
        self._stack_cmd(cmd)
        self.sync()

    def write_tms_tdi_read_tdo(self, tms, tdi):
        """Write out TMS bits while holding TDI constant and reading back in TDO"""
        if not isinstance(tms, BitStream):
            raise JtagError('Expect a BitStream')
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
            raise JtagError('Incorrect type for tdi - must bit BitStream, BitArray or bool')
        
        # apply the last TDI bit
        #@@@if self._last is not None:
        #@@@    out[7] = self._last
        # print("TMS", tms, (self._last is not None) and 'w/ Last' or '')
        # reset last bit
        #@@@self._last = None
        cmd = array('B', (Ftdi.RW_BITS_TMS_PVE_NVE, length-1, tms.int))
        self._stack_cmd(cmd)
        self.sync()
        data = self._ftdi.read_data_bytes(1, 4)
        if (len(data) != 1):
            raise JtagError('Not all data read! Expected {} bytes but only read {} bytes'.format(1,len(data)))
        tdo = BitStream(data)
        tdo.reverse()
        tdo = tdo[:length] # only pass back the same number of bits as clocked out
        return tdo

    def read(self, length):
        """Read out a sequence of bits from TDO"""
        byte_count = length//8
        bit_count = length-8*byte_count
        bs = BitSequence()
        if byte_count:
            bytes_ = self._read_bytes(byte_count)
            bs.append(bytes_)
        if bit_count:
            bits = self._read_bits(bit_count)
            bs.append(bits)
        return bs

    def write_tdi_read_tdo(self, out, use_last=False):
        """ Output a sequence of bits to TDI while reading the TDO input bits """

        if not isinstance(out, BitStream):
            raise JtagError('Expect a BitStream')

        ## @@@ Not used at the moment
        #if use_last:
        #    #(out, self._last) = (out[:-1], bool(out[-1]))
        #    self._last = out[-1]

        byte_count = len(out)//8
        pos = 8*byte_count
        bit_count = len(out)-pos

        # Seperate into BYTE and BIT commands
        tdo = BitStream()
        if byte_count:
            tdo += self._write_read_bytes(out[:pos])

        if bit_count:
            tdo += self._write_read_bits(out[pos:])

        return tdo

    def shift_register(self, out, use_last=False):
        """Shift a BitSequence into the current register and retrieve the
           register output"""
        if not isinstance(out, BitSequence):
            return JtagError('Expect a BitSequence')
        length = len(out)
        if use_last:
            (out, self._last) = (out[:-1], int(out[-1]))
        byte_count = len(out)//8
        pos = 8*byte_count
        bit_count = len(out)-pos
        if not byte_count and not bit_count:
            raise JtagError("Nothing to shift")
        if byte_count:
            blen = byte_count-1
            # print("RW OUT %s" % out[:pos])
            cmd = array('B',
                        (Ftdi.RW_BYTES_PVE_NVE_LSB, blen, (blen >> 8) & 0xff))
            cmd.extend(out[:pos].tobytes(msby=True))
            self._stack_cmd(cmd)
            # print("push %d bytes" % byte_count)
        if bit_count:
            # print("RW OUT %s" % out[pos:])
            cmd = array('B', (Ftdi.RW_BITS_PVE_NVE_LSB, bit_count-1))
            cmd.append(out[pos:].tobyte())
            self._stack_cmd(cmd)
            # print("push %d bits" % bit_count)
        self.sync()
        bs = BitSequence()
        byte_count = length//8
        pos = 8*byte_count
        bit_count = length-pos
        if byte_count:
            data = self._ftdi.read_data_bytes(byte_count, 4)
            if not data:
                raise JtagError('Unable to read data from FTDI')
            byteseq = BitSequence(bytes_=data, length=8*byte_count)
            # print("RW IN %s" % byteseq)
            bs.append(byteseq)
            # print("pop %d bytes" % byte_count)
        if bit_count:
            data = self._ftdi.read_data_bytes(1, 4)
            if not data:
                raise JtagError('Unable to read data from FTDI')
            byte = data[0]
            # need to shift bits as they are shifted in from the MSB in FTDI
            byte >>= 8-bit_count
            bitseq = BitSequence(byte, length=bit_count)
            bs.append(bitseq)
            # print("pop %d bits" % bit_count)
        if len(bs) != length:
            raise ValueError("Internal error")
        return bs

    def _stack_cmd(self, cmd):
        if not isinstance(cmd, array):
            raise TypeError('Expect a byte array')
        if not self._ftdi:
            raise JtagError("FTDI controller terminated")
        # Currrent buffer + new command + send_immediate
        if (len(self._write_buff)+len(cmd)+1) >= JtagController.FTDI_PIPE_LEN:
            self.sync()
        self._write_buff.extend(cmd)

    def _read_bits(self, length):
        """Read out bits from TDO"""
        if length > 8:
            raise JtagError("Cannot fit into FTDI fifo")
        cmd = array('B', (Ftdi.READ_BITS_NVE_LSB, length-1))
        self._stack_cmd(cmd)
        self.sync()
        data = self._ftdi.read_data_bytes(1, 4)
        # need to shift bits as they are shifted in from the MSB in FTDI
        byte = data[0] >> 8-length
        bs = BitSequence(byte, length=length)
        # print("READ BITS %s" % bs)
        return bs

    def _write_read_bits(self, out):
        """Output bits on TDI while reading TDO bits in"""

        # a bitstring.BitStream() has first bit in left-most array position (ie. msb first)
        byte = out.tobytes()    # pads to 8 bits
        
        length = len(out)

        # Check number of bits.
        if not (0 < length <= 8):
            raise JtagError('Wrong number of bits: {}'.format(length))

        # length of 0 for 1 bit, length of 7 for 8 bits, etc.
        cmd = array('B', (self.RW_BITS_PVE_NVE_MSB, length-1, byte.int))

        self._stack_cmd(cmd)
        self.sync()
        data = self._ftdi.read_data_bytes(1, 4)
        if (len(data) != 1):
            raise JtagError('Not all data read! Expected {} bytes but only read {} bytes'.format(1,len(data)))
        tdo = BitStream(data)
        tdo = tdo[:length] # only pass back the same number of bits as clocked out
        return tdo

    def _write_bits(self, out):
        """Output bits on TDI"""
        length = len(out)
        byte = out.tobyte()
        # print("WRITE BITS %s" % out)
        cmd = array('B', (Ftdi.WRITE_BITS_NVE_LSB, length-1, byte))
        self._stack_cmd(cmd)

    def _read_bytes(self, length):
        """Read out bytes from TDO"""
        if length > JtagController.FTDI_PIPE_LEN:
            raise JtagError("Cannot fit into FTDI fifo")
        alen = length-1
        cmd = array('B', (Ftdi.READ_BYTES_NVE_LSB, alen & 0xff,
                          (alen >> 8) & 0xff))
        self._stack_cmd(cmd)
        self.sync()
        data = self._ftdi.read_data_bytes(length, 4)
        bs = BitSequence(bytes_=data, length=8*length)
        # print("READ BYTES %s" % bs)
        return bs

    def _write_read_bytes(self, out):
        """Output bytes on TDI while reading TDO bits in"""

        # a bitstring.BitStream() has first bit in left-most array position (ie. msb first)
        bytes_ = out.bytes
        
        olen = len(bytes_)
        #print("WRITE BYTES %s" % out)

        # Check number of bits.
        #
        # NOTE: the PyFTDI Ftdi class does not define this maximum so we do instead. 
        if (olen > self.MAX_WRITE_BYTES):
            raise JtagError('Too many bits: {}'.format(olen*8))
        
        cmd = array('B', (Ftdi.RW_BYTES_PVE_NVE_MSB, olen & 0xff,
                          (olen >> 8) & 0xff))
        cmd.extend(bytes_)
        self._stack_cmd(cmd)
        self.sync()
        data = self._ftdi.read_data_bytes(olen, 4)
        if (len(data) != olen):
            raise JtagError('Not all data read! Expected {} bytes but only read {} bytes'.format(olen,len(data)))
        return BitStream(data)

    def _write_bytes(self, out):
        """Output bytes on TDI"""
        bytes_ = out.tobytes(msby=True)  # don't ask...
        olen = len(bytes_)-1
        # print("WRITE BYTES %s" % out)
        cmd = array('B', (Ftdi.WRITE_BYTES_NVE_LSB, olen & 0xff,
                          (olen >> 8) & 0xff))
        cmd.extend(bytes_)
        self._stack_cmd(cmd)

    def _write_bytes_raw(self, out):
        """Output bytes on TDI"""
        olen = len(out)-1
        cmd = array('B', (Ftdi.WRITE_BYTES_NVE_LSB, olen & 0xff,
                          (olen >> 8) & 0xff))
        cmd.extend(out)
        self._stack_cmd(cmd)

