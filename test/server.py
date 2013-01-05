#!/usr/bin/env python

#Copyright (C) 2013 Niklas Thorne.

#This file is part of killerrabbit.
#
#killerrabbit is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, either version 3 of the License, or
#(at your option) any later version.
#
#killerrabbit is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.
#
#You should have received a copy of the GNU General Public License
#along with killerrabbit.  If not, see <http://www.gnu.org/licenses/>.

""" This application, which is used to test killerrabbit, implements an echo
SERVER. """

import binascii
import sys

import logging
import socket
import threading


class ClientThread(threading.Thread):
    """ This type implements the echo SERVER. """

    def __init__(self, channel, details):

        self.channel = channel
        self.details = details
        threading.Thread.__init__(self)

    def run(self):
        try:
            while True:
                byte = self.channel.recv(1)

                if not byte:
                    logging.debug("Received empty string. Closing channel.")
                    self.channel.close()

                logging.debug("Received 0x%s", binascii.hexlify(byte))
                self.channel.send(byte)
        except Exception, exc:
            logging.debug("%s", exc)
            self.channel.close()

if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)-15s %(message)s')

    LOGGER = logging.getLogger()
    LOGGER.setLevel(logging.INFO)

    SERVER = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    SERVER.bind(('', 55132))
    SERVER.listen(5)

    logging.info("Starting server")

    try:
        while True:
            CHANNEL, DETAILS = SERVER.accept()
            CLIENT = ClientThread(CHANNEL, DETAILS)
            CLIENT.start()
            CLIENT.join()
    except KeyboardInterrupt:
        sys.exit(1)
