"""Target = one firmware workspace + QEMU + GDB. Its methods are the agent tools.

A workspace is built from fw/common (startup code, board header, linker script,
Makefile) overlaid with one benchmark case directory (fw/bug_XXX, its main.c).
Only files in EDITABLE may ever be patched.
"""
import difflib
import os
import re
import shutil
import socket
import subprocess
import time

from pygdbmi.gdbcontroller import GdbController

COMMON_DIR = "fw/common"
EDITABLE = {"main.c"}                       # only these files may be patched
READABLE_EXT = (".c", ".h", ".ld")          # agent may read these (read-only unless EDITABLE)
NOT_COPIED = ("*.elf", "uart.log", "case.json")

# Run statuses returned by Target.run()
HARDFAULT = "HARDFAULT"                     # CPU entered HardFault_Handler
UNHANDLED = "UNHANDLED_EXCEPTION"           # CPU entered Default_Handler (no handler installed)
NO_FAULT = "NO_FAULT"                       # still running when the time window ended (then halted)

# Cortex-M fault status bits (ARMv7-M ARM, B3.2.15 / B3.2.16)
CFSR_BITS = {
    "IACCVIOL": 0, "DACCVIOL": 1, "MUNSTKERR": 3, "MSTKERR": 4, "MMARVALID": 7,       # MemManage
    "IBUSERR": 8, "PRECISERR": 9, "IMPRECISERR": 10, "UNSTKERR": 11, "STKERR": 12,    # BusFault
    "BFARVALID": 15,
    "UNDEFINSTR": 16, "INVSTATE": 17, "INVPC": 18, "NOCP": 19, "UNALIGNED": 24,       # UsageFault
    "DIVBYZERO": 25,
}
HFSR_BITS = {"VECTTBL": 1, "FORCED": 30, "DEBUGEVT": 31}
# GDB commands the agent may not run: shell escapes, scripting, file I/O, target control
BLOCKED_GDB = {"shell", "pipe", "python", "python-interactive", "pi", "py", "guile", "gu",
               "source", "define", "document", "dump", "append", "restore", "cd", "make",
               "file", "exec-file", "symbol-file", "add-symbol-file", "core-file", "target",
               "detach", "disconnect", "kill", "quit", "q", "run", "r", "start", "starti",
               "attach", "monitor", "load", "save", "generate-core-file", "gcore", "tui",
               "edit", "alias", "init-if-undefined", "eval", "with", "commands"}
EXCEPTION_NAMES = {2: "NMI", 3: "HardFault", 4: "MemManage", 5: "BusFault", 6: "UsageFault",
                   11: "SVCall", 14: "PendSV", 15: "SysTick"}


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def prepare_workspace(case_dir, workspace, common_dir=COMMON_DIR):
    """Fresh copy of common files + case files into `workspace`."""
    shutil.rmtree(workspace, ignore_errors=True)
    shutil.copytree(common_dir, workspace, ignore=shutil.ignore_patterns(*NOT_COPIED))
    shutil.copytree(case_dir, workspace, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*NOT_COPIED))
    return os.path.abspath(workspace)


class Target:
    def __init__(self, fw_src="fw/bug_001", workspace="workspaces/run", fresh=True):
        if fresh:
            prepare_workspace(fw_src, workspace)
        self.fw_src = fw_src
        self.ws = os.path.abspath(workspace)
        self.uart_log = os.path.join(self.ws, "uart.log")
        self.qemu = self.gdb = None
        self.port = None
        self.last_stop = None                   # info captured at the moment the CPU stopped
        self.patches = []                       # applied diffs, in order
        self._originals = {f: open(os.path.join(self.ws, f)).read()
                           for f in EDITABLE if os.path.exists(os.path.join(self.ws, f))}

    @classmethod
    def attach(cls, workspace):
        """Use an existing workspace as-is (no copy)."""
        return cls(workspace=workspace, fresh=False)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()

    # ---------- lifecycle ----------
    def build(self):
        subprocess.run(["make", "-C", self.ws, "-s", "clean"], capture_output=True)
        r = subprocess.run(["make", "-C", self.ws, "-s"], capture_output=True, text=True)
        return r.returncode == 0, (r.stdout + r.stderr).strip()

    def start(self):
        """Boot fw.elf in QEMU (halted at reset) and attach GDB."""
        self.stop()
        open(self.uart_log, "w").close()
        self.last_stop = None
        self.port = _free_port()
        self.qemu = subprocess.Popen(
            ["qemu-system-arm", "-machine", "netduino2", "-kernel", f"{self.ws}/fw.elf",
             "-nographic", "-serial", f"file:{self.uart_log}", "-monitor", "none",
             "-S", "-gdb", f"tcp:127.0.0.1:{self.port}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.gdb = GdbController(command=["gdb-multiarch", "--interpreter=mi3", "-q", "-nx"])
        self._mi("-gdb-set mi-async on")          # lets -exec-interrupt halt a running CPU
        self._mi(f"-file-exec-and-symbols {self.ws}/fw.elf")
        for _ in range(50):                                  # wait for the gdbstub, max ~5 s
            if self.qemu.poll() is not None:
                raise RuntimeError("QEMU exited: " + self.qemu.stderr.read().decode(errors="replace"))
            if any(m.get("message") == "connected"
                   for m in self._mi(f"-target-select remote 127.0.0.1:{self.port}", 3)):
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("could not connect GDB to QEMU")
        self._bp = {}
        for name in ("HardFault_Handler", "Default_Handler"):
            r = self._mi(f"-break-insert *{name}")
            for m in r:
                if m.get("message") == "done" and isinstance(m.get("payload"), dict):
                    self._bp[m["payload"]["bkpt"]["number"]] = name

    def stop(self):
        if self.gdb:
            try:
                self.gdb.exit()
            except Exception:
                pass
            self.gdb = None
        if self.qemu:
            self.qemu.terminate()
            try:
                self.qemu.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.qemu.kill()
                self.qemu.wait()
            self.qemu = None

    def _mi(self, c, timeout=5):
        return self.gdb.write(c, timeout_sec=timeout, raise_error_on_timeout=False)

    # ---------- agent tools ----------
    def cmd(self, c, timeout=10):
        """Run a GDB (CLI) command and return its console text."""
        if self.gdb is None:
            return "(target not running: call run_firmware / rebuild_and_run first)"
        r = self._mi(c, timeout)
        out = "".join(m["payload"] for m in r
                      if m["type"] in ("console", "log") and isinstance(m["payload"], str)
                      and m["payload"].strip() != c.strip())
        err = [m["payload"].get("msg") for m in r
               if m.get("message") == "error" and isinstance(m.get("payload"), dict)]
        return out + ("\n".join(f"error: {e}" for e in err if e))

    def gdb_command(self, c):
        """Agent-facing GDB access. Rejects commands that could escape the sandbox
        (shell, scripting, file I/O) or detach/replace the target."""
        c = c.strip()
        first = re.split(r"[\s/]", c, maxsplit=1)[0].lower()
        if not c or c[0] in "!|" or "|" in c or first in BLOCKED_GDB or first.startswith("-"):
            return f"REJECTED: '{c}' is not an allowed debugging command"
        if re.match(r"set\s+(logging|history|auto-load|pagination|confirm|remote)", c) \
                or re.search(r"\b(apply|commands)\b", c):
            return f"REJECTED: '{c}' is not an allowed debugging command"
        return self.cmd(c) or "(no output)"

    def run(self, seconds=3):
        """Continue the CPU for up to `seconds`. Returns HARDFAULT, UNHANDLED_EXCEPTION or
        NO_FAULT. In every case the CPU is halted afterwards so GDB can inspect it."""
        stopped = self._wait_stopped(self._mi("-exec-continue", 0.5), seconds)
        status = NO_FAULT
        if stopped is None:                                    # still running -> halt it
            stopped = self._wait_stopped(self._mi("-exec-interrupt", 0.5), 3)
        elif stopped.get("reason") == "breakpoint-hit":
            hit = self._bp.get(stopped.get("bkptno"))
            status = HARDFAULT if hit == "HardFault_Handler" else UNHANDLED if hit else NO_FAULT
        self.last_stop = self._capture_stop(status)
        return status

    def _wait_stopped(self, first, seconds):
        deadline, resp = time.time() + seconds, list(first)
        while True:
            for m in resp:
                if m.get("message") == "stopped" and isinstance(m.get("payload"), dict):
                    return m["payload"]
            if time.time() >= deadline:
                return None
            resp = self.gdb.get_gdb_response(timeout_sec=0.2, raise_error_on_timeout=False)

    def _capture_stop(self, status):
        """Snapshot what matters at the stop point (exception frame is only valid now)."""
        regs = self.registers()
        info = {"status": status, "pc": regs.get("pc"), "location": self._where(regs.get("pc"))}
        if status in (HARDFAULT, UNHANDLED):
            ipsr = int(regs.get("xpsr", "0"), 16) & 0x1FF
            info["exception"] = EXCEPTION_NAMES.get(ipsr, f"IRQ{ipsr - 16}" if ipsr >= 16 else str(ipsr))
            info["exception_number"] = ipsr
            if status == UNHANDLED:
                info["location"] = ("Default_Handler (startup.c): no handler is defined for the "
                                    f"active exception {info['exception']}, so it fell through to "
                                    "the weak default handler")
            exc_return = int(regs.get("lr", "0"), 16)
            sp = int(regs.get("psp" if exc_return & 0x4 else "msp", regs.get("sp", "0")), 16)
            frame = [self._word(sp + 4 * i) for i in range(8)]
            names = ["r0", "r1", "r2", "r3", "r12", "lr", "pc", "xpsr"]
            info["stacked_frame"] = {n: hex(v) for n, v in zip(names, frame)}
            info["faulting_pc"] = hex(frame[6])
            info["faulting_location"] = self._where(hex(frame[6]))
            info["caller_lr"] = hex(frame[5])
            info["caller_location"] = self._where(hex(frame[5] & ~1))
        return info

    def _where(self, addr):
        if not addr:
            return "?"
        sym = self.cmd(f"info symbol {addr}").strip()
        line = self.cmd(f"info line *{addr}").strip()
        m = re.search(r'Line (\d+) of "([^"]+)"', line)
        src = f"{os.path.basename(m.group(2))}:{m.group(1)}" if m else ""
        return " ".join(x for x in (sym if "No symbol" not in sym else "no symbol", src) if x)

    def _word(self, addr):
        try:
            return int(self.cmd(f"x/1wx {addr}").split()[-1], 16)
        except (ValueError, IndexError):
            return 0

    def registers(self):
        """Core registers as {name: hex string}."""
        regs = {}
        for line in self.cmd("info registers").splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1].startswith("0x"):
                regs[parts[0]] = parts[1]
        return regs

    def backtrace(self):
        return self.cmd("bt").strip()

    def fault_registers(self):
        """Decoded CFSR/HFSR/MMFAR/BFAR plus the exception frame captured at the stop."""
        cfsr, hfsr = self._word("0xE000ED28"), self._word("0xE000ED2C")
        mmfar, bfar = self._word("0xE000ED34"), self._word("0xE000ED38")
        out = {"CFSR": hex(cfsr), "HFSR": hex(hfsr)}
        out["active_flags"] = [k for k, b in CFSR_BITS.items() if cfsr >> b & 1] + \
                              [k for k, b in HFSR_BITS.items() if hfsr >> b & 1]
        if cfsr >> 7 & 1:
            out["MMFAR"] = hex(mmfar)
        if cfsr >> 15 & 1:
            out["BFAR"] = hex(bfar)
        if self.last_stop:
            out["stop"] = self.last_stop
        return out

    def read_uart(self):
        try:
            with open(self.uart_log, "rb") as f:
                return f.read().decode("utf-8", errors="replace")
        except FileNotFoundError:
            return ""

    def list_sources(self):
        return sorted(f for f in os.listdir(self.ws) if f.endswith(READABLE_EXT)) + ["Makefile"]

    def read_source(self, path="main.c", start=1, end=200):
        name = os.path.basename(path)
        if name not in self.list_sources():
            raise ValueError(f"{path} is not readable; available: {', '.join(self.list_sources())}")
        lines = open(os.path.join(self.ws, name)).read().splitlines()
        return "\n".join(f"{i}: {l}" for i, l in enumerate(lines, 1) if start <= i <= end)

    # ---------- patching ----------
    def make_patch(self, path, old, new):
        """Returns (diff, new_text) or raises ValueError. Does not write."""
        name = os.path.basename(path)
        if name not in EDITABLE:
            raise ValueError(f"{path} is not editable (editable: {', '.join(sorted(EDITABLE))})")
        text = open(os.path.join(self.ws, name)).read()
        if not old:
            raise ValueError("old text must not be empty")
        if text.count(old) != 1:
            raise ValueError(f"old text must match exactly once (found {text.count(old)})")
        new_text = text.replace(old, new)
        diff = "".join(difflib.unified_diff(text.splitlines(1), new_text.splitlines(1),
                                            f"a/{name}", f"b/{name}"))
        return diff, new_text

    def apply_patch(self, path, new_text, diff=""):
        name = os.path.basename(path)
        if name not in EDITABLE:
            raise ValueError(f"{path} is not editable")
        open(os.path.join(self.ws, name), "w").write(new_text)
        self.patches.append({"file": name, "diff": diff})

    def revert(self):
        """Restore every editable file to its original (buggy) content."""
        for name, text in self._originals.items():
            open(os.path.join(self.ws, name), "w").write(text)
        self.patches.clear()

    def total_diff(self):
        out = []
        for name, orig in self._originals.items():
            cur = open(os.path.join(self.ws, name)).read()
            out.append("".join(difflib.unified_diff(orig.splitlines(1), cur.splitlines(1),
                                                    f"a/{name}", f"b/{name}")))
        return "".join(out)

    def rebuild_and_run(self, seconds=3):
        ok, out = self.build()
        if not ok:
            self.stop()
            return {"build": "FAILED", "output": out}
        self.start()
        status = self.run(seconds)
        res = {"build": "OK", "status": status, "uart": self.read_uart()}
        if out:
            res["warnings"] = out
        if status != NO_FAULT:
            res["fault"] = self.fault_registers()
        return res
