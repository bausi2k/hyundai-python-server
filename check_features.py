import os
import asyncio
import json
from dotenv import load_dotenv
from hyundai_kia_connect_api import VehicleManager

# Lade Umgebungsvariablen
load_dotenv()
USERNAME = os.getenv("BLUELINK_USERNAME")
PASSWORD = os.getenv("BLUELINK_PASSWORD")
PIN = os.getenv("BLUELINK_PIN")
REGION = int(os.getenv("BLUELINK_REGION_ID", 1))
BRAND = int(os.getenv("BLUELINK_BRAND_ID", 2))

async def inspect_vehicle():
    print("🔄 Logging in...")
    vm = VehicleManager(region=REGION, brand=BRAND, username=USERNAME, password=PASSWORD, pin=PIN)
    vm.check_and_refresh_token()
    print("🔄 Updating vehicle status...")
    vm.update_all_vehicles_with_cached_state()
    
    if not vm.vehicles:
        print("❌ No vehicles found.")
        return

    # Wir nehmen das erste Auto
    vehicle_id = next(iter(vm.vehicles))
    vehicle = vm.vehicles[vehicle_id]
    
    print(f"\n🚘 INSPECTING: {vehicle.name} ({vehicle.model})")
    print("="*60)

    # Rohdaten abrufen
    # Die Library speichert das rohe JSON oft in 'vehicle.data' (ein Dictionary)
    raw_data = getattr(vehicle, 'data', {})
    
    # 1. Klimaanlage & Heizung
    print("\n[CLIMATE FEATURES]")
    # Wir suchen im JSON nach Schlüsseln, die auf Features hindeuten
    # Die Struktur kann variieren, daher suchen wir "generisch"
    def find_key(data, target):
        if isinstance(data, dict):
            for k, v in data.items():
                if target.lower() in k.lower():
                    print(f"  - Found '{k}': {v}")
                find_key(v, target)
        elif isinstance(data, list):
            for item in data:
                find_key(item, target)

    print("Checking for 'Steering' (Lenkrad):")
    find_key(raw_data, "Steering")
    
    print("\nChecking for 'Seat' (Sitze):")
    find_key(raw_data, "Seat")
    
    print("\nChecking for 'Mirror' (Spiegel):")
    find_key(raw_data, "Mirror")
    
    print("\nChecking for 'Defrost'/'Defog':")
    find_key(raw_data, "Defog")
    
    print("\n" + "="*60)
    print("TIPP: Wenn oben bei 'Seat' oder 'Steering' Werte wie '0' oder '1' stehen")
    print("oder Objekte wie {'state': 0} gefunden wurden, unterstützt dein Auto die Status-Anzeige.")
    print("Ob es STEUERUNG unterstützt, probierst du am besten einfach aus.")

if __name__ == "__main__":
    asyncio.run(inspect_vehicle())