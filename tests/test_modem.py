"""Unit tests for the Hayes modem engine, no emulator required.

A FakeEmulator speaks the same [tag][len][payload] frame protocol as the
patched RunCPM, so the whole personality — AT parsing, dialing, RING/answer,
telnet filtering, pacing — is tested against real loopback TCP sockets.

Stdlib only, per the project's no-external-dependencies rule.
"""
import os
import socket
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness.modem import ModemEngine  # noqa: E402


class FakeEmulator:
    """The C side of the bridge, reduced to its wire behavior."""

    def __init__(self, sock_path):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(sock_path)
        self.sock.settimeout(0.05)
        self._raw = bytearray()
        self.data = bytearray()   # accumulated 'D' payloads
        self.carrier = None       # last 'S' payload bit0

    def send(self, payload: bytes):
        frames = b"".join(
            b"D" + bytes([len(payload[i:i + 255])]) + payload[i:i + 255]
            for i in range(0, len(payload), 255)
        )
        self.sock.sendall(frames)

    def command(self, line: str):
        self.send(line.encode() + b"\r")

    def pump(self):
        try:
            chunk = self.sock.recv(4096)
            if chunk:
                self._raw += chunk
        except socket.timeout:
            pass
        while len(self._raw) >= 2:
            length = self._raw[1]
            if len(self._raw) < 2 + length:
                break
            tag, payload = self._raw[0], bytes(self._raw[2:2 + length])
            if tag == ord("D"):
                self.data += payload
            elif tag == ord("S"):
                self.carrier = payload[0] & 1
            del self._raw[:2 + length]

    def wait_for(self, needle: bytes, timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.pump()
            if needle in self.data:
                return True
        return False

    def wait_carrier(self, value: int, timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.pump()
            if self.carrier == value:
                return True
        return False

    def clear(self):
        self.data = bytearray()

    def close(self):
        self.sock.close()


class EchoServer(threading.Thread):
    """Echoes bytes back; records everything it received."""

    def __init__(self):
        super().__init__(daemon=True)
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.port = self.listener.getsockname()[1]
        self.received = bytearray()
        self.conn = None
        self._halt = threading.Event()
        self.start()

    def run(self):
        self.listener.settimeout(0.2)
        while not self._halt.is_set():
            try:
                conn, _ = self.listener.accept()
            except (socket.timeout, OSError):
                continue
            self.conn = conn
            conn.settimeout(0.2)
            while not self._halt.is_set():
                try:
                    data = conn.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not data:
                    break
                self.received += data
                try:
                    conn.sendall(data)
                except OSError:
                    break

    def wait_conn(self, timeout: float = 5.0):
        deadline = time.monotonic() + timeout
        while self.conn is None and time.monotonic() < deadline:
            time.sleep(0.02)
        return self.conn

    def drop_client(self):
        if self.conn:
            self.conn.close()

    def stop(self):
        self._halt.set()
        self.drop_client()
        self.listener.close()
        self.join(timeout=2)


# S12=5 shrinks the +++ guard time to 0.1 s so escape tests stay fast.
FAST_GUARD = {"12": 5}


class ModemTestCase(unittest.TestCase):
    def setUp(self):
        self._engines = []
        self._servers = []
        self._emus = []
        self._dirs = []

    def tearDown(self):
        for emu in self._emus:
            emu.close()
        for engine in self._engines:
            engine.stop()
        for server in self._servers:
            server.stop()

    def make_engine(self, **overrides) -> ModemEngine:
        machine_dir = tempfile.mkdtemp(prefix="modemtest-")
        self._dirs.append(machine_dir)
        config = {
            "sio": {"data_port": 4, "status_port": 6, "baud_port": 0},
            "listen_port": 0,
            "s_registers": dict(FAST_GUARD),
        }
        config.update(overrides)
        engine = ModemEngine(config, machine_dir)
        engine.start()
        self._engines.append(engine)
        return engine

    def make_emu(self, engine: ModemEngine) -> FakeEmulator:
        emu = FakeEmulator(engine.sock_path)
        self._emus.append(emu)
        return emu

    def make_echo(self) -> EchoServer:
        server = EchoServer()
        self._servers.append(server)
        return server

    def escape(self, emu: FakeEmulator):
        """Send +++ with guard-time silence around it; expect OK."""
        time.sleep(0.15)
        emu.clear()
        emu.send(b"+++")
        self.assertTrue(emu.wait_for(b"OK"), "no OK after +++ escape")


class TestCommandMode(ModemTestCase):
    def test_at_ok(self):
        emu = self.make_emu(self.make_engine())
        emu.command("AT")
        self.assertTrue(emu.wait_for(b"OK"))

    def test_unknown_command_errors(self):
        emu = self.make_emu(self.make_engine())
        emu.command("AT%")
        self.assertTrue(emu.wait_for(b"ERROR"))

    def test_not_at_errors(self):
        emu = self.make_emu(self.make_engine())
        emu.command("HELLO")
        self.assertTrue(emu.wait_for(b"ERROR"))

    def test_echo_toggle(self):
        emu = self.make_emu(self.make_engine())
        emu.command("ATE0")
        self.assertTrue(emu.wait_for(b"OK"))
        emu.clear()
        emu.command("AT")
        self.assertTrue(emu.wait_for(b"OK"))
        self.assertNotIn(b"AT", emu.data, "command was echoed despite ATE0")

    def test_accept_and_ignore_classic_knobs(self):
        emu = self.make_emu(self.make_engine())
        emu.command("AT&C1&D2X4M0V1Q0E1")
        self.assertTrue(emu.wait_for(b"OK"))

    def test_numeric_result_codes(self):
        emu = self.make_emu(self.make_engine())
        emu.command("ATV0")
        self.assertTrue(emu.wait_for(b"0\r"))
        emu.clear()
        emu.command("AT%")
        self.assertTrue(emu.wait_for(b"4\r"))

    def test_s_register_set_and_query(self):
        emu = self.make_emu(self.make_engine())
        emu.command("ATS0=2")
        self.assertTrue(emu.wait_for(b"OK"))
        emu.clear()
        emu.command("ATS0?")
        self.assertTrue(emu.wait_for(b"002"))

    def test_info(self):
        emu = self.make_emu(self.make_engine())
        emu.command("ATI")
        self.assertTrue(emu.wait_for(b"RunCPM"))


class TestOutboundCalls(ModemTestCase):
    def test_dial_roundtrip_escape_resume_hangup(self):
        echo = self.make_echo()
        emu = self.make_emu(self.make_engine())
        emu.command(f"ATDT 127.0.0.1:{echo.port}")
        self.assertTrue(emu.wait_for(b"CONNECT"))
        self.assertTrue(emu.wait_carrier(1))

        emu.clear()
        emu.send(b"hello\r")
        self.assertTrue(emu.wait_for(b"hello\r"), "echo did not round-trip")

        self.escape(emu)

        emu.clear()
        emu.command("ATO")
        self.assertTrue(emu.wait_for(b"CONNECT"))
        emu.clear()
        emu.send(b"again")
        self.assertTrue(emu.wait_for(b"again"))

        self.escape(emu)
        emu.clear()
        emu.command("ATH")
        self.assertTrue(emu.wait_for(b"OK"))
        self.assertTrue(emu.wait_carrier(0))

    def test_plus_bytes_inside_data_pass_through(self):
        echo = self.make_echo()
        emu = self.make_emu(self.make_engine())
        emu.command(f"ATDT 127.0.0.1:{echo.port}")
        self.assertTrue(emu.wait_for(b"CONNECT"))
        emu.clear()
        # No guard-time silence around these, so they must reach the remote.
        emu.send(b"a+++b")
        self.assertTrue(emu.wait_for(b"a+++b"))

    def test_remote_close_drops_carrier(self):
        echo = self.make_echo()
        emu = self.make_emu(self.make_engine())
        emu.command(f"ATDT 127.0.0.1:{echo.port}")
        self.assertTrue(emu.wait_for(b"CONNECT"))
        self.assertTrue(emu.wait_carrier(1))
        emu.clear()
        echo.drop_client()
        self.assertTrue(emu.wait_for(b"NO CARRIER"))
        self.assertTrue(emu.wait_carrier(0))

    def test_refused_connection_is_busy(self):
        placeholder = socket.socket()
        placeholder.bind(("127.0.0.1", 0))
        dead_port = placeholder.getsockname()[1]
        placeholder.close()
        emu = self.make_emu(self.make_engine())
        emu.command(f"ATDT 127.0.0.1:{dead_port}")
        self.assertTrue(emu.wait_for(b"BUSY"))

    def test_unknown_number_is_no_carrier(self):
        emu = self.make_emu(self.make_engine())
        emu.command("ATDT 5551212")
        self.assertTrue(emu.wait_for(b"NO CARRIER"))

    def test_phonebook_dialing(self):
        echo = self.make_echo()
        engine = self.make_engine(
            phonebook={"42": {"host": f"127.0.0.1:{echo.port}", "telnet": False}}
        )
        emu = self.make_emu(engine)
        emu.command("ATDT 42")
        self.assertTrue(emu.wait_for(b"CONNECT"))
        emu.clear()
        emu.send(b"ping")
        self.assertTrue(emu.wait_for(b"ping"))


class TestInboundCalls(ModemTestCase):
    def test_ring_answer_talk_hangup(self):
        engine = self.make_engine()
        emu = self.make_emu(engine)
        time.sleep(0.1)  # let the engine adopt this emulator connection
        caller = socket.create_connection(("127.0.0.1", engine.listen_port))
        caller.settimeout(5)
        self.assertTrue(emu.wait_for(b"RING"))
        emu.clear()
        emu.command("ATA")
        self.assertTrue(emu.wait_for(b"CONNECT"))
        self.assertTrue(emu.wait_carrier(1))

        caller.sendall(b"knock knock")
        self.assertTrue(emu.wait_for(b"knock knock"))
        emu.clear()
        emu.send(b"who is there")
        got = b""
        while b"who is there" not in got:
            got += caller.recv(4096)

        caller.close()
        self.assertTrue(emu.wait_for(b"NO CARRIER"))
        self.assertTrue(emu.wait_carrier(0))

    def test_auto_answer(self):
        engine = self.make_engine(s_registers={"0": 1, **FAST_GUARD})
        emu = self.make_emu(engine)
        time.sleep(0.1)
        caller = socket.create_connection(("127.0.0.1", engine.listen_port))
        caller.settimeout(5)
        self.assertTrue(emu.wait_for(b"CONNECT"))
        self.assertTrue(emu.wait_carrier(1))
        caller.sendall(b"auto")
        self.assertTrue(emu.wait_for(b"auto"))
        caller.close()

    def test_answer_without_ring_errors(self):
        emu = self.make_emu(self.make_engine())
        emu.command("ATA")
        self.assertTrue(emu.wait_for(b"ERROR"))


class TestMachineToMachine(ModemTestCase):
    def test_two_engines_call_each_other(self):
        callee_engine = self.make_engine(s_registers={"0": 1, **FAST_GUARD})
        caller_engine = self.make_engine(
            phonebook={"200": f"127.0.0.1:{callee_engine.listen_port}"}
        )
        callee = self.make_emu(callee_engine)
        caller = self.make_emu(caller_engine)
        time.sleep(0.1)

        caller.command("ATD 200")
        self.assertTrue(caller.wait_for(b"CONNECT"))
        self.assertTrue(callee.wait_for(b"CONNECT"))

        caller.clear()
        callee.clear()
        caller.send(b"MARCO")
        self.assertTrue(callee.wait_for(b"MARCO"))
        callee.send(b"POLO")
        self.assertTrue(caller.wait_for(b"POLO"))


class TestTelnetFiltering(ModemTestCase):
    IAC, DONT, DO, WONT, WILL = 255, 254, 253, 252, 251

    def test_negotiation_refused_and_stripped(self):
        echo = self.make_echo()
        engine = self.make_engine(
            phonebook={"9": {"host": f"127.0.0.1:{echo.port}", "telnet": True}}
        )
        emu = self.make_emu(engine)
        emu.command("ATDT 9")
        self.assertTrue(emu.wait_for(b"CONNECT"))
        emu.clear()

        # The "server" (echo) sends us back whatever we send it, so drive the
        # negotiation from the far side directly.
        echo.wait_conn().sendall(bytes([self.IAC, self.DO, 1]) + b"clean")
        self.assertTrue(emu.wait_for(b"clean"))
        self.assertNotIn(self.IAC, emu.data, "IAC leaked through to CP/M")

        deadline = time.monotonic() + 5
        expected = bytes([self.IAC, self.WONT, 1])
        while time.monotonic() < deadline and expected not in echo.received:
            time.sleep(0.02)
        self.assertIn(expected, echo.received, "modem did not refuse IAC DO")

    def test_iac_iac_is_literal_ff(self):
        echo = self.make_echo()
        engine = self.make_engine(
            phonebook={"9": {"host": f"127.0.0.1:{echo.port}", "telnet": True}}
        )
        emu = self.make_emu(engine)
        emu.command("ATDT 9")
        self.assertTrue(emu.wait_for(b"CONNECT"))
        emu.clear()
        echo.wait_conn().sendall(bytes([self.IAC, self.IAC]) + b"x")
        self.assertTrue(emu.wait_for(b"\xffx"))

    def test_outbound_ff_is_escaped(self):
        echo = self.make_echo()
        engine = self.make_engine(
            phonebook={"9": {"host": f"127.0.0.1:{echo.port}", "telnet": True}}
        )
        emu = self.make_emu(engine)
        emu.command("ATDT 9")
        self.assertTrue(emu.wait_for(b"CONNECT"))
        emu.send(b"\xff")
        deadline = time.monotonic() + 5
        expected = bytes([self.IAC, self.IAC])
        while time.monotonic() < deadline and expected not in echo.received:
            time.sleep(0.02)
        self.assertIn(expected, echo.received)


class TestPacing(ModemTestCase):
    def test_300_baud_trickles(self):
        echo = self.make_echo()
        engine = self.make_engine(baud=300)
        emu = self.make_emu(engine)
        emu.command(f"ATDT 127.0.0.1:{echo.port}")
        self.assertTrue(emu.wait_for(b"CONNECT"))
        emu.clear()

        emu.send(b"x" * 60)  # 60 echoed bytes at ~30 cps ≈ 2 s
        time.sleep(0.5)
        emu.pump()
        early = len(emu.data)
        self.assertLess(early, 45, "300 baud pacing not applied")
        self.assertTrue(emu.wait_for(b"x" * 60, timeout=10), "paced bytes never all arrived")


if __name__ == "__main__":
    unittest.main()
