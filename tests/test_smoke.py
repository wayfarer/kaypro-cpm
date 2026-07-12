"""End-to-end smoke tests: boot each machine and drive it through real work.

Stdlib only, per the project's no-external-dependencies rule.

Run with:  make test   (or: python -m unittest discover -s tests)

These need the native binary (`make native`) and are skipped without it.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import RUNCPM, machine_names, resolve_machine  # noqa: E402
from harness.daemon import handle  # noqa: E402
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


@unittest.skipUnless(os.path.exists(RUNCPM), "native RunCPM not built — run: make native")
class SmokeTest(unittest.TestCase):
    """Runs against every machine under machines/."""

    def _artifacts(self, machine_dir):
        drive_b = os.path.join(machine_dir, "B", "0")
        return [os.path.join(drive_b, f"{STEM}.{ext}") for ext in ("FOR", "REL", "COM")]

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
                session = CPMSession(machine_dir)
                try:
                    self._check_dir(session)
                    self._check_no_output_lag(session)
                    self._check_fortran(session, machine_dir)
                finally:
                    session.close()
                    self._cleanup(machine_dir)

    def _check_dir(self, session):
        listing = session.run("DIR")
        self.assertIn("A:", listing)
        # The echoed command and the emulator's warm-boot banner are chrome,
        # and must never reach the caller.
        self.assertNotIn("DIR\n", listing)
        self.assertNotIn("RunCPM Version", listing)

    def _check_no_output_lag(self, session):
        """Each command must return its own output and nothing else.

        Guards the bug where a stray prompt left unread in the pty buffer
        surfaced at the head of the *next* command's output.
        """
        session.run("DIR")
        # A literal 'Ok' in program output used to be mistaken for MBASIC's
        # prompt and cut the read short.
        session.run("MBASIC")
        self.assertEqual(session.run('PRINT "Ok computer"'), "Ok computer")
        self.assertEqual(session.run("PRINT 6*7"), "42")
        session.run("SYSTEM")
        self.assertIn("A:", session.run("DIR"))

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
