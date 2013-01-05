#!/usr/bin/env python

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
