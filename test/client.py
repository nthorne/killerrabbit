#!/usr/bin/env python

""" This application is used to test killerrabbit.

It connects to a server (via killerrabbit), sends some data to it and
asserts that the same data is sent back, closes down the connection and
then starts all over again. """

import socket
import threading
import sys
import time
import logging


# Here's our thread:
class ConnectionThread(threading.Thread):
    """ This type establishes a connection with the server, sends some data
    to it, asserts taht the same data is echoed back, and then terminates
    the connection. """

    def __init__(self, host='localhost', port=9090):
        super(ConnectionThread, self).__init__()

        self.__host = host
        self.__port = port

    def run(self):
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            client.connect((self.__host, self.__port))
        except:
            logging.info("Failed to connect to %s:%d", self.__host,
                         self.__port)

        for tx_byte in xrange(42):
            try:
                client.send(chr(tx_byte))
                rx_byte = client.recv(1)
                logging.debug("  (%d->, ->%d)", tx_byte, ord(rx_byte))
            except:
                break

            assert(chr(tx_byte) == rx_byte)

        logging.debug("Session finished. Closing channel.")
        client.close()

try:
    logging.basicConfig(format='%(asctime)-15s %(message)s')

    LOGGER = logging.getLogger()
    LOGGER.setLevel(logging.INFO)

    socket.setdefaulttimeout(5)

    logging.info("Starting client..")

    while True:
        CONNECTION = ConnectionThread()
        CONNECTION.start()
        CONNECTION.join()

        time.sleep(3)
except KeyboardInterrupt:
    sys.exit(1)
