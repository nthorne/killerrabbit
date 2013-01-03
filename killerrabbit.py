#!/usr/bin/env python

"""
Simple pure-python socket proxy.

This proxy basically provides data inspection as well as low-level
manipulation of the streams (e.g. connection termination, dropping
messages).
"""
import binascii
import select
import sys
import time

import logging
import socket
import threading


#forward_to = ('10.160.153.75', 55132)
# TODO: This should be default, to be able to be ovveriden by means
#  of command line argument (argparse)
forward_to = ('localhost', 55132)


class Forward:
    def __init__(self):
        self.forward = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def start(self, host, port):
        logging.info(
            "Connecting forwarding proxy to %s:%s" % (host, port))

        try:
            self.forward.connect((host, port))
            return self.forward
        except Exception, e:
            logging.warning(
                "Encountered exception %s in forwarding proxy" % e)
            return False


class TheServer(threading.Thread):
    input_list = []
    channel = {}

    def __init__(self, host, port, delay=0.0001, buffer_size=4096, timeout=5):
        super(TheServer, self).__init__()

        logging.info("Server running at %s:%d" % (host, port))

        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((host, port))
        self.server.listen(200)

        self.delay = delay
        self.buffer_size = buffer_size

        self.forward_data = True

        self.terminate = False

        self.timeout = timeout

    def run(self):
        self.input_list.append(self.server)
        while not self.terminate:
            time.sleep(self.delay)
            ss = select.select
            inputready, outputready, exceptready = ss(self.input_list, [], [], self.timeout)
            for self.s in inputready:
                if self.s == self.server:
                    self.on_accept()
                    break

                try:
                    self.data = self.s.recv(self.buffer_size)

                    if len(self.data) == 0:
                        self.on_close()
                    else:
                        self.on_recv()
                except Exception:
                    self.on_close()

    def on_accept(self):
        forward = Forward().start(forward_to[0], forward_to[1])
        clientsock, clientaddr = self.server.accept()
        if forward:
            logging.info("%s:%d has connected" % clientaddr)

            self.input_list.append(clientsock)
            self.input_list.append(forward)
            self.channel[clientsock] = forward
            self.channel[forward] = clientsock
        else:
            logging.warning("Cannot connect to %s:%d" % forward_to)
            logging.warning("Closing connection with %s:%d" % clientaddr)
            clientsock.close()

    def on_close(self):
        try:
            logging.info("%s:%d has disconnected" % self.s.getpeername())
        except socket.error, e:
            logging.warning("Encountered %s when trying to close socket" % e)
            pass

        if not self.forward_data:
            logging.debug("Connection strangled. Ignoring close request.")
            return

        try:
            self.input_list.remove(self.s)
        except ValueError:
            logging.warning("ValueError when removing file descriptor.")

        try:
            out = self.channel[self.s]
            self.input_list.remove(self.channel[self.s])

            # close the connection with client
            self.channel[out].close()  # equivalent to do self.s.close()
            # close the connection with remote server
            del self.channel[out]
        except (KeyError, ValueError), e:
            logging.warning("%s when attempting to close connections" % e)

        try:
            self.channel[self.s].close()
            # delete both objects from channel dict
            del self.channel[self.s]
        except (KeyError, ValueError), e:
            logging.warning("%s when attempting to delete input descriptor" % e)

    def on_recv(self):
        data = self.data
        logging.debug("Data from %s (strangling connection after %d messages) :\n%s\n" % (
            self.s.getpeername(), self.forward_data, binascii.hexlify(data)))

        if self.forward_data:
            self.channel[self.s].send(data)


class ControlServer(object):
    def __init__(self, rabbit_server, control_host='', control_port=9089,
                 delay=0.0001):
        super(ControlServer, self).__init__()

        logging.info("Starting control server at %s:%d" %
                     (control_host, control_port))

        self.__control_host = control_host
        self.__control_port = control_port
        self.__rabbit_server = rabbit_server

        self.terminate = False

        self.__command_dict = {
            '?': ("Show help", self.show_help),
            'q': ("Terminate application", self.terminate_application),
            't': ("Toggle data forwarding", self.toggle_data_forwarding),
            'ld': ("Change log level to DEBUG", self.set_debug_loglevel),
            'li': ("Change log level to INFO", self.set_info_loglevel)
        }

    def main_loop(self):
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.bind((self.__control_host, self.__control_port))
            self.server.listen(200)
        except Exception, e:
            logging.warning("Encountered exception in control object: %s" % e)
            self.server.terminate = True
            return

        self.__channel, details = self.server.accept()

        self.greet()

        while not self.terminate:
            command = self.read_stripped_lowercased()

            try:
                self.__command_dict[command][1]()
            except KeyError:
                self.send("%s - no such command" % command)

    def greet(self):
        self.send("Control session established (enter ? for available commands)")

    def send(self, msg):
        try:
            self.__channel.send("%s\n" % msg)
        except:
            pass

    def show_prompt(self):
        try:
            self.__channel.send("> ")
        except:
            pass

    def read_stripped_lowercased(self):
        try:
            self.show_prompt()
            return self.__channel.recv(1024).strip().lower()
        except:
            pass

    def close(self):
        try:
            self.__channel.close()
        except:
            pass

    def show_help(self):
        for command in self.__command_dict.keys():
            self.send("%s - %s" % (command, self.__command_dict[command][0]))

    def terminate_application(self):
        logging.info("Terminating apllication..")
        self.__rabbit_server.terminate = True
        self.close()
        self.terminate = True

    def toggle_data_forwarding(self):
        logging.info("Toggling data forwarding (was %s)" %
                     self.__rabbit_server.forward_data)
        self.__rabbit_server.forward_data = not self.__rabbit_server.forward_data

    def set_debug_loglevel(self):
        logging.info("Changing log level to DEBUG")
        logger.setLevel(logging.DEBUG)

    def set_info_loglevel(self):
        logging.info("Changing log level to INFO")
        logger.setLevel(logging.INFO)


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)-15s %(message)s')

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    server = TheServer('', 9090)
    try:
        server.start()
        #server.join()

        c = ControlServer(server)
        c.main_loop()

        # THIS DID NOT TERMINATE PROPERLY. WHY?
        server.join()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt. Stopping server.")
        sys.exit(1)
