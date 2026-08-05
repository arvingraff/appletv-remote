"""Run this on the Pi to pair with Apple TV: .venv-pi/bin/python3 pair_pi.py"""
import asyncio, pyatv, re, os

APPLE_TV_ID = "12:FD:8F:CE:56:74"
SERVER_FILE  = os.path.join(os.path.dirname(__file__), "appletv_server.py")

async def main():
    print("Scanning for Apple TV...")
    loop = asyncio.get_event_loop()
    devices = await pyatv.scan(loop, identifier=APPLE_TV_ID)
    if not devices:
        print("Apple TV not found!")
        return

    print(f"Found: {devices[0].name}")
    creds = {}

    for protocol in [pyatv.Protocol.Companion, pyatv.Protocol.AirPlay]:
        print(f"\nPairing {protocol.name}...")
        pairing = await pyatv.pair(devices[0], protocol, loop)
        await pairing.begin()
        pin = input("Enter PIN shown on Apple TV screen: ")
        pairing.pin(int(pin))
        await pairing.finish()
        creds[protocol.name] = pairing.service.credentials
        print(f"Got {protocol.name} credentials ✅")
        await pairing.close()

    # Write credentials directly into appletv_server.py
    with open(SERVER_FILE, "r") as f:
        src = f.read()

    src = re.sub(
        r'COMPANION_CREDENTIALS = \(.*?\)',
        f'COMPANION_CREDENTIALS = (\n    "{creds["Companion"]}"\n)',
        src, flags=re.DOTALL)
    src = re.sub(
        r'AIRPLAY_CREDENTIALS = \(.*?\)',
        f'AIRPLAY_CREDENTIALS = (\n    "{creds["AirPlay"]}"\n)',
        src, flags=re.DOTALL)

    with open(SERVER_FILE, "w") as f:
        f.write(src)

    print("\n✅ Credentials saved to appletv_server.py automatically!")
    print("Now run: sudo systemctl restart appletv-remote")

asyncio.run(main())
