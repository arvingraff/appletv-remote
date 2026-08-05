"""Run this on the Pi to pair with Apple TV: .venv-pi/bin/python3 pair_pi.py"""
import asyncio, pyatv

APPLE_TV_ID = "12:FD:8F:CE:56:74"

async def main():
    print("Scanning for Apple TV...")
    devices = await pyatv.scan(asyncio.get_event_loop(), identifier=APPLE_TV_ID)
    if not devices:
        print("Apple TV not found! Make sure Pi and Apple TV are on the same network.")
        return

    print(f"Found: {devices[0].name}")

    for protocol in [pyatv.Protocol.Companion, pyatv.Protocol.AirPlay]:
        print(f"\nPairing {protocol.name}...")
        pairing = await pyatv.pair(devices[0], protocol, asyncio.get_event_loop())
        await pairing.begin()
        pin = input("Enter PIN shown on Apple TV screen: ")
        pairing.pin(int(pin))
        await pairing.finish()
        print(f"{protocol.name} credentials: {pairing.service.credentials}")
        await pairing.close()

    print("\nDone! Copy the credentials above into appletv_server.py")

asyncio.run(main())
