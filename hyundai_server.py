import os
import asyncio
import json
import traceback
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from hyundai_kia_connect_api import VehicleManager

# --- Configuration ---
load_dotenv()
USERNAME = os.getenv("BLUELINK_USERNAME")
PASSWORD = os.getenv("BLUELINK_PASSWORD")
PIN = os.getenv("BLUELINK_PIN")
VIN = os.getenv("BLUELINK_VIN")
REGION_ID = 1  # 1 = Europe
BRAND_ID = 2   # 2 = Hyundai
SERVER_PORT = int(os.getenv("PORT", 8080))

if not all([USERNAME, PASSWORD, PIN, VIN]):
    print("❌ ERROR: Missing environment variables in .env file!")
    exit()

# --- Global Vehicle Manager Instance ---
vm = None
try:
    print("[INFO] Initializing VehicleManager...")
    vm = VehicleManager(region=REGION_ID, brand=BRAND_ID, username=USERNAME, password=PASSWORD, pin=PIN)
    print("[INFO] Performing initial login/token refresh...")
    vm.check_and_refresh_token()
    vm.update_all_vehicles_with_cached_state() # Initial cache fill
    print("✅ SUCCESS: VehicleManager initialized and logged in.")
except Exception as e:
    print(f"\n[FATAL] Failed to initialize VehicleManager during startup!")
    traceback.print_exc()
    print("Server cannot start without successful initial login. Exiting.")
    exit()

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Helper Function for Consistent Responses ---
def create_response(endpoint_name, success=True, data=None, error_message=None, status_code=200):
    response_body = { "success": success, "command_invoked": endpoint_name }
    if success:
        response_body["message"] = f"{endpoint_name} successful."
        if data is not None: response_body["data"] = data
    else:
        response_body["error"] = f"Error during {endpoint_name}."
        if error_message: response_body["details"] = str(error_message)
    return jsonify(response_body), status_code

# --- Helper: Find Vehicle ---
def find_vehicle():
    global vm
    if not vm: raise ConnectionError("VehicleManager not initialized.")
    vehicle = vm.get_vehicle(VIN)
    if vehicle: return vehicle
    for v in vm.vehicles.values():
        if v.VIN == VIN: return v
    raise ValueError(f"Vehicle with VIN {VIN} not found.")

# --- Helper: Execute Async Vehicle Action ---
async def run_vehicle_action(command, *args, **kwargs):
    """Refreshes token, finds vehicle, and runs an async action command."""
    global vm
    if not vm: raise ConnectionError("VehicleManager not initialized.")
    try:
        vm.check_and_refresh_token()
        vehicle = find_vehicle()
        method_to_call = getattr(vehicle, command)

        if asyncio.iscoroutinefunction(method_to_call):
            print(f"[DEBUG] Running ASYNC command on vehicle: {command}")
            result = await method_to_call(*args, **kwargs)
        else:
            print(f"[DEBUG] Running SYNC command/attribute on vehicle: {command}")
            result = method_to_call(*args, **kwargs) if callable(method_to_call) else method_to_call
        return result
    except Exception as e:
        print(f"[ERROR] Exception during run_vehicle_action for '{command}': {e}")
        traceback.print_exc()
        raise e


# --- API Endpoints ---
apiInfo = {
  "description": "Hyundai/Kia Connect API Server (Python)", "version": "1.0.3",
  "endpoints": [
    { "path": "/", "method": "GET", "description": "Shows welcome message and link to /info." },
    { "path": "/info", "method": "GET", "description": "Shows this API information." },
    { "path": "/status", "method": "GET", "description": "Gets cached vehicle status." },
    { "path": "/status/refresh", "method": "GET", "description": "Forces refresh and gets live vehicle status." },
    { "path": "/status/soc", "method": "GET", "description": "Gets live State of Charge (SoC) in percent." },
    { "path": "/status/range", "method": "GET", "description": "Gets live driving range (DTE) in km." },
    { "path": "/lock", "method": "POST", "description": "Locks the vehicle." },
    { "path": "/unlock", "method": "POST", "description": "Unlocks the vehicle." },
    { "path": "/climate/start", "method": "POST", "description": "Starts climate control.", "body_example": { "temperature": 21, "defrost": False, "climate": True, "heating": True}, "notes": "Temperature in °C." },
    { "path": "/climate/stop", "method": "POST", "description": "Stops climate control." },
    { "path": "/charge/start", "method": "POST", "description": "Starts charging (EV/PHEV)." },
    { "path": "/charge/stop", "method": "POST", "description": "Stops charging (EV/PHEV)." },
    { "path": "/odometer", "method": "GET", "description": "Gets the odometer reading." },
    { "path": "/location", "method": "GET", "description": "Gets the vehicle location." }
  ]
}

@app.route('/', methods=['GET'])
def route_root():
    return create_response("root", data={"message": "Hyundai/Kia Connect Python Server running! See /info for endpoints."})

@app.route('/info', methods=['GET'])
def route_info():
    return create_response("info", data=apiInfo)

@app.route('/status', methods=['GET'])
async def route_status_cached():
    endpoint_name = "status_cached"
    try:
        if not vm: raise ConnectionError("VehicleManager not initialized.")
        print("[DEBUG] /status: Checking token...")
        vm.check_and_refresh_token()
        print("[DEBUG] /status: Updating cached state...")
        try:
            # --- Specific error handling around the update call ---
            vm.update_all_vehicles_with_cached_state() # Sync cache update
            print("[DEBUG] /status: Cached state updated successfully.")
        except KeyError as ke:
            # Catch KeyError specifically if it happens during the update
            print(f"[ERROR] KeyError during vm.update_all_vehicles_with_cached_state: {ke}")
            print("[ERROR] This likely indicates an internal library issue or inconsistent state related to VIN lookup.")
            traceback.print_exc()
            # Return a specific error message indicating the update failed
            return create_response(endpoint_name, success=False, error_message=f"Internal error during cache update (KeyError): {ke}", status_code=500)
        except Exception as update_err:
            # Catch any other error during update
            print(f"[ERROR] Exception during vm.update_all_vehicles_with_cached_state: {update_err}")
            traceback.print_exc()
            return create_response(endpoint_name, success=False, error_message=f"Internal error during cache update: {update_err}", status_code=500)
        # --- End specific error handling ---

        print("[DEBUG] /status: Searching for vehicle...")
        vehicle = None
        for v in vm.vehicles.values(): # Iterate through vehicle objects
            if v.VIN == VIN:           # Accesses the VIN attribute of the object
                vehicle = v
                break

        if not vehicle:
             print(f"[ERROR] /status: Vehicle {VIN} not found in vm.vehicles after update.")
             return create_response(endpoint_name, success=False, error_message=f"Vehicle {VIN} not found.", status_code=404)

        print("[DEBUG] /status: Vehicle found, returning data.")
        return create_response(endpoint_name, data=vehicle.data)
    except Exception as e:
        # Catch errors in the main try block (e.g., find_vehicle errors after successful update)
        print(f"[ERROR] General exception during /status route:")
        traceback.print_exc()
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/status/refresh', methods=['GET'])
async def route_status_refresh():
    endpoint_name = "status_live"
    try:
        if not vm: raise ConnectionError("VehicleManager not initialized.")
        vm.check_and_refresh_token()
        print(f"[DEBUG] Forcing refresh via vm.update_vehicle_with_latest_state({VIN})...")
        await vm.update_vehicle_with_latest_state(VIN)
        print(f"[DEBUG] Refresh complete.")
        vehicle = find_vehicle()
        return create_response(endpoint_name, data=vehicle.data)
    except Exception as e:
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/status/soc', methods=['GET'])
async def route_status_soc():
    endpoint_name = "status_soc"
    try:
        if not vm: raise ConnectionError("VehicleManager not initialized.")
        vm.check_and_refresh_token()
        print(f"[DEBUG] Forcing refresh via vm.update_vehicle_with_latest_state({VIN})...")
        await vm.update_vehicle_with_latest_state(VIN)
        print(f"[DEBUG] Refresh complete.")
        vehicle = find_vehicle()
        soc = getattr(vehicle, 'soc_in_percent', None)
        if soc is None: return create_response(endpoint_name, success=False, error_message="SoC data not available.", status_code=404)
        return create_response(endpoint_name, data={"soc": soc, "unit": "%"})
    except Exception as e:
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/status/range', methods=['GET'])
async def route_status_range():
    endpoint_name = "status_range"
    try:
        if not vm: raise ConnectionError("VehicleManager not initialized.")
        vm.check_and_refresh_token()
        print(f"[DEBUG] Forcing refresh via vm.update_vehicle_with_latest_state({VIN})...")
        await vm.update_vehicle_with_latest_state(VIN)
        print(f"[DEBUG] Refresh complete.")
        vehicle = find_vehicle()
        range_km = getattr(vehicle, 'ev_driving_range_in_km', getattr(vehicle, 'driving_range_in_km', None))
        if range_km is None: return create_response(endpoint_name, success=False, error_message="Range data not available.", status_code=404)
        return create_response(endpoint_name, data={"range": range_km, "unit": "km"})
    except Exception as e:
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/odometer', methods=['GET'])
async def route_odometer():
    endpoint_name = "odometer"
    try:
        if not vm: raise ConnectionError("VehicleManager not initialized.")
        vm.check_and_refresh_token()
        print(f"[DEBUG] Forcing refresh via vm.update_vehicle_with_latest_state({VIN})...")
        await vm.update_vehicle_with_latest_state(VIN)
        print(f"[DEBUG] Refresh complete.")
        vehicle = find_vehicle()
        odometer = getattr(vehicle, 'odometer_in_km', None)
        if odometer is None: return create_response(endpoint_name, success=False, error_message="Odometer data not available.", status_code=404)
        return create_response(endpoint_name, data={"odometer": odometer, "unit": "km"})
    except Exception as e:
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/location', methods=['GET'])
async def route_location():
    endpoint_name = "location"
    try:
        if not vm: raise ConnectionError("VehicleManager not initialized.")
        vm.check_and_refresh_token()
        print(f"[DEBUG] Forcing refresh via vm.update_vehicle_with_latest_state({VIN})...")
        await vm.update_vehicle_with_latest_state(VIN)
        print(f"[DEBUG] Refresh complete.")
        vehicle = find_vehicle()

        location_time = getattr(vehicle, 'location_last_updated_at', None)
        coords = getattr(vehicle, 'location_coordinate', None)

        if not location_time or not coords:
            return create_response(endpoint_name, success=False, error_message="Location data not available.", status_code=404)

        location_data = {
            "latitude": coords.latitude, "longitude": coords.longitude, "altitude": coords.altitude,
            "last_updated": location_time.isoformat() if location_time else None
        }
        return create_response(endpoint_name, data=location_data)
    except Exception as e:
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

# --- Action Routes ---
# --- FIX: Correct multi-line indentation ---
@app.route('/lock', methods=['POST'])
async def route_lock():
    endpoint_name = "lock"
    try:
        result = await run_vehicle_action("lock")
        return create_response(endpoint_name, data={"result": result})
    except Exception as e:
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/unlock', methods=['POST'])
async def route_unlock():
    endpoint_name = "unlock"
    try:
        result = await run_vehicle_action("unlock")
        return create_response(endpoint_name, data={"result": result})
    except Exception as e:
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/climate/start', methods=['POST'])
async def route_climate_start():
    endpoint_name = "climate_start"
    try:
        data = request.get_json()
        if not data or 'temperature' not in data:
            return create_response(endpoint_name, success=False, error_message="Missing 'temperature' in JSON body.", status_code=400)

        set_temp = data.get('temperature')
        defrost = data.get('defrost', False) 
        climate = data.get('climate', True)   
        heating = data.get('heating', True)   

        if not isinstance(set_temp, (int, float)) or not (16 <= set_temp <= 30):
             return create_response(endpoint_name, success=False, error_message="Invalid temperature value (expected number between 16-30).", status_code=400)

        result = await run_vehicle_action("start_climate", set_temp=set_temp, climate=climate, defrost=defrost, heating=heating)
        return create_response(endpoint_name, data={"result": result})
    except Exception as e:
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/climate/stop', methods=['POST'])
async def route_climate_stop():
    endpoint_name = "climate_stop"
    try:
        result = await run_vehicle_action("stop_climate")
        return create_response(endpoint_name, data={"result": result})
    except Exception as e:
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/charge/start', methods=['POST'])
async def route_charge_start():
    endpoint_name = "charge_start"
    try:
        result = await run_vehicle_action("start_charge")
        return create_response(endpoint_name, data={"result": result})
    except Exception as e:
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/charge/stop', methods=['POST'])
async def route_charge_stop():
    endpoint_name = "charge_stop"
    try:
        result = await run_vehicle_action("stop_charge")
        return create_response(endpoint_name, data={"result": result})
    except Exception as e:
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)
# --- End Fix ---

@app.errorhandler(404)
def route_not_found(e):
    return create_response("route_not_found", success=False, error_message="The requested endpoint does not exist. See /info.", status_code=404)

# --- Main Execution ---
if __name__ == '__main__':
    print(f"[INFO] Starting Flask server on http://0.0.0.0:{SERVER_PORT}...")
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False)