killerrabbit
============

This application is a TCP proxy that can be used to inspect and modify
communication sessions; its behavior is controlled by connecting to the
application control port (currently hard coded to 9089).

sample session
--------------

    $ ./killerrabbit.py
    $ telnet localhost 9089
    Trying 127.0.0.1...
    Connected to localhost.
    Escape character is '^]'.
    Control session established (? for available commands)
    > q
    Connection closed by foreign host.
