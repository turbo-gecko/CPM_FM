"""Standalone transport-port diagnostic for cpm-fm (throwaway; safe to delete).

Isolates the X-Modem transport link from the GUI so we can tell *where* a
transfer is failing: wrong COM device, dead cable, or the CP/M side simply not
responding to our start prompt.

Usage (run from the repo root, with the venv active):

    python tools/transport_diag.py                 # list available COM ports
    python tools/transport_diag.py COM5 --loopback # jumper TX<->RX, verify port
    python tools/transport_diag.py COM5            # listen mode (prompt + dump)

Options:
    --baud N     baud rate (default 9600)
    --seconds N  listen duration (default 30)
    --prompt c   start char to send while listening: 'C' (CRC) or 'N' (NAK)
"""

import argparse
import sys
import time

import serial
import serial.tools.list_ports


def list_ports() -> None:
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("No serial ports found.")
        return
    print("Available serial ports:")
    for p in ports:
        print(f"  {p.device:10}  {p.description}")


def loopback(port: str, baud: int) -> None:
    """Write a known pattern and read it back. Requires TX<->RX jumpered
    (DB9 pins 2-3) at the host end. Proves the COM device/driver works and the
    COM number is the one physically present."""
    pattern = bytes(range(0x20, 0x30))  # printable, easy to eyeball
    with serial.Serial(port, baud, timeout=1.0) as ser:
        ser.reset_input_buffer()
        ser.write(pattern)
        time.sleep(0.2)
        got = ser.read(len(pattern))
    print(f"sent {len(pattern)} bytes: {pattern!r}")
    print(f"read {len(got)} bytes: {got!r}")
    if got == pattern:
        print("PASS: loopback OK — this COM port and its adapter work.")
    elif not got:
        print("FAIL: nothing read back. Wrong COM port, no jumper, or dead adapter.")
    else:
        print("PARTIAL: data garbled — check the baud rate and adapter.")


def listen(port: str, baud: int, seconds: float, prompt: str) -> None:
    """Send an X-Modem start prompt periodically and dump anything received.
    Run this, then issue PCPUT on the CP/M side. If the cable/port are right,
    bytes from PCPUT appear here (look for 01=SOH or 02=STX)."""
    start_char = b"C" if prompt.upper().startswith("C") else b"\x15"
    label = "C (CRC)" if start_char == b"C" else "NAK (checksum)"
    print(f"Listening on {port} @ {baud} for {seconds:.0f}s, prompting with {label}.")
    print("Issue PCPUT on the CP/M side now. Ctrl-C to stop.\n")
    last_prompt = 0.0
    total = 0
    with serial.Serial(port, baud, timeout=0.2) as ser:
        ser.reset_input_buffer()
        end = time.time() + seconds
        while time.time() < end:
            now = time.time()
            if now - last_prompt >= 3.0:
                ser.write(start_char)
                last_prompt = now
                print(f"[{now:.1f}] -> sent prompt {start_char!r}")
            data = ser.read(256)
            if data:
                total += len(data)
                hexs = " ".join(f"{b:02X}" for b in data)
                print(f"[{time.time():.1f}] <- {len(data)} bytes: {hexs}")
    print(f"\nDone. Received {total} bytes total.")
    if total == 0:
        print("Nothing received: prompt isn't reaching the sender, wrong port, "
              "or PCPUT wasn't armed. Try --loopback to verify the port itself.")


def main() -> int:
    ap = argparse.ArgumentParser(description="cpm-fm transport-port diagnostic")
    ap.add_argument("port", nargs="?", help="COM port (omit to list ports)")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--loopback", action="store_true", help="TX<->RX jumper test")
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--prompt", default="C", help="start char: C or N")
    args = ap.parse_args()

    if not args.port:
        list_ports()
        return 0
    try:
        if args.loopback:
            loopback(args.port, args.baud)
        else:
            listen(args.port, args.baud, args.seconds, args.prompt)
    except serial.SerialException as e:
        print(f"Serial error: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
