import os
import asyncio
import json
import traceback
import inspect # Needed to inspect methods if desired
from dotenv import load_dotenv
from hyundai_kia_connect_api import VehicleManager

# --- Configuration ---
load_dotenv()
USERNAME = os.getenv("BLUELINK_USERNAME")
PASSWORD = os.getenv("BLUELINK_PASSWORD")
PIN = os.getenv("BLUELINK_PIN")
VIN = os.getenv("BLUELINK_VIN")
LANGUAGE = os.getenv("BLUELINK_LANGUAGE")
SERVER_PORT_STR = os.getenv("PORT", "8080") # Read PORT as string first

# --- FIX START: Read IDs as strings first ---
region_id_str = os.getenv("BLUELINK_REGION_ID")
brand_id_str = os.getenv("BLUELINK_BRAND_ID")
# --- FIX END ---

REGION_ID = None
BRAND_ID = None
SERVER_PORT = None

# Versuche, die IDs und den Port in Zahlen umzuwandeln
try:
    if region_id_str:
        REGION_ID = int(region_id_str) # Convert string to int
    if brand_id_str:
        BRAND_ID = int(brand_id_str)   # Convert string to int
    if SERVER_PORT_STR:
        SERVER_PORT = int(SERVER_PORT_STR) # Convert string to int

except ValueError as e:
    print(f"❌ ERROR: Ungültiger Zahlenwert in .env: {e}")
    print(f"   - Prüfe BLUELINK_REGION_ID ('{region_id_str}')")
    print(f"   - Prüfe BLUELINK_BRAND_ID ('{brand_id_str}')")
    print(f"   - Prüfe PORT ('{SERVER_PORT_STR}')")
    exit()

# Überprüfe, ob alle notwendigen Variablen vorhanden sind (inklusive der konvertierten IDs)
# Check for None for the integer variables, and directly check string variables
if not all([USERNAME, PASSWORD, PIN, VIN, REGION_ID is not None, BRAND_ID is not None, SERVER_PORT is not None, LANGUAGE]):
    print("❌ ERROR: Eine oder mehrere Umgebungsvariablen fehlen oder sind ungültig in der .env-Datei!")
    print(f"   - USERNAME: {'OK' if USERNAME else 'MISSING'}")
    print(f"   - PASSWORD: {'OK' if PASSWORD else 'MISSING'}")
    print(f"   - PIN: {'OK' if PIN else 'MISSING'}")
    print(f"   - VIN: {'OK' if VIN else 'MISSING'}")
    print(f"   - REGION_ID: {REGION_ID if REGION_ID is not None else 'MISSING/INVALID'}")
    print(f"   - BRAND_ID: {BRAND_ID if BRAND_ID is not None else 'MISSING/INVALID'}")
    print(f"   - LANGUAGE: {'OK' if LANGUAGE else 'MISSING'}")
    print(f"   - PORT: {SERVER_PORT if SERVER_PORT is not None else 'MISSING/INVALID'}")
    exit()

print("✅ All environment variables loaded and validated successfully.")
print(f"   - VIN: {VIN}")
print(f"   - Region ID: {REGION_ID}, Brand ID: {BRAND_ID}, Language: {LANGUAGE}")



async def main():
    """Main function to test with the VehicleManager."""
    vm = None # Define vm here for the finally block
    try:
        vm = VehicleManager(
            region=REGION_ID, # Übergibt jetzt die Zahl
            brand=BRAND_ID,   # Übergibt jetzt die Zahl
            username=USERNAME,
            password=PASSWORD,
            pin=PIN,
            language=LANGUAGE # Übergibt die Sprache
        )
        print("\n[INFO] Starting token check and login...")
        vm.check_and_refresh_token()
        print("✅ SUCCESS: Login and token refresh was successful!")

        # --- INSPECT THE VM OBJECT ---
        print("\n" + "="*20 + " Inspecting vm Object " + "="*20)
        print("Available attributes and methods (via dir()):")
        print([item for item in dir(vm) if not item.startswith('_')])

        print("\nAttributes and their values (via vars()):")
        try:
            vm_attributes = {}
            for key, value in vars(vm).items():
                if not key.startswith('_'):
                    if isinstance(value, (str, int, float, bool, list, dict, type(None))):
                        vm_attributes[key] = value
                    elif isinstance(value, object) and hasattr(value, '__class__'):
                        vm_attributes[key] = f"<Object of type {value.__class__.__name__}>"
                    else:
                        vm_attributes[key] = f"<Non-printable value of type {type(value).__name__}>"
            print(json.dumps(vm_attributes, indent=2, default=str))
        except Exception as inspect_err:
            print(f"Could not fully inspect vars(vm): {inspect_err}")
        print("="*60 + "\n")
        # --- END INSPECTION BLOCK ---


        print("\n[INFO] Fetching vehicle data...")
        vm.update_all_vehicles_with_cached_state()

        my_vehicle = None
        for vehicle in vm.vehicles.values():
            if vehicle.VIN == VIN:
                my_vehicle = vehicle
                break

        if not my_vehicle:
            print(f"❌ ERROR: Vehicle with VIN {VIN} was not found in the account vehicles list!")
            print("Available vehicles found:")
            for vehicle in vm.vehicles.values():
                print(f"  - Name: {vehicle.name}, VIN: {vehicle.VIN}")
            return

        print(f"✅ SUCCESS: Vehicle '{my_vehicle.name}' found.")
        soc = getattr(my_vehicle, 'soc_in_percent', 'N/A')
        range_km = getattr(my_vehicle, 'ev_driving_range_in_km', 'N/A')
        odometer_km = getattr(my_vehicle, 'odometer_in_km', 'N/A')

        print(f"   - State of Charge (SoC): {soc}%")
        print(f"   - Range: {range_km} km")
        print(f"   - Odometer: {odometer_km} km")

        print("\n[INFO] Complete vehicle status (raw data):")
        print(json.dumps(getattr(my_vehicle, 'data', {}), indent=2))

    except Exception as e:
        print(f"\n[FATAL] An error occurred!")
        print(f"   - Error Type: {type(e)}")
        print(f"   - Error Message: {e}")
        print("\n--- Full Error Traceback ---")
        traceback.print_exc()
        print("--------------------------")

if __name__ == "__main__":
    asyncio.run(main())