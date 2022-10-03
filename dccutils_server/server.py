import sys
import threading
import socket
import uvicorn
import logging

from dccutils_server.api import app

if app.dcc_context.get_dcc_name() == "Unreal Editor":
    # monkey patch to fix logger
    sys.stdout.isatty = lambda: False
    sys.stderr.isatty = lambda: False

    monkeylogger = logging.getLogger("monkeylogger")
    monkeylogger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = uvicorn.logging.DefaultFormatter("%(levelprefix)s %(message)s")
    handler.setFormatter(formatter)
    monkeylogger.addHandler(handler)
    monkeylogger.propagate = False
    uvicorn.server.logger = monkeylogger

    from uvicorn.lifespan.on import LifespanOn

    old_init = LifespanOn.__init__

    def new_init(self, config: uvicorn.Config) -> None:
        old_init(self, config)
        self.logger = monkeylogger

    LifespanOn.__init__ = new_init
    # end monkey patch


def find_free_port(port_range=range(10000, 10100)):
    for port in port_range:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return False


def server_start(port_range=range(10000, 10100)):
    port = find_free_port(port_range)
    if port:
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        app.dcc_context.software_print(
            "Cannot find a free port in the range [%i...%i]"
            % (port_range[0], port_range[len(port_range - 1)])
        )


def server_start_threading(port_range=range(10000, 10100)):
    thread = threading.Thread(
        target=server_start, kwargs={"port_range": port_range}, daemon=True
    )
    thread.start()
    return thread
