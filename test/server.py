#!/usr/bin/env python
import sys

import pickle
import socket
import threading
import binascii
import logging


# We'll pickle a list of numbers:
someList = [1, 2, 7, 9, 0]
pickledList = pickle.dumps(someList)


# Our thread class:
class ClientThread(threading.Thread):
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

                logging.debug("Received 0x%s" % binascii.hexlify(byte))
                self.channel.send(byte)
        except Exception, e:
            logging.debug("%s" % e)
            self.channel.close()

if __name__ == '__main__':
    # Set up logging
    logging.basicConfig(format='%(asctime)-15s %(message)s')

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Set up the server:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('', 55132))
    server.listen(5)

    logging.info("Starting server")

    # Have the server serve "forever":
    try:
        while True:
            channel, details = server.accept()
            c = ClientThread(channel, details)
            c.start()
            c.join()
    except KeyboardInterrupt:
        sys.exit(1)
