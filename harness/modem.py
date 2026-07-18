"""Hayes-style modem engine, the peer of RunCPM's serial-bridge patch.

The patched emulator (harness/patches/) presents a minimal Z80 SIO at the
machine's historical modem ports and relays the byte stream over a Unix socket
in the machine directory. This module is the other end of that socket: the
modem *personality*. It speaks the Hayes AT command set to CP/M software and
turns "phone calls" into TCP connections — dialing out to arbitrary hosts or
phonebook entries, and answering inbound connections on a listen port with
RING/ATA. The real Kaypro modem predates Hayes (software poked a TI dialer
chip directly), but AT is the dialect every terminal program speaks.

A machine gets a modem by having a modem.json next to its drives:

    {
      "sio": {"data_port": 4, "status_port": 6, "baud_port": 0},
      "listen_port": 2323,          // omit for no inbound calls; 0 = ephemeral
      "listen_host": "127.0.0.1",   // default; set 0.0.0.0 to answer the world
      "baud": 0,                    // 0 = full speed, 300 = authentic pacing
      "telnet_default": false,      // IAC filtering for non-phonebook dials
      "phonebook": {"2": {"host": "127.0.0.1:2324", "telnet": false}},
      "s_registers": {"0": 0}       // Hayes S-register defaults
    }

Wire format on the Unix socket, both directions: [tag:1][len:1][payload:len].
To the emulator: 'D' = data, 'S' = status (payload bit0 = carrier/DCD).
From the emulator: 'D' = data. The engine runs in one daemon thread with one
selector loop; the daemon's main thread can stay blocked in session.run()
while a comms program is online.
"""
import errno
import json
import os
import re
import selectors
import socket
import threading
import time

from . import modem_sock_path

# Hayes result codes: verbose text and the ATV0 numeric equivalents.
_RESULT_CODES = {
    "OK": 0,
    "CONNECT": 1,
    "RING": 2,
    "NO CARRIER": 3,
    "ERROR": 4,
    "NO DIALTONE": 6,
    "BUSY": 7,
    "NO ANSWER": 8,
}

_S_DEFAULTS = {0: 0, 2: 43, 7: 30, 12: 50}  # auto-answer, escape char, dial timeout s, guard 1/50 s

# Telnet protocol bytes, for IAC filtering.
_IAC, _DONT, _DO, _WONT, _WILL, _SB, _SE = 255, 254, 253, 252, 251, 250, 240

_RING_INTERVAL = 3.0
_RING_GIVE_UP = 10  # unanswered rings before the "caller" is dropped

# Dial-string modifiers a comms program may embed in a number: separators,
# waits, pauses. Stripped for phonebook lookup only — hostnames keep their dots
# and dashes.
_DIAL_MODIFIERS = re.compile(r"[\s\-,!@;()]")

_COMMAND, _DIALING, _ONLINE, _RINGING = "COMMAND", "DIALING", "ONLINE", "RINGING"


class ModemEngine:
    def __init__(self, config: dict, machine_dir: str):
        self.machine_dir = machine_dir
        self.sock_path = modem_sock_path(machine_dir)
        sio = config.get("sio", {})
        self._sio_env = {
            "CPM_MODEM_SOCKET": self.sock_path,
            "CPM_SIO_DATA_PORT": str(sio.get("data_port", 4)),
            "CPM_SIO_STATUS_PORT": str(sio.get("status_port", 6)),
            "CPM_SIO_BAUD_PORT": str(sio.get("baud_port", 0)),
        }
        self._listen_port_cfg = config.get("listen_port")
        self._listen_host = config.get("listen_host", "127.0.0.1")
        self.baud = int(config.get("baud", 0))
        self.telnet_default = bool(config.get("telnet_default", False))
        self.phonebook = config.get("phonebook", {})
        self._s_defaults = dict(_S_DEFAULTS)
        for key, value in config.get("s_registers", {}).items():
            self._s_defaults[int(key)] = int(value)

        self.listen_port = None  # actual port once bound (listen_port 0 = ephemeral)
        self._sel = None
        self._server = None
        self._listener = None
        self._thread = None
        self._stop = threading.Event()

        self._emu = None            # the emulator's Unix-socket connection
        self._emu_in = bytearray()  # frame reassembly from the emulator
        self._emu_out = bytearray() # frames awaiting a writable emulator socket
        self._remote = None         # the TCP "phone line"
        self._remote_label = None
        self._reset_call_state()
        self._reset_profile()

    @classmethod
    def from_machine(cls, machine_dir: str):
        """The engine for a machine, or None if it has no modem.json."""
        cfg_path = os.path.join(machine_dir, "modem.json")
        if not os.path.exists(cfg_path):
            return None
        with open(cfg_path) as f:
            return cls(json.load(f), machine_dir)

    def env(self) -> dict:
        """Environment overlay telling the patched emulator where the SIO lives."""
        return dict(self._sio_env)

    def status(self) -> dict:
        return {
            "state": self._state,
            "carrier": bool(self._carrier),
            "listening": self.listen_port,
            "connected_to": self._remote_label if self._remote else None,
        }

    # -- lifecycle ---------------------------------------------------------

    def start(self):
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)
        self._sel = selectors.DefaultSelector()
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(self.sock_path)
        self._server.listen(1)
        self._server.setblocking(False)
        self._sel.register(self._server, selectors.EVENT_READ, self._accept_emu)
        if self._listen_port_cfg is not None:
            self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._listener.bind((self._listen_host, self._listen_port_cfg))
            self._listener.listen(1)
            self._listener.setblocking(False)
            self.listen_port = self._listener.getsockname()[1]
            self._sel.register(self._listener, selectors.EVENT_READ, self._accept_call)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        for sock in (self._emu, self._remote, self._listener, self._server):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        if self._sel:
            self._sel.close()
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)

    def _loop(self):
        while not self._stop.is_set():
            for key, _ in self._sel.select(timeout=0.05):
                key.data(key.fileobj)
            self._tick()

    # -- modem state -------------------------------------------------------

    def _reset_call_state(self):
        self._state = _COMMAND
        self._carrier = 0
        self._cmd_buf = bytearray()
        self._plus_count = 0
        self._plus_pending = bytearray()
        self._last_emu_byte = 0.0
        self._dial_deadline = 0.0
        self._ring_count = 0
        self._next_ring = 0.0
        self._rx_queue = bytearray()   # remote bytes awaiting delivery (pacing / ATO)
        self._pace_allowance = 0.0
        self._pace_last = time.monotonic()
        self._telnet = False
        self._tn_state = 0             # 0 normal, 1 saw IAC, 2 await option, 3 in SB
        self._tn_cmd = 0

    def _reset_profile(self):
        self.echo = True
        self.verbose = True
        self.quiet = False
        self.s_reg = dict(self._s_defaults)

    @property
    def _guard_time(self) -> float:
        return self.s_reg.get(12, 50) / 50.0

    # -- emulator side -----------------------------------------------------

    def _accept_emu(self, server):
        conn, _ = server.accept()
        conn.setblocking(False)
        if self._emu is not None:
            # The emulator restarted: the old connection is dead, and any call
            # in progress died with the session that placed it.
            self._sel.unregister(self._emu)
            self._emu.close()
            self._drop_line(silent=True)
        self._emu = conn
        self._emu_in = bytearray()
        self._emu_out = bytearray()
        self._sel.register(conn, selectors.EVENT_READ, self._emu_event)
        self._send_status()

    def _emu_event(self, conn):
        try:
            data = conn.recv(4096)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            data = b""
        if not data:
            self._sel.unregister(conn)
            conn.close()
            self._emu = None
            self._drop_line(silent=True)
            return
        self._emu_in.extend(data)
        # Parse [tag][len][payload] frames; only 'D' arrives from the emulator.
        while len(self._emu_in) >= 2:
            length = self._emu_in[1]
            if len(self._emu_in) < 2 + length:
                break
            if self._emu_in[0] == ord("D"):
                self._handle_emu_bytes(bytes(self._emu_in[2:2 + length]))
            del self._emu_in[:2 + length]

    def _send_frames(self, payload: bytes, tag: bytes = b"D"):
        if self._emu is None:
            return
        out = bytearray()
        for i in range(0, len(payload), 255):
            chunk = payload[i:i + 255]
            out += tag + bytes([len(chunk)]) + chunk
        self._emu_out += out
        self._flush_emu()

    def _flush_emu(self):
        if self._emu is None:
            return
        if self._emu_out:
            try:
                sent = self._emu.send(self._emu_out)
                del self._emu_out[:sent]
            except (BlockingIOError, InterruptedError):
                pass
            except OSError:
                return
        events = selectors.EVENT_READ
        if self._emu_out:
            events |= selectors.EVENT_WRITE
        self._sel.modify(
            self._emu,
            events,
            self._emu_event if events == selectors.EVENT_READ else self._emu_rw_event,
        )

    def _emu_rw_event(self, conn):
        # Level-triggered: a single callback serves both directions.
        self._flush_emu()
        self._emu_event(conn)

    def _send_status(self):
        self._send_frames(bytes([self._carrier]), tag=b"S")

    def _result(self, code: str, extra: str = None):
        if self.quiet:
            return
        if self.verbose:
            text = extra if extra else code
            self._send_frames(b"\r\n" + text.encode() + b"\r\n")
        else:
            self._send_frames(str(_RESULT_CODES[code]).encode() + b"\r")

    def _info(self, text: str):
        self._send_frames(b"\r\n" + text.encode() + b"\r\n")

    # -- byte routing ------------------------------------------------------

    def _handle_emu_bytes(self, data: bytes):
        for byte in data:
            if self._state in (_COMMAND, _RINGING):
                self._command_byte(byte)
            elif self._state == _DIALING:
                # Any keystroke aborts a dial in progress, per Hayes.
                self._abort_dial()
            elif self._state == _ONLINE:
                self._online_byte(byte)

    def _command_byte(self, byte: int):
        if byte in (0x08, 0x7F):
            if self._cmd_buf:
                self._cmd_buf.pop()
                if self.echo:
                    self._send_frames(b"\x08 \x08")
            return
        if self.echo:
            self._send_frames(bytes([byte]))
        if byte == 0x0D:
            line = self._cmd_buf.decode("ascii", errors="replace").strip()
            self._cmd_buf = bytearray()
            if line:
                self._run_at_line(line)
        elif byte != 0x0A:
            self._cmd_buf.append(byte)

    def _online_byte(self, byte: int):
        now = time.monotonic()
        escape_char = self.s_reg.get(2, 43)
        if byte == escape_char and (
            self._plus_count > 0 or now - self._last_emu_byte >= self._guard_time
        ):
            self._plus_count += 1
            self._plus_pending.append(byte)
            if self._plus_count > 3:
                self._flush_pluses()
        else:
            self._flush_pluses()
            self._to_remote(bytes([byte]))
        self._last_emu_byte = now

    def _flush_pluses(self):
        if self._plus_pending:
            self._to_remote(bytes(self._plus_pending))
            self._plus_pending = bytearray()
        self._plus_count = 0

    def _to_remote(self, data: bytes):
        if self._remote is None:
            return
        if self._telnet:
            data = data.replace(bytes([_IAC]), bytes([_IAC, _IAC]))
        try:
            self._remote.sendall(data)
        except OSError:
            self._drop_line()

    # -- AT command parsing ------------------------------------------------

    def _run_at_line(self, line: str):
        if line[:2].upper() != "AT":
            self._result("ERROR")
            return
        rest = line[2:]
        i = 0
        while i < len(rest):
            char = rest[i].upper()
            if char == " ":
                i += 1
                continue
            if char == "D":
                # Dial consumes the remainder of the line, per Hayes.
                self._dial(rest[i + 1:])
                return
            if char == "A" and rest[i + 1:i + 2] != "/":
                self._answer()
                return
            i += 1
            digits = ""
            while i < len(rest) and rest[i].isdigit():
                digits += rest[i]
                i += 1
            if char == "E":
                self.echo = digits != "0"
            elif char == "Q":
                self.quiet = digits == "1"
            elif char == "V":
                self.verbose = digits != "0"
            elif char == "H":
                if self._remote:
                    self._drop_line(silent=True)
            elif char == "O":
                if self._carrier and self._remote:
                    self._go_online()
                    return
                self._result("NO CARRIER")
                return
            elif char == "Z":
                if self._remote:
                    self._drop_line(silent=True)
                self._reset_profile()
            elif char == "S":
                i = self._at_s_register(rest, i, digits)
                if i < 0:
                    self._result("ERROR")
                    return
            elif char == "I":
                self._info("RunCPM SIO/MODEM BRIDGE")
            elif char == "&":
                if i < len(rest) and rest[i].isalpha():
                    i += 1
                    while i < len(rest) and rest[i].isdigit():
                        i += 1
                else:
                    self._result("ERROR")
                    return
            elif char in "BCFLMNPTWXY":
                pass  # classic knobs (speaker, duplex, ...): accept and ignore
            else:
                self._result("ERROR")
                return
        self._result("OK")

    def _at_s_register(self, rest: str, i: int, digits: str) -> int:
        """Parse Sn=v / Sn? starting after the digits; return new index or -1."""
        if not digits:
            return -1
        reg = int(digits)
        if rest[i:i + 1] == "?":
            self._info("%03d" % self.s_reg.get(reg, 0))
            return i + 1
        if rest[i:i + 1] == "=":
            i += 1
            value = ""
            while i < len(rest) and rest[i].isdigit():
                value += rest[i]
                i += 1
            if not value:
                return -1
            self.s_reg[reg] = int(value)
            return i
        return -1

    # -- dialing and answering ---------------------------------------------

    def _resolve_dial(self, dial_str: str):
        """A dial string names a phonebook entry or a literal host[:port]."""
        target = dial_str.strip()
        if target[:1].upper() in ("T", "P"):  # ATDT / ATDP tone-pulse modifier
            target = target[1:].strip()
        cleaned = _DIAL_MODIFIERS.sub("", target)
        entry = self.phonebook.get(cleaned)
        if entry is not None:
            if isinstance(entry, str):
                entry = {"host": entry}
            host, _, port = entry["host"].partition(":")
            port = int(entry.get("port", port or 23))
            telnet = entry.get("telnet")
        elif re.search(r"[A-Za-z.:]", target):
            host, _, port = target.partition(":")
            port = int(port or 23)
            telnet = None
        else:
            return None  # a bare "phone number" we have no mapping for
        if telnet is None:
            telnet = True if port == 23 else self.telnet_default
        return host, port, telnet

    def _dial(self, dial_str: str):
        target = self._resolve_dial(dial_str)
        if target is None:
            self._result("NO CARRIER")
            return
        host, port, telnet = target
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setblocking(False)
        try:
            err = sock.connect_ex((host, port))
        except OSError:
            sock.close()
            self._result("NO CARRIER")
            return
        if err not in (0, errno.EINPROGRESS, errno.EWOULDBLOCK):
            sock.close()
            self._result("BUSY" if err == errno.ECONNREFUSED else "NO CARRIER")
            return
        self._remote = sock
        self._remote_label = f"{host}:{port}"
        self._telnet = telnet
        self._state = _DIALING
        self._dial_deadline = time.monotonic() + self.s_reg.get(7, 30)
        self._sel.register(sock, selectors.EVENT_WRITE, self._dial_event)

    def _dial_event(self, sock):
        err = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if err == 0:
            self._go_online(fresh=True)
        else:
            self._sel.unregister(sock)
            sock.close()
            self._remote = None
            self._state = _COMMAND
            self._result("BUSY" if err == errno.ECONNREFUSED else "NO CARRIER")

    def _abort_dial(self):
        self._sel.unregister(self._remote)
        self._remote.close()
        self._remote = None
        self._state = _COMMAND
        self._result("NO CARRIER")

    def _accept_call(self, listener):
        conn, addr = listener.accept()
        if self._remote is not None or self._state != _COMMAND or self._emu is None:
            conn.close()  # busy signal: one line, one call
            return
        conn.setblocking(False)
        self._remote = conn
        self._remote_label = f"{addr[0]}:{addr[1]}"
        self._telnet = self.telnet_default
        self._state = _RINGING
        self._ring_count = 0
        self._next_ring = time.monotonic()
        self._sel.register(conn, selectors.EVENT_READ, self._ringing_event)

    def _ringing_event(self, conn):
        # Only watch for the caller giving up; their data waits until we answer.
        try:
            peek = conn.recv(1, socket.MSG_PEEK)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            peek = b""
        if peek == b"":
            self._sel.unregister(conn)
            conn.close()
            self._remote = None
            self._state = _COMMAND
        else:
            self._sel.unregister(conn)  # data waiting; stop the level-trigger spin

    def _answer(self):
        if self._state != _RINGING or self._remote is None:
            self._result("ERROR")
            return
        self._go_online(fresh=True, answering=True)

    def _go_online(self, fresh: bool = False, answering: bool = False):
        sock = self._remote
        try:
            self._sel.unregister(sock)
        except KeyError:
            pass
        self._sel.register(sock, selectors.EVENT_READ, self._remote_event)
        self._state = _ONLINE
        self._carrier = 1
        if fresh:
            self._rx_queue = bytearray()
            self._tn_state = 0
            self._pace_allowance = 0.0
            self._pace_last = time.monotonic()
        self._plus_count = 0
        self._plus_pending = bytearray()
        self._last_emu_byte = time.monotonic()
        self._send_status()
        self._result("CONNECT", extra="CONNECT" if self.baud == 0 else f"CONNECT {self.baud}")

    def _remote_event(self, sock):
        try:
            data = sock.recv(4096)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            data = b""
        if not data:
            self._drop_line()
            return
        if self._telnet:
            data = self._telnet_filter(data)
        self._rx_queue += data
        self._deliver_rx()

    def _drop_line(self, silent: bool = False):
        """The call ended: remote hung up, ATH, or the emulator went away."""
        if self._remote is not None:
            try:
                self._sel.unregister(self._remote)
            except KeyError:
                pass
            self._remote.close()
            self._remote = None
        had_carrier = self._carrier
        self._state = _COMMAND
        self._carrier = 0
        self._rx_queue = bytearray()
        self._send_status()
        if not silent and had_carrier:
            self._result("NO CARRIER")

    # -- delivery to the emulator: pacing and telnet -----------------------

    def _deliver_rx(self):
        """Move queued remote bytes to the emulator, honoring baud pacing.

        Delivery pauses while escaped to command mode (+++); ATO drains the
        backlog. The queue is capped so a chatty peer can't grow it forever.
        """
        if self._state != _ONLINE:
            del self._rx_queue[65536:]
            return
        if self.baud <= 0:
            if self._rx_queue:
                self._send_frames(bytes(self._rx_queue))
                self._rx_queue = bytearray()
            return
        now = time.monotonic()
        self._pace_allowance += (now - self._pace_last) * (self.baud / 10.0)
        self._pace_last = now
        allowed = int(self._pace_allowance)
        if allowed <= 0:
            return
        burst = bytes(self._rx_queue[:allowed])
        if burst:
            del self._rx_queue[:len(burst)]
            self._pace_allowance -= len(burst)
            self._send_frames(burst)
        else:
            self._pace_allowance = min(self._pace_allowance, 1.0)

    def _telnet_filter(self, data: bytes) -> bytes:
        """Strip telnet option negotiation, refusing everything offered."""
        out = bytearray()
        reply = bytearray()
        for byte in data:
            if self._tn_state == 0:
                if byte == _IAC:
                    self._tn_state = 1
                else:
                    out.append(byte)
            elif self._tn_state == 1:
                if byte == _IAC:
                    out.append(_IAC)
                    self._tn_state = 0
                elif byte in (_DO, _DONT, _WILL, _WONT):
                    self._tn_cmd = byte
                    self._tn_state = 2
                elif byte == _SB:
                    self._tn_state = 3
                else:
                    self._tn_state = 0  # NOP, GA, ... two-byte commands
            elif self._tn_state == 2:
                if self._tn_cmd == _DO:
                    reply += bytes([_IAC, _WONT, byte])
                elif self._tn_cmd == _WILL:
                    reply += bytes([_IAC, _DONT, byte])
                self._tn_state = 0
            elif self._tn_state == 3:
                if byte == _IAC:
                    self._tn_state = 4
            elif self._tn_state == 4:
                self._tn_state = 3 if byte != _SE else 0
        if reply and self._remote is not None:
            try:
                self._remote.sendall(bytes(reply))
            except OSError:
                pass
        return bytes(out)

    # -- timers ------------------------------------------------------------

    def _tick(self):
        now = time.monotonic()
        if self._state == _ONLINE:
            if self._plus_count == 3 and now - self._last_emu_byte >= self._guard_time:
                self._plus_count = 0
                self._plus_pending = bytearray()
                self._state = _COMMAND  # escaped; carrier stays up for ATO
                self._result("OK")
            self._deliver_rx()
        elif self._state == _DIALING:
            if now > self._dial_deadline:
                self._abort_dial()
        elif self._state == _RINGING:
            if now >= self._next_ring:
                self._next_ring = now + _RING_INTERVAL
                self._ring_count += 1
                if self._ring_count > _RING_GIVE_UP:
                    try:
                        self._sel.unregister(self._remote)
                    except KeyError:
                        pass
                    self._remote.close()
                    self._remote = None
                    self._state = _COMMAND
                    return
                self._result("RING")
                auto = self.s_reg.get(0, 0)
                if auto > 0 and self._ring_count >= auto:
                    self._go_online(fresh=True, answering=True)
