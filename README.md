Short description
=================
Xvcd Server is a program which interfaces Xilinx with JTAG adapters using the
Xilinx Virtual Cable. This is achieved by starting a TCP server listening for
xvc commands which are sent out to a jtag adapter.

Usage
=====

Start xvcd_server.py <adapter>

Where <adapter> is one of the adapters under the adapters folder.
Either ft2232h, ft4232h, ft232h, papilio_one or xula. xula still uses
the old GPIO method whereas the others use FTDI MPSSE mode.

This server listens to TCP port 2542

In Xilinx iMPACT, Cable Setup choose "Open Cable Plug-in" and enter

"xilinx_xvc host=127.0.0.1:2542 disableversioncheck=true"

Thanks to
=========

Many thanks to the person behind this blog post!

http://debugmo.de/2012/02/xvcd-the-xilinx-virtual-cable-daemon/
