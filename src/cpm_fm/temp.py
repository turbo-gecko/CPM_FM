import sys
print("Python:", sys.executable)

try:
    import serial.tools.list_ports
    print("✅ pyserial imported successfully!")
except ImportError as e:
    print("❌ Failed to import pyserial:", e)
    exit(1)

ports = serial.tools.list_ports.comports()
if ports:
    print("\n🔌 Available serial ports:")
    for port in ports:
        print(f"  {port.device} - {port.description}")
else:
    print("\nNo serial ports found.")
