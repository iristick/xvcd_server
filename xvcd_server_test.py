#!/usr/bin/env python3


#------------------------------------------------------------------------------
# Copyright 2018 Stephen Goadhouse (sgoadhouse@virginia.edu)
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

## This is used to send test packets to the xvcd_server so can debug
## the code using crafted messages.

import socket
from bitstring import BitArray


# From: https://stackoverflow.com/questions/1908878/netcat-implementation-in-python
def netcat(host, port, content, length):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, int(port)))

    s.sendall(content)
    #s.shutdown(socket.SHUT_WR)
    data = s.recv(length)
    #while True:
    #    data = s.recv(length)
    #    if not data:
    #        break
    #    print(repr(data))
    s.close()
    return data

def xvcdSend(cmd, data, retlen):
    IP = '172.28.36.86'
    PORT = 2542

    if isinstance(cmd, str):
        msg = cmd.encode()
    else:
        print("xvcdSend(): cmd must be a string!");
        return(b'')

    if isinstance(data, str):
        dbytes = data.encode()
    elif isinstance(data, bytes):
        dbytes = data
    else:
        print("xvcdSend(): Wrong type for data");
        return(b'')

    print("> {}{}".format(cmd, dbytes.hex()))
    resp = netcat(IP, PORT, msg+dbytes, retlen)

    return resp

def xvcShift(TMS, TDI):

    numBits = TMS.len

    print("TMS: ", TMS)
    print("TDI: ", TDI)
    
    ## Pad to nearest byte alignment
    TMS += BitArray((8 - numBits) % 8)
    TDI += BitArray((8 - numBits) % 8)

    ## Make "little-endian" essentially where bit 0 of first byte is
    ## the first bit out.
    TMS.reverse()
    TMS.byteswap()
    TDI.reverse()
    TDI.byteswap()

    msg = numBits.to_bytes(4, byteorder='little')+TMS.bytes+TDI.bytes
    resp = xvcdSend('shift:', msg, TMS.len // 8)
    TDO = BitArray(resp)
    TDO.byteswap()
    TDO.reverse()
    TDO = TDO[0:numBits]
    
    #print("< 0x{} == ".format(resp.hex()), TDO)
    print("< 0x{}".format(resp.hex()))
    print("TDO: ", TDO)
    print()

    return TDO


if(__name__ == '__main__'):

    resp = xvcdSend('getinfo:', b'', 25)
    print("< ", resp)
    print()
    
    period = 1000
    resp = xvcdSend('settck:', period.to_bytes(4, byteorder='little'), 5)
    print("< 0x{} == {}".format(resp.hex(),int.from_bytes(resp, byteorder='little')))
    print()


    TDO = xvcShift(BitArray('0b1111110110000000000000000'), \
                   BitArray('0b0000000000110110110110110'))

    
