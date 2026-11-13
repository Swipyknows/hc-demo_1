"""Hidden evaluator: judges BEHAVIOUR of the submitted firmware. The agent never sees this file."""
from tools.target import Target

def evaluate(workspace):
    t = Target.__new__(Target); t.ws = workspace; t.qemu = t.gdb = None
    import os; t.uart_log = os.path.join(workspace, "uart.log")
    ok, out = t.build()
    if not ok: return "BUILD_FAIL", out
    t.start(); status = t.run(seconds=3); uart = t.read_uart(); t.stop()
    if status != "RAN_WITHOUT_FAULT": return "INT", f"still faults. UART={uart!r}"
    for must in ("boot ok", "rx ok", "init done"):
        if must not in uart: return "INT", f"missing {must!r} in UART={uart!r}"
    return "PASS", uart
