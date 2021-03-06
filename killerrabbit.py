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

import argparse
import logging
import socket
import threading


class ProxyServer(threading.Thread):
    """ This type implements the proxy server. """

    input_list = []
    channel = {}

    def __init__(self, args, delay=0.0001, buffer_size=4096, timeout=5):
        super(ProxyServer, self).__init__()

        logging.info("Server running at %s:%d", '', args.listen)

        self.args = args

        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(('', args.listen))
        self.server.listen(200)

        self.delay = delay
        self.buffer_size = buffer_size
        self.timeout = timeout

        self.forwarding = True

        self.terminate = False

    def run(self):
        self.input_list.append(self.server)
        while not self.terminate:
            time.sleep(self.delay)
            inputready, _, _ = select.select(self.input_list, [], [],
                                             self.timeout)
            for input_descriptor in inputready:
                if input_descriptor == self.server:
                    self.on_accept()
                    break

                try:
                    data = input_descriptor.recv(self.buffer_size)

                    if len(data) == 0:
                        self.on_close(input_descriptor)
                    else:
                        self.on_recv(input_descriptor, data)
                except socket.error:
                    self.on_close(input_descriptor)

    def on_accept(self):
        """ Called upon when accepting a client connection. Creates the
        forwarding proxy type, and adding it and the client socket to
        the input_list, and setting up the channels. """

        forward = self.connect_socket(self.args.HOST, self.args.PORT)
        clientsock, clientaddr = self.server.accept()
        if forward:
            logging.info("%s:%d has connected", clientaddr[0], clientaddr[1])

            self.input_list.append(clientsock)
            self.input_list.append(forward)
            self.channel[clientsock] = forward
            self.channel[forward] = clientsock
        else:
            logging.warning("Cannot connect to %s:%d", self.args.HOST,
                            self.args.PORT)
            logging.warning("Closing connection with %s:%d", clientaddr[0],
                            clientaddr[1])
            clientsock.close()

    def on_close(self, sock):
        """ Called upon when a client-server connection is to be closed. The
        sockets are closed and removed from the socket list. The associated
        channels are also destroyed. """

        try:
            logging.info("%s:%d has disconnected",
                         sock.getpeername()[0],
                         sock.getpeername()[1])
        except socket.error, exc:
            logging.warning("Encountered %s when trying to close socket", exc)

        if not self.forwarding:
            logging.debug("Connection strangled. Ignoring close request.")
            return

        try:
            self.input_list.remove(sock)
        except ValueError:
            logging.warning("ValueError when removing file descriptor.")

        try:
            out = self.channel[sock]
            self.input_list.remove(self.channel[sock])

            # close the connection with client
            self.channel[out].close()
            # close the connection with remote server
            del self.channel[out]
        except (KeyError, ValueError), exc:
            logging.warning("%s when attempting to close connections", exc)

        try:
            self.channel[sock].close()
            # delete both objects from channel dict
            del self.channel[sock]
        except (KeyError, ValueError), exc:
            logging.warning("%s when attempting to delete input descriptor",
                            exc)

    def on_recv(self, sock, data):
        """ Called upon when data is received on socket sock. Forwards data to
        the intended recipient unless forwarding is False. """

        logging.debug("%s:%d: %s",
                      sock.getpeername()[0],
                      sock.getpeername()[1],
                      binascii.hexlify(data))

        if self.forwarding:
            self.channel[sock].send(data)

    @staticmethod
    def connect_socket(host, port):
        """ Create a socket connected to host:port, and return the socket,
        or None if the connection attempt fails. """

        forward = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        logging.info("Connecting to %s:%s", host, port)

        try:
            forward.connect((host, port))
            return forward
        except socket.error, exc:
            logging.warning("Forwarding proxy: %s", exc)
            return None


class ControlServer(object):
    """ This type is used to control the behavior of the application,
    e.g. toggling data forwarding and terminating the application. Commands
    are sent to the ControlServer over a socket. """

    def __init__(self, rabbit_server, args):
        super(ControlServer, self).__init__()

        logging.info("Starting control server at %s:%d", '',
                     args.control)

        self.__control_host = ''
        self.__control_port = args.control
        self.__rabbit_server = rabbit_server

        self.terminate = False

        self.__command_dict = {
            '?': ("Show help", self.show_help),
            'q': ("Terminate application", self.terminate_application),
            't': ("Toggle data forwarding", self.toggle_data_forwarding),
            'ld': ("Change log level to DEBUG", self.set_debug_loglevel),
            'li': ("Change log level to INFO", self.set_info_loglevel)
        }

        self.__channel = None
        self.server = None

    def main_loop(self):
        """ The main loop of the server. Opens a listening socket on which
        control commands can be sent, and once a control session has been
        established, the command loop is entered. """

        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.bind((self.__control_host, self.__control_port))
            self.server.listen(200)
        except socket.error, exc:
            logging.warning("ControlServer main loop: %s", exc)
            self.server.terminate = True
            return

        self.__channel, _ = self.server.accept()

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
        except socket.error:
            pass

    def show_prompt(self):
        """ Send the prompt to the remote client when awaiting input. """

        try:
            self.__channel.send("> ")
        except socket.error:
            pass

    def read_stripped_lowercased(self):
        """ Read input from remote client, strip it and lowercase it. """
        try:
            self.show_prompt()
            return self.__channel.recv(1024).strip().lower()
        except socket.error:
            pass

    def close(self):
        """ Close the control session channel. """

        try:
            self.__channel.close()
        except socket.error:
            pass

    def show_help(self):
        """ Show the help to the remote client. The help message is built by
        iterating the command map, and generating the help by combining the
        key with the help string associated with each dictionary item. """

        for command in sorted(self.__command_dict.keys()):
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
                     self.__rabbit_server.forwarding)
        self.__rabbit_server.forwarding = not self.__rabbit_server.forwarding

    @staticmethod
    def set_debug_loglevel():
        """ Change application log level to DEBUG. """

        logging.info("Changing log level to DEBUG")
        LOGGER.setLevel(logging.DEBUG)

    @staticmethod
    def set_info_loglevel():
        """ Change application log level to INFO. """

        logging.info("Changing log level to INFO")
        LOGGER.setLevel(logging.INFO)


def parse_arguments():
    """ Parse command line arguments. """
    parser = argparse.ArgumentParser()

    parser.add_argument("HOST",
                        help="Remote host address")
    parser.add_argument("PORT", type=int,
                        help="Remote host port")
    parser.add_argument("--listen", type=int, default=9090,
                        help="Listening port for proxied connections.")
    parser.add_argument("--control", type=int, default=9089,
                        help="Control session port")
    parser.add_argument("--log", type=str, default=None,
                        help="Log to file rather than stdout")

    return parser.parse_args()


if __name__ == '__main__':
    ARGS = parse_arguments()

    logging.basicConfig(format='%(asctime)-15s %(message)s',
                        filename=ARGS.log)

    LOGGER = logging.getLogger()
    LOGGER.setLevel(logging.INFO)

    SERVER = ProxyServer(ARGS)
    try:
        SERVER.start()

        CONTROL = ControlServer(SERVER, ARGS)
        CONTROL.main_loop()

        SERVER.join()
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt. Stopping server.")
        sys.exit(1)
