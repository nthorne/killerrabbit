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


#FORWARD_TO = ('10.160.153.75', 55132)
# TODO: This should be default, to be able to be ovveriden by means
#  of command line argument (argparse)
FORWARD_TO = ('localhost', 55132)


class Forward:
    def __init__(self):
        self.forward = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def start(self, host, port):
        """ Called upon to connect the forwarding proxy to the remote server."""
        logging.info("Connecting forwarding proxy to %s:%s", host, port)

        try:
            self.forward.connect((host, port))
            return self.forward
        except Exception, exc:
            logging.warning("Encountered exception %s in forwarding proxy", exc)
            return False


class TheServer(threading.Thread):
    input_list = []
    channel = {}

    def __init__(self, host, port, delay=0.0001, buffer_size=4096, timeout=5):
        super(TheServer, self).__init__()

        logging.info("Server running at %s:%d", host, port)

        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((host, port))
        self.server.listen(200)

        self.delay = delay
        self.buffer_size = buffer_size

        self.forward_data = True

        self.terminate = False

        self.timeout = timeout

        self.s = None
        self.data = None

    def run(self):
        self.input_list.append(self.server)
        while not self.terminate:
            time.sleep(self.delay)
            inputready, _, _ = select.select(self.input_list, [], [],
                                             self.timeout)
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
        """ Called upon when accepting a client connection. Creates the
        forwarding proxy type, and adding it and the client socket to
        the input_list, and setting up the channels. """

        forward = Forward().start(FORWARD_TO[0], FORWARD_TO[1])
        clientsock, clientaddr = self.server.accept()
        if forward:
            logging.info("%s:%d has connected", clientaddr[0], clientaddr[1])

            self.input_list.append(clientsock)
            self.input_list.append(forward)
            self.channel[clientsock] = forward
            self.channel[forward] = clientsock
        else:
            logging.warning("Cannot connect to %s:%d", FORWARD_TO[0],
                            FORWARD_TO[1])
            logging.warning("Closing connection with %s:%d", clientaddr[0],
                            clientaddr[1])
            clientsock.close()

    def on_close(self):
        """ Called upon when a client-server connection is to be closed. The
        sockets are closed and removed from the socket list. The associated
        channels are also destroyed. """

        try:
            logging.info("%s:%d has disconnected", self.s.getpeername()[0],
                         self.s.getpeername()[1])
        except socket.error, exc:
            logging.warning("Encountered %s when trying to close socket", exc)

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
        except (KeyError, ValueError), exc:
            logging.warning("%s when attempting to close connections", exc)

        try:
            self.channel[self.s].close()
            # delete both objects from channel dict
            del self.channel[self.s]
        except (KeyError, ValueError), exc:
            logging.warning("%s when attempting to delete input descriptor",
                            exc)

    def on_recv(self):
        """ Called upon when data is received on a socket. Forwards data to the
        intended recipient unless forward_data is False. """

        data = self.data
        logging.debug("Data from %s:\n%s\n",
                      self.s.getpeername()[0], self.s.getpeername()[1],
                      binascii.hexlify(data))

        if self.forward_data:
            self.channel[self.s].send(data)


class ControlServer(object):
    """ This type is used to control the behavior of the application,
    e.g. toggling data forwarding and terminating the application. Commands
    are sent to the ControlServer over a socket. """

    def __init__(self, rabbit_server, control_host='', control_port=9089):
        super(ControlServer, self).__init__()

        logging.info("Starting control server at %s:%d", control_host,
                     control_port)

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
        """ The main loop of the server. Opens a listening socket on which
        control commands can be sent, and once a control session has been
        established, the command loop is entered. """

        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.bind((self.__control_host, self.__control_port))
            self.server.listen(200)
        except Exception, exc:
            logging.warning("Encountered exception in control object: %s", exc)
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
        """ Greet client upon connection to control server. """

        self.send("Control session established (? for available commands)")

    def send(self, msg):
        """ Send newline terminated message to the remote client. """

        try:
            self.__channel.send("%s\n" % msg)
        except Exception:
            pass

    def show_prompt(self):
        """ Send the prompt to the remote client when awaiting input. """

        try:
            self.__channel.send("> ")
        except Exception:
            pass

    def read_stripped_lowercased(self):
        """ Read input from remote client, strip it and lowercase it. """
        try:
            self.show_prompt()
            return self.__channel.recv(1024).strip().lower()
        except Exception:
            pass

    def close(self):
        """ Close the control session channel. """

        try:
            self.__channel.close()
        except Exception:
            pass

    def show_help(self):
        """ Show the help to the remote client. The help message is built by
        iterating the command map, and generating the help by combining the
        key with the help string associated with each dictionary item. """

        for command in self.__command_dict.keys():
            self.send("%s - %s" % (command, self.__command_dict[command][0]))

    def terminate_application(self):
        """ Terminate the application, by telling the main server to exit from
        its main loop, and by flagging that the control server also should exit
        from its main loop. """

        logging.info("Terminating apllication..")
        self.__rabbit_server.terminate = True
        self.close()
        self.terminate = True

    def toggle_data_forwarding(self):
        """ Toggle data forwarding, i.e. tell the main server that no data shall
        be forwarded from the sending party to the receiving party. """

        logging.info("Toggling data forwarding (was %s)",
                     self.__rabbit_server.forward_data)
        self.__rabbit_server.forward_data = not self.__rabbit_server.forward_data

    def set_debug_loglevel(self):
        """ Change application log level to DEBUG. """

        logging.info("Changing log level to DEBUG")
        LOGGER.setLevel(logging.DEBUG)

    def set_info_loglevel(self):
        """ Change application log level to INFO. """

        logging.info("Changing log level to INFO")
        LOGGER.setLevel(logging.INFO)


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)-15s %(message)s')

    LOGGER = logging.getLogger()
    LOGGER.setLevel(logging.INFO)

    SERVER = TheServer('', 9090)
    try:
        SERVER.start()

        CONTROL = ControlServer(SERVER)
        CONTROL.main_loop()

        SERVER.join()
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt. Stopping server.")
        sys.exit(1)
