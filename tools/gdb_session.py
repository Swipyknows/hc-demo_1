"""Milestone 1: QEMU + GDB debugging."""

from tools.target import Target


t = Target()

try:

    # Step 1: Compile firmware
    ok, out = t.build()

    print("\n========== BUILD ==========")

    print("SUCCESS" if ok else "FAILED")
    print(out)

    if not ok:
        raise RuntimeError("Firmware compilation failed")

    # Step 2: Start QEMU and GDB
    print("\n========== STARTING QEMU ==========")

    t.start()

    # Step 3: Execute firmware
    print("\n========== EXECUTION ==========")

    status = t.run()

    print("Status:", status)

    # Step 4: Capture UART
    print("\n========== UART OUTPUT ==========")

    print(t.read_uart())

    # Step 5: Inspect fault registers
    print("\n========== FAULT REGISTERS ==========")

    print(t.fault_registers())

    # Step 6: Inspect processor registers
    print("\n========== CPU REGISTERS ==========")

    print(t.cmd("info registers"))

    # Step 7: Inspect backtrace
    print("\n========== BACKTRACE ==========")

    print(t.cmd("bt"))

finally:

    t.stop()