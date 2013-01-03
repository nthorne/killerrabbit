#!/usr/bin/env python

#import pickle
import socket
import threading
import sys
import time
import logging


# Here's our thread:
class ConnectionThread(threading.Thread):
    def __init__(self, host='localhost', port=9090):
        super(ConnectionThread, self).__init__()

        self.__host = host
        self.__port = port

    def run(self):
        # Connect to the server:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            client.connect((self.__host, self.__port))
        except:
            logging.info("Failed to connect to %s:%d" %
                         (self.__host, self.__port))

        # Retrieve and unpickle the list object:
        #print pickle.loads(client.recv(1024))

        # Send some messages:
        for x in xrange(42):
            try:
                client.send(chr(x))
                y = client.recv(1)
            except:
                break

            logging.debug("  (%d->, ->%d)" % (x, ord(y)))
            assert(chr(x) == y)

        logging.debug("Session finished. Closing channel.")
        # Close the connection
        client.close()

try:
    logging.basicConfig(format='%(asctime)-15s %(message)s')

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    socket.setdefaulttimeout(5)

    while True:
        c = ConnectionThread()
        c.start()
        c.join()

        time.sleep(3)
except KeyboardInterrupt:
    sys.exit(1)
