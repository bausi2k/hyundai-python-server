import os
import asyncio
import json
from dotenv import load_dotenv
from hyundai_kia_connect_api import HyundaiKiaConnect

load_dotenv()

USERNAME = os.getenv("BLUELINK_USERNAME")
PASSWORD = os.getenv("BLUELINK_PASSWORD")
PIN = os.getenv("BLUELINK_PIN")
VIN = os.getenv("BLUELINK_VIN")
REGION = os.getenv("BLUELINK_REGION")
BRAND = os.getenv("BLUELINK_BRAND")

if not all([USERNAME, PASSWORD, PIN, VIN, REGION, BRAND]):
    print("❌ FEHLER: Eine oder mehrere Umgebungsvariablen fehlen in der .env-Datei!")
    exit()

print("✅ Alle Umgebungsvariablen erfolgreich geladen.")
print(f"   - Region: {REGION}, Marke: {BRAND}")
print(f"   - VIN: {VIN}")

async def main():
    """Hauptfunktion zum Testen der Bibliothek."""
    try:
        client = HyundaiKiaConnect(
            username=USERNAME,
            password=PASSWORD,
            pin=PIN,
            region=REGION,
            brand=BRAND,
        )

        print("\n[INFO] Starte Login-Versuch...")
        await client.login()
        print("✅ SUCCESS: Login war erfolgreich!")

        print("\n[INFO] Rufe Fahrzeugdaten ab...")
        await client.update_all_vehicles_with_cached_state()

        my_vehicle = client.get_vehicle(VIN)
        if not my_vehicle:
            print(f"❌ FEHLER: Fahrzeug mit der VIN {VIN} wurde nicht im Account gefunden!")
            return

        print(f"✅ SUCCESS: Fahrzeug '{my_vehicle.name}' gefunden.")
        print(f"   - Ladestand (SoC): {my_vehicle.soc_in_percent}%")
        print(f"   - Reichweite: {my_vehicle.ev_driving_range_in_km} km")
        print(f"   - Kilometerstand: {my_vehicle.odometer_in_km} km")

        print("\n[INFO] Kompletter Fahrzeugstatus (Rohdaten):")
        print(json.dumps(my_vehicle.data, indent=2))

    except Exception as e:
        print(f"\n[FATAL] Ein Fehler ist aufgetreten: {e}")
    finally:
        if 'client' in locals():
            await client.logout()
            print("\n[INFO] Logout erfolgreich.")

if __name__ == "__main__":
    asyncio.run(main())