"""End-to-end smoke tests: boot each machine and drive it through real work.

Stdlib only, per the project's no-external-dependencies rule.

Run with:  make test   (or: python -m unittest discover -s tests)

These need the native binary (`make native`) and are skipped without it.
"""
import os
import socket
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import RUNCPM, machine_names, resolve_machine  # noqa: E402
from harness.daemon import handle  # noqa: E402
from harness.modem import ModemEngine  # noqa: E402
from harness.session import CPMSession  # noqa: E402

FORTRAN_SRC = """\
      PROGRAM ZZSMOK
      WRITE (5,10)
10    FORMAT (1X,13HSMOKE TEST OK)
      STOP
      END
"""

# Kept distinct so a failed run can never clobber real work on B:.
STEM = "ZZSMOK"

# Drives the modem from MBASIC through the real SIO ports: INP/OUT against the
# patched emulator's status (RR0 bit0 = RX ready, bit2 = TX ready) and data
# ports. Sends each A$ then collects printable reply bytes until W$ appears
# (or an idle countdown expires), so assertions see exactly what CP/M saw.
MODEM_BAS = """\
10 D={data}:S={status}
20 W$="OK":A$="AT":GOSUB 500
30 W$="CONNECT":A$="ATDT 127.0.0.1:{port}":GOSUB 500
40 W$="PING":A$="PING":GOSUB 500
50 END
500 A$=A$+CHR$(13)
510 FOR I=1 TO LEN(A$)
520 IF (INP(S) AND 4)=0 THEN 520
530 OUT D,ASC(MID$(A$,I,1))
540 NEXT I
600 R$="":T=0
610 IF (INP(S) AND 1)=0 THEN 650
620 C=INP(D):T=0
630 IF C>31 THEN R$=R$+CHR$(C)
640 GOTO 610
650 T=T+1:IF INSTR(R$,W$)=0 AND T<30000 THEN 610
660 PRINT R$
670 RETURN
"""


@unittest.skipUnless(os.path.exists(RUNCPM), "native RunCPM not built — run: make native")
class SmokeTest(unittest.TestCase):
    """Runs against every machine under machines/."""

    def _artifacts(self, machine_dir):
        drive_b = os.path.join(machine_dir, "B", "0")
        paths = [os.path.join(drive_b, f"{STEM}.{ext}") for ext in ("FOR", "REL", "COM")]
        paths.append(os.path.join(drive_b, "ZZMODEM.BAS"))
        return paths

    def _cleanup(self, machine_dir):
        for path in self._artifacts(machine_dir):
            if os.path.exists(path):
                os.remove(path)

    def test_machines(self):
        machines = machine_names()
        self.assertTrue(machines, "no machines found under machines/")

        for name in machines:
            with self.subTest(machine=name):
                _, machine_dir = resolve_machine(name)
                self._cleanup(machine_dir)
                # Mirror the daemon: a machine with a modem.json gets a live
                # engine, and the emulator learns where the SIO lives via env.
                modem = ModemEngine.from_machine(machine_dir)
                if modem:
                    modem.start()
                session = CPMSession(machine_dir, env=modem.env() if modem else None)
                try:
                    self._check_dir(session)
                    self._check_no_output_lag(session, machine_dir)
                    self._check_modem(session, machine_dir, modem)
                    # Last: its skipTest aborts anything that would follow.
                    self._check_fortran(session, machine_dir)
                finally:
                    session.close()
                    if modem:
                        modem.stop()
                    self._cleanup(machine_dir)

    def _check_dir(self, session):
        listing = session.run("DIR")
        self.assertIn("A:", listing)
        # The echoed command and the emulator's warm-boot banner are chrome,
        # and must never reach the caller.
        self.assertNotIn("DIR\n", listing)
        self.assertNotIn("RunCPM Version", listing)

    def _check_no_output_lag(self, session, machine_dir):
        """Each command must return its own output and nothing else.

        Guards the bug where a stray prompt left unread in the pty buffer
        surfaced at the head of the *next* command's output.
        """
        if not os.path.exists(os.path.join(machine_dir, "A", "0", "MBASIC.COM")):
            return  # no MBASIC on this machine; the output-lag guard needs it

        session.run("DIR")
        # A literal 'Ok' in program output used to be mistaken for MBASIC's
        # prompt and cut the read short.
        session.run("MBASIC")
        self.assertEqual(session.run('PRINT "Ok computer"'), "Ok computer")
        self.assertEqual(session.run("PRINT 6*7"), "42")
        session.run("SYSTEM")
        self.assertIn("A:", session.run("DIR"))

    def _check_modem(self, session, machine_dir, modem):
        """AT dialogue and a dialed TCP round-trip, driven from MBASIC.

        Proves the whole chain: MBASIC INP/OUT -> patched SIO ports -> Unix
        socket -> ModemEngine -> TCP -> echo server and back.
        """
        if modem is None or not os.path.exists(
            os.path.join(machine_dir, "A", "0", "MBASIC.COM")
        ):
            return  # no modem or no MBASIC on this machine; nothing to drive

        received = bytearray()
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        def echo():
            conn, _ = listener.accept()
            with conn:
                while True:
                    data = conn.recv(4096)
                    if not data:
                        return
                    received.extend(data)
                    conn.sendall(data)

        echo_thread = threading.Thread(target=echo, daemon=True)
        echo_thread.start()

        try:
            env = modem.env()
            handle(
                {
                    "action": "write",
                    "filename": "ZZMODEM.BAS",
                    "content": MODEM_BAS.format(
                        data=env["CPM_SIO_DATA_PORT"],
                        status=env["CPM_SIO_STATUS_PORT"],
                        port=port,
                    ),
                },
                session,
                machine_dir,
            )
            session.run("MBASIC")
            session.run('LOAD "B:ZZMODEM"')
            out = session.run("RUN")
            session.run("SYSTEM")
            self.assertIn("OK", out, "modem did not answer AT")
            self.assertIn("CONNECT", out, "modem did not connect the call")
            self.assertIn("PING", out, "dialed connection did not round-trip")
            self.assertIn(b"PING\r", received, "echo server never got the payload")
        finally:
            listener.close()

    def _check_fortran(self, session, machine_dir):
        if not os.path.exists(os.path.join(machine_dir, "A", "0", "F80.COM")):
            self.skipTest("no FORTRAN-80 on this machine's A: drive")

        written = handle(
            {"action": "write", "filename": f"{STEM}.FOR", "content": FORTRAN_SRC},
            session,
            machine_dir,
        )
        self.assertIn(f"{STEM}.FOR", written)

        session.run(f"F80 =B:{STEM}")
        self.assertIn(
            f"{STEM}.REL",
            os.listdir(os.path.join(machine_dir, "B", "0")),
            "F80 did not produce a .REL",
        )

        link = session.run(f"L80 B:{STEM},A:FORLIB/S,B:{STEM}/N/E")
        self.assertIn("Link-80", link)

        # The payoff: an exact-match assertion. A lagged or contaminated
        # stream fails here, where a human would skim past it.
        self.assertEqual(session.run(f"B:{STEM}"), "SMOKE TEST OK STOP")


if __name__ == "__main__":
    unittest.main()
