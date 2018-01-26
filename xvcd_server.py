#!/usr/bin/env python3

#------------------------------------------------------------------------------
# Copyright 2013 Joachim Lublin (joachim.lublin@gmail.com)
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

import socket
import socketserver
import sys
import time
import bitstring
from math import ceil
import argparse
import importlib

BIT_SHIFT_MAX = 512
XVC_VERSION = 1.0
XVC_INFO = "xvcServer_v{:.1f}:{}\n".format(XVC_VERSION, BIT_SHIFT_MAX) 

class xvcd_server(socketserver.BaseRequestHandler):

    # This code has been updated to handle all of the Virtual
    # Cable commands and restructered to operate more like
    # Xilinx's official Virtual Cable code found at
    # https://github.com/Xilinx/XilinxVirtualCable/blob/master/XAPP1251/src/xvcServer.c.
    # The attribution comment from this file follows. Note that this is based on v1.0 of xvcServer.c
    #
    # This work, "xvcServer.c", is a derivative of "xvcd.c" (https://github.com/tmbinc/xvcd)
    # by tmbinc, used under CC0 1.0 Universal (http://creativecommons.org/publicdomain/zero/1.0/).
    # "xvcServer.c" is licensed under CC0 1.0 Universal (http://creativecommons.org/publicdomain/zero/1.0/)
    # by Avnet and is used by Xilinx for XAPP1251.

    def sread(self, length):
        data = b''              # start with empty byte array
        while (length):
            #@@@# Is there a more efficient way to handle reading data into a buffer for Python?
            try:
                newData = self.request.recv(length)
                if not newData:
                    # Possibly an error like timeout, so return the
                    # empty byte array to flag error.
                    print('Error during socket read')
                    return b''
                    
            except ConnectionResetError:
                print('Connection reset by peer')
                return b''

            # catch all others
            except:             
                print('Unknown error during socket read')
                return b''

            # Add read data into the data array and update length variable
            data += newData
            length -= len(newData)

        return data

    
    def handle(self):

        if(self.server.has_client_connected):
            if(self.server.opts.verbose >= 2):
                print('Another client attempted to connect - REJECTING!')
            return
        self.server.has_client_connected = True

        while(True):

            ## Read the first two characters to differentiate the commands
            cmdSnippet = self.sread(2)

            ## Handle commands
            if (cmdSnippet == b'ge'):
                ## From https://github.com/Xilinx/XilinxVirtualCable#message-getinfo:
                #
                # getinfo
                #
                # The primary use of "getinfo:" message is to get the XVC
                # server version. The server version provides a client a
                # way of determining the protocol capabilites of the
                # server.
                #
                # Server Returns:
                #
                # “xvcServer_v1.0:<xvc_vector_len>\n”
                # Where:
                #
                # <xvc_vector_len> is the max width of the vector that can be shifted
                #                  into the server (in ASCII)
                #

                # Expect this to be "getinfo:", so read the rest of the
                # command and verify it, just in case
                data = self.sread(6)
                
                if (data == b'tinfo:'):
                    if(self.server.opts.verbose >= 2):
                        print('CMD=getinfo - Response: {}'.format(XVC_INFO))
                    self.request.sendall(XVC_INFO.encode())
                    continue    ## get next input
                else:
                    print('Invalid command "{}". Aborting!'.format(cmdSnippet + data))
                    break       ## Abort

            elif (cmdSnippet == b'se'): 
                ## From https://github.com/Xilinx/XilinxVirtualCable#message-settck:
                #            
                # The "settck:" message configures the server TCK
                # period. When sending JTAG vectors the TCK rate may need
                # to be varied to accomodate cable and board signal
                # integrity conditions. This command is used by clients to
                # adjust the TCK rate in order to slow down or speed up
                # the shifting of JTAG vectors.
                #
                # Syntax:
                # Client Sends:   "settck:<set period>"
                # Server Returns: “<current period>”
                #
                # Where:
                #
                # <set period>      is TCK period specified in ns. This value is a little-endian
                #                   integer value.
                # <current period>  is the value set on the server by the settck command. If
                #                   the server cannot set the value then it will return the
                #                   current value.
                #

                # Expect this to be "settck:<set period>", so read the rest of the
                # command and verify it, just in case
                data = self.sread(9)
                
                if (data[0:5] == b'ttck:'):
                    ## YES, it is settck:<set period>
                    #
                    # Now, grab the period argument
                    set_period = int.from_bytes(data[5:9], byteorder='little')
                
                    ## Ask the JTAG adapter to set the TCK period and
                    #  return the period that it says it can do
                    current_period = self.server.jtag.set_tck_period(set_period)
                
                    if(self.server.opts.verbose >= 2):
                        print('CMD={}:{} - Response={}'.format(cmdSnippet+data[0:5], set_period, current_period))

                    self.request.sendall(current_period.to_bytes(4, byteorder='little'))
                    continue ## get next input
                else:
                    print('Invalid command "{}". Aborting!'.format(cmdSnippet + data))
                    break       ## Abort

            elif (cmdSnippet == b'sh'): 
                ## From https://github.com/Xilinx/XilinxVirtualCable#message-shift:
                #            
                # The "shift:" message is used to shift JTAG vectors in and out of a
                # device. The number of bits to shift is specified as the first shift
                # command parameter followed by the TMS and TDI data vectors. The TMS
                # and TDI vectors are sized according to the number of bits to shift,
                # rouneded to the nearest byte. For instance if shifting in 13 bits the
                # byte vectors will be rounded to 2 bytes. Upon completion of the JTAG
                # shift operation the server will return a byte sized vector containing
                # the sampled target TDO value for each shifted TCK clock.
                # 
                # Syntax:
                # Client Sends:   "shift:<num bits><tms vector><tdi vector>"
                # Server Returns: “<tdo vector>”
                # 
                # Where:
                # 
                # <num bits>   : is a integer in little-endian mode. This represents the number
                #                of TCK clk toggles needed to shift the vectors out
                # <tms vector> : is a byte sized vector with all the TMS shift in bits Bit 0 in
                #                Byte 0 of this vector is shifted out first. The vector is
                #                num_bits and rounds up to the nearest byte.
                # <tdi vector> : is a byte sized vector with all the TDI shift in bits Bit 0 in
                #                Byte 0 of this vector is shifted out first. The vector is
                #                num_bits and rounds up to the nearest byte.
                # <tdo vector> : is a byte sized vector with all the TDO shift out bits Bit 0 in
                #                Byte 0 of this vector is shifted out first. The vector is
                #                num_bits and rounds up to the nearest byte.
                #

                # Expect this to be "shift:<num bits><tms vector><tdi vector>", so read the rest of the
                # command and verify it, just in case
                data = self.sread(4)
                
                if (data == b'ift:'):
                    ## YES, it is "shift:"
                    #
                    # However, since all of the real processing
                    # happens for this command, handle it below. Here,
                    # simple output a verbose message and continue
                    # below
                
                    if(self.server.opts.verbose >= 2):
                        print('CMD={}:'.format(cmdSnippet+data))

                else:
                    print('Invalid command "{}". Aborting!'.format(cmdSnippet + data))
                    break       ## Abort

            else:
                print('Invalid command snippet "{}". Aborting!'.format(cmdSnippet))
                break       ## Abort
                
            ## Command must be shift: to get this far, but have not read the argument yet - still could be invalid
            #
            # Read the bit length parameter
            numBitsArg = self.sread(4)
            if (not numBitsArg):
                print('Reading "shift:" bit length parameter failed - ABORTING!')
                break ## An error occurred - simply abort here

            numBits = int.from_bytes(numBitsArg, byteorder='little')
            numBytes = (numBits + 7) // 8

            #@@@# Should we check buffer size like in xvcServer.c? Do we care in Python?
                
            if(self.server.opts.verbose >= 2):
                print('shift: Num Bits: {} = Num Bytes: {}:'.format(numBits, numBytes))

            # Read the TMS & TDI vectors
            vectArg = self.sread(numBytes * 2)
            if (not vectArg):
                print('Reading "shift:" TMS & TDI vector parameters failed - ABORTING!')
                break ## An error occurred - simply abort here
            
            # Split args in TMS data and TDI data
            vectArg = [vectArg[0:numBytes], vectArg[numBytes:2*numBytes]]

            TMS = bitstring.pack('bytes:{}'.format(numBytes), vectArg[0])
            TDI = bitstring.pack('bytes:{}'.format(numBytes), vectArg[1])

            # Fix LSB first (@@@ Is this really necessary? Simply deal with bits backwards? Performance Hit to do this?)
            TMS.byteswap()
            TMS.reverse()
            TDI.byteswap()
            TDI.reverse()

            TMS = TMS[0:numBits]
            TDI = TDI[0:numBits]

            if(self.server.opts.verbose >= 3):
                print('TMS bitstream: {}'.format(TMS.bin))
                print('TDI bitstream: {}'.format(TDI.bin))

            # Fix for bug in Xilinx ISE
            if(self.server.jtag.get_state() == self.server.jtag.EXIT_1_IR and TMS == bitstring.BitStream('0b11101')):
                if(self.server.opts.verbose >= 2):
                    print('Avoiding "route via Capture-IR"-bug')

                self.request.sendall(b'\x1f')
                continue


            startTime = time.time()
            TDO = self.server.jtag.send_data(TMS, TDI)
            stopTime  = time.time()

            if(self.server.opts.verbose >= 2):
                print('send_data() time: {}'.format(stopTime-startTime))

            if(self.server.opts.verbose >= 3):
                print('TDO bitstream: {}'.format(TDO.bin))

            # Add padding
            TDO += bitstring.BitStream((8 - TDO.len) % 8)
            TDO.reverse()
            TDO.byteswap()

            # Return the TDO vector as response to "shift:" message
            # and continue to top of loop.
            self.request.sendall(TDO.tobytes())

        # Abort the server
        self.finish()
        
        # Allow a new client to connect
        self.server.has_client_connected = False


def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP
                        
if(__name__ == '__main__'):

    parser = argparse.ArgumentParser()
    parser.add_argument('--reset', action='store_true', help='Pulses the PROGRAM_B pin before starting server')
    parser.add_argument('adapter', help='Select which JTAG adapter to use')
    parser.add_argument('--port', default=2542, type=int)
    parser.add_argument('--verbose', '-v', action='count', default=0, help='Increase verbosity level')
    parser.add_argument('--local', '-l', action='store_true', help='Use to bind to local HOST typically when running on same computer as Xilinx tools')

    opts = parser.parse_args()

    # Load JTAG adapter
    try:
        mod = importlib.import_module('adapters.' + opts.adapter)
    except:
        print('Adapter {} failed to load. Exiting...'.format(opts.adapter))
        exit()

    jtag = mod.jtag_adapter()
    jtag.set_verbosity(opts.verbose)

    if(opts.reset):
        jtag.reset()

    if(opts.local):
        #@@@#HOST = 'localhost'
        HOST = '127.0.0.1'
    else:
        HOST = get_ip()
        
    #Print a helpful message indicating how to use the XVCD server.
    print("Starting XVCD server. In the relevant tool, use the following cable plugin command:\n")
    print("If ISE (?):")
    print(("    xilinx_xvc host={0}:{1} disableversioncheck=true\n").format(HOST,opts.port))
    print("If Vivado, in the Tcl Console:")
    print( "    connect_hw_server")
    print(("    open_hw_target -xvc_url {0}:{1}\n").format(HOST,opts.port))
    print("You should be able to use the relevant tool normally.\n")

    try:
        server = socketserver.TCPServer((HOST, opts.port), xvcd_server)
        server.has_client_connected = False     # Single client for now, deny other requests
        server.opts = opts     ## pass the command line options to the server
        server.jtag = jtag     ## pass the server which adapter has been selected
        server.serve_forever()

    except KeyboardInterrupt:
        print("\nExiting Xilinx Virtual Cable Driver Server\n")
        sys.exit(0)

