import os
import asyncio
import json
import traceback
from dotenv import load_dotenv
from hyundai_kia_connect_api import VehicleManager

load_dotenv()

USERNAME = os.getenv("BLUELINK_USERNAME")
PASSWORD = os.getenv("BLUELINK_PASSWORD")
PIN = os.getenv("BLUELINK_PIN")
VIN = os.getenv("BLUELINK_VIN")
REGION_ID = 1  # 1 = Europe
BRAND_ID = 2   # 2 = Hyundai

if not all([USERNAME, PASSWORD, PIN, VIN]):
    print("❌ ERROR: One or more environment variables are missing from the .env file!")
    exit()

print("✅ All environment variables loaded successfully.")
print(f"   - VIN: {VIN}")

async def main():
    """Main function to test with the VehicleManager."""
    try:
        vm = VehicleManager(
            region=REGION_ID,
            brand=BRAND_ID,
            username=USERNAME,
            password=PASSWORD,
            pin=PIN
        )

        print("\n[INFO] Starting token check and login...")
        vm.check_and_refresh_token()
        print("✅ SUCCESS: Login and token refresh was successful!")

        print("\n[INFO] Fetching vehicle data...")
        vm.update_all_vehicles_with_cached_state()

        my_vehicle = None
        for vehicle in vm.vehicles.values():
            # --- THIS IS THE FIX ---
            # Use uppercase VIN as suggested by the error message
            if vehicle.VIN == VIN:
            # -----------------------
                my_vehicle = vehicle
                break

        if not my_vehicle:
            print(f"❌ ERROR: Vehicle with VIN {VIN} was not found in the account vehicles list!")
            print("Available vehicles found:")
            for vehicle in vm.vehicles.values():
                # --- Also fix here for the error message ---
                print(f"  - Name: {vehicle.name}, VIN: {vehicle.VIN}")
                # ------------------------------------------
            return

        print(f"✅ SUCCESS: Vehicle '{my_vehicle.name}' found.")
        # Let's check a few common attributes - names might differ slightly in this library
        # Use getattr with default values to prevent errors if attributes are missing
        soc = getattr(my_vehicle, 'soc_in_percent', 'N/A')
        range_km = getattr(my_vehicle, 'ev_driving_range_in_km', 'N/A')
        odometer_km = getattr(my_vehicle, 'odometer_in_km', 'N/A')

        print(f"   - State of Charge (SoC): {soc}%")
        print(f"   - Range: {range_km} km")
        print(f"   - Odometer: {odometer_km} km")

        print("\n[INFO] Complete vehicle status (raw data):")
        # The raw data is usually in a .data attribute
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