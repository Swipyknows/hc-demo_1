"""Target = one firmware workspace + QEMU + GDB. Its methods are the agent tools."""
import difflib, os, shutil, subprocess, time
from pygdbmi.gdbcontroller import GdbController

PORT = 1234
EDITABLE = {"main.c"}          # only these files may be patched

class Target:
    def __init__(self, fw_src="fw", workspace="workspaces/run"):
        shutil.rmtree(workspace, ignore_errors=True)
        shutil.copytree(fw_src, workspace, ignore=shutil.ignore_patterns("*.elf"))
        self.ws = os.path.abspath(workspace)
        self.uart_log = os.path.join(self.ws, "uart.log")
        self.qemu = self.gdb = None

    # ---------- lifecycle ----------
    def build(self):
        r = subprocess.run(["make", "-C", self.ws, "-s"], capture_output=True, text=True)
        return r.returncode == 0, (r.stdout + r.stderr).strip()

    def start(self):
        self.stop()
        open(self.uart_log, "w").close()
        self.qemu = subprocess.Popen(
            ["qemu-system-arm", "-machine", "netduino2", "-kernel", f"{self.ws}/fw.elf",
             "-nographic", "-serial", f"file:{self.uart_log}", "-monitor", "none",
             "-S", "-gdb", f"tcp::{PORT}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        self.gdb = GdbController(command=["gdb-multiarch", "--interpreter=mi3", "-q"])
        self.cmd(f"file {self.ws}/fw.elf"); self.cmd(f"target remote :{PORT}")

    def stop(self):
        if self.gdb: self.gdb.exit(); self.gdb = None
        if self.qemu: self.qemu.terminate(); self.qemu.wait(); self.qemu = None

    # ---------- agent tools ----------
    def cmd(self, c, timeout=10):
        r = self.gdb.write(c, timeout_sec=timeout, raise_error_on_timeout=False)
        return "".join(m["payload"] for m in r if m["type"] == "console" and isinstance(m["payload"], str))

    def run(self, seconds=3):
        # Set a temporary breakpoint to avoid accumulating
        # duplicate breakpoints on repeated executions.
        self.cmd("tbreak HardFault_Handler")

        # Continue firmware execution.
        response = self.gdb.write(
            "continue",
            timeout_sec=seconds,
            raise_error_on_timeout=False
        )

        # Check GDB asynchronous stop events.
        faulted = any(
            isinstance(m.get("payload"), dict)
            and m.get("message") == "stopped"
            and m["payload"].get("reason") == "breakpoint-hit"
            for m in response
        )

        # Fallback: inspect the current program-counter symbol.
        # This handles cases where the stop event wasn't captured
        # in the expected MI response format.
        if not faulted:
            try:
                symbol = self.cmd("info symbol $pc")
                faulted = "HardFault_Handler" in symbol
            except Exception:
                faulted = False

        if faulted:
            return "STOPPED_AT_HARDFAULT"

        return "RAN_WITHOUT_FAULT"

    def _word(self, addr):
        try:
            return int(self.cmd(f"x/1wx {addr}").split()[-1], 16)
        except (ValueError, IndexError):
            return 0

    def fault_registers(self):
        cfsr, hfsr = self._word("0xE000ED28"), self._word("0xE000ED2C")
        return {"CFSR": hex(cfsr), "HFSR": hex(hfsr), "INVSTATE": bool(cfsr & 1 << 17),
                "FORCED": bool(hfsr & 1 << 30), "IBUSERR": bool(cfsr & 1 << 0),
                "PRECISERR": bool(cfsr & 1 << 9), "UNDEFINSTR": bool(cfsr & 1 << 16)}

    def read_uart(self):
        return open(self.uart_log).read()

    def read_source(self, path="main.c", start=1, end=200):
        p = os.path.join(self.ws, os.path.basename(path))
        lines = open(p).read().splitlines()
        return "\n".join(f"{i}: {l}" for i, l in enumerate(lines, 1) if start <= i <= end)

    def make_patch(self, path, old, new):
        """Returns (diff, new_text) or raises ValueError. Does not write."""
        if os.path.basename(path) not in EDITABLE: raise ValueError(f"{path} is not editable")
        p = os.path.join(self.ws, os.path.basename(path)); text = open(p).read()
        if text.count(old) != 1: raise ValueError(f"old text must match exactly once (found {text.count(old)})")
        new_text = text.replace(old, new)
        diff = "".join(difflib.unified_diff(text.splitlines(1), new_text.splitlines(1), "before", "after"))
        return diff, new_text

    def apply_patch(self, path, new_text):
        open(os.path.join(self.ws, os.path.basename(path)), "w").write(new_text)

    def rebuild_and_run(self):
        ok, out = self.build()
        if not ok: return {"build": "FAILED", "output": out}
        self.start(); status = self.run()
        return {"build": "OK", "status": status, "uart": self.read_uart()}
