import os
import asyncio
import json
import traceback
import logging # Using logging module for better log management
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from hyundai_kia_connect_api import VehicleManager, ClimateRequestOptions, exceptions as hke

# --- Basic Logging Setup ---
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(),
                    format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
load_dotenv()
USERNAME = os.getenv("BLUELINK_USERNAME")
PASSWORD = os.getenv("BLUELINK_PASSWORD")
PIN = os.getenv("BLUELINK_PIN")
VIN = os.getenv("BLUELINK_VIN")
REGION_ID = int(os.getenv("BLUELINK_REGION_ID", 1)) # Default to 1 (Europe)
BRAND_ID = int(os.getenv("BLUELINK_BRAND_ID", 2))   # Default to 2 (Hyundai)
SERVER_PORT = int(os.getenv("PORT", 8080))

# Validate essential config
if not all([USERNAME, PASSWORD, PIN, VIN]):
    logging.error("❌ ERROR: Missing essential environment variables in .env file (USERNAME, PASSWORD, PIN, VIN)!")
    exit()

# --- Global Vehicle Manager Instance ---
vm = None
try:
    logging.info("Initializing VehicleManager...")
    vm = VehicleManager(region=REGION_ID, brand=BRAND_ID, username=USERNAME, password=PASSWORD, pin=PIN)
    logging.info("Performing initial login/token refresh...")
    vm.check_and_refresh_token()
    logging.info("Performing initial vehicle cache update...")
    vm.update_all_vehicles_with_cached_state()
    # Check if our specific vehicle was found after initial update
    if VIN not in vm.vehicles:
        logging.warning(f"⚠️ WARNING: Vehicle with VIN {VIN} not found in initial vehicle list after login.")
        # Optionally, list available VINs if any exist
        if vm.vehicles:
            logging.warning(f"Available VINs: {list(vm.vehicles.keys())}")
        else:
            logging.warning("No vehicles found in the account at all.")
    logging.info("✅ SUCCESS: VehicleManager initialized and logged in.")
except hke.AuthenticationError as auth_err:
    logging.error(f"\n[FATAL] Authentication failed during startup! Check credentials.")
    logging.error(f"   - Error: {auth_err}")
    traceback.print_exc()
    exit()
except Exception as e:
    logging.error(f"\n[FATAL] Failed to initialize VehicleManager during startup!")
    logging.error(f"   - Error Type: {type(e)}")
    logging.error(f"   - Error Message: {e}")
    traceback.print_exc()
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
    # Log errors server-side
    if not success:
        logging.error(f"API Error ({status_code}) for '{endpoint_name}': {error_message}")
    return jsonify(response_body), status_code

# --- Helper: Find Vehicle ---
def find_vehicle(vin_to_find=VIN):
    """Finds the vehicle object by VIN. Raises ValueError if not found."""
    global vm
    if not vm or not vm.vehicles:
        logging.warning("find_vehicle called but vm or vm.vehicles not initialized.")
        raise ConnectionError("VehicleManager not initialized or vehicles not loaded.")

    # Try the library's built-in get_vehicle first (it might use VIN after update)
    vehicle = vm.get_vehicle(vin_to_find)
    if vehicle and vehicle.VIN == vin_to_find:
         logging.debug(f"find_vehicle: Found via vm.get_vehicle: {vehicle.name}")
         return vehicle

    # Fallback to iteration
    logging.debug("find_vehicle: Searching through vm.vehicles.values()...")
    for v in vm.vehicles.values():
        vehicle_vin = getattr(v, 'VIN', None)
        if vehicle_vin and vehicle_vin == vin_to_find:
            logging.debug(f"find_vehicle: Found via iteration: {v.name}")
            return v

    logging.error(f"find_vehicle: Vehicle with VIN {vin_to_find} not found.")
    raise ValueError(f"Vehicle with VIN {vin_to_find} not found.")

# --- Helper: Execute Async Vehicle Action ---
async def execute_vehicle_action(command, *args, **kwargs):
    """Refreshes token, finds vehicle, and runs an async action command."""
    global vm
    if not vm: raise ConnectionError("VehicleManager not initialized.")
    try:
        logging.debug(f"execute_vehicle_action: Refreshing token for command '{command}'...")
        vm.check_and_refresh_token() # Sync token refresh
        logging.debug("execute_vehicle_action: Token refreshed.")
        vehicle = find_vehicle() # Find vehicle by VIN
        method_to_call = getattr(vehicle, command)

        # Ensure method exists before calling
        if not callable(method_to_call):
             raise AttributeError(f"Vehicle object does not have a callable method named '{command}'.")

        if asyncio.iscoroutinefunction(method_to_call):
            logging.debug(f"Running ASYNC command on vehicle: {command}")
            result = await method_to_call(*args, **kwargs)
        else:
            # Should not happen for most actions, but handle sync case
            logging.debug(f"Running SYNC command on vehicle: {command}")
            result = method_to_call(*args, **kwargs)
        logging.debug(f"Command '{command}' executed successfully.")
        return result
    except Exception as e:
        logging.error(f"Exception during execute_vehicle_action for '{command}': {e}")
        # traceback.print_exc() # Keep this commented unless deep debugging needed
        raise e # Re-raise for the route handler to catch

# --- Helper: Force Refresh and Get Data ---
async def force_refresh_and_get_vehicle():
    """Forces update and returns the specific vehicle object."""
    global vm
    if not vm: raise ConnectionError("VehicleManager not initialized.")
    vm.check_and_refresh_token()
    logging.debug(f"Forcing refresh via vm.update_vehicle_with_latest_state({VIN})...")
    await vm.update_vehicle_with_latest_state(VIN) # Correct refresh method on vm
    logging.debug("Refresh complete.")
    vehicle = find_vehicle() # Find vehicle again after refresh
    return vehicle


# --- API Endpoints ---
aapiInfo = {
  "description": "Hyundai/Kia Connect API Server (Python)",
  "version": "1.0.0", # <-- Update this line to 1.0.0
  "endpoints": [
    { "path": "/", "method": "GET", "description": "Shows welcome message and link to /info." },
    { "path": "/info", "method": "GET", "description": "Shows this API information." },
    { "path": "/status", "method": "GET", "description": "Gets cached vehicle status (updates cache first)." },
    { "path": "/status/refresh", "method": "GET", "description": "Forces refresh and gets live vehicle status." },
    # Removed /status/soc and /status/range
    { "path": "/lock", "method": "POST", "description": "Locks the vehicle." },
    { "path": "/unlock", "method": "POST", "description": "Unlocks the vehicle." },
    { "path": "/climate/start", "method": "POST", "description": "Starts climate control.", "body_example": { "temperature": 21, "defrost": False, "climate": True, "heating": True}, "notes": "Temperature in °C." },
    { "path": "/climate/stop", "method": "POST", "description": "Stops climate control." },
    { "path": "/charge/start", "method": "POST", "description": "Starts charging (EV/PHEV)." },
    { "path": "/charge/stop", "method": "POST", "description": "Stops charging (EV/PHEV)." },
    { "path": "/odometer", "method": "GET", "description": "Gets the odometer reading (forces refresh)." },
    { "path": "/location", "method": "GET", "description": "Gets the vehicle location (forces refresh)." }
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
        vm.check_and_refresh_token()
        logging.debug("Updating cache for /status route...")
        vm.update_all_vehicles_with_cached_state() # Update cache synchronously
        logging.debug("Cache update complete.")
        vehicle = find_vehicle()
        return create_response(endpoint_name, data=vehicle.data)
    except Exception as e:
        # Log specific error for this route
        logging.error(f"Exception during /status route:", exc_info=True)
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/status/refresh', methods=['GET'])
async def route_status_refresh():
    endpoint_name = "status_live"
    try:
        vehicle = await force_refresh_and_get_vehicle()
        return create_response(endpoint_name, data=vehicle.data)
    except Exception as e:
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

# --- Action Routes ---
@app.route('/lock', methods=['POST'])
async def route_lock():
    endpoint_name = "lock"
    try:
        result = await execute_vehicle_action("lock")
        return create_response(endpoint_name, data={"result": result})
    except Exception as e:
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/unlock', methods=['POST'])
async def route_unlock():
    endpoint_name = "unlock"
    try:
        result = await execute_vehicle_action("unlock")
        return create_response(endpoint_name, data={"result": result})
    except Exception as e:
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/climate/start', methods=['POST'])
async def route_climate_start():
    endpoint_name = "climate_start"
    try:
        if not vm: raise ConnectionError("VehicleManager not initialized.")
        vm.check_and_refresh_token()

        data = request.get_json(silent=True) or {}
        set_temp = data.get('temperature')
        defrost = data.get('defrost', False)
        climate = data.get('climate', True)
        heating = data.get('heating', False)

        temp_value_for_options = None
        if 'temperature' in data:
            if not isinstance(set_temp, (int, float)) or not (16 <= set_temp <= 30):
                 return create_response(endpoint_name, success=False, error_message="Invalid temperature value (expected number between 16-30).", status_code=400)
            temp_value_for_options = float(set_temp)

        climate_options = ClimateRequestOptions(
            set_temp=temp_value_for_options,
            defrost=bool(defrost),
            climate=bool(climate),
            heating=bool(heating)
        )

        vehicle = find_vehicle()
        vehicle_internal_id = vehicle.id
        if not vehicle_internal_id:
             return create_response(endpoint_name, success=False, error_message="Could not find internal vehicle ID.", status_code=500)

        logging.debug(f"Calling vm.start_climate for Vehicle ID {vehicle_internal_id} (VIN {VIN}) with options: {climate_options}")
        # Call method directly on vm, passing internal ID and options OBJECT
        result = vm.start_climate(vehicle_id=vehicle_internal_id, options=climate_options) # This is SYNCHRONOUS
        logging.debug("vm.start_climate executed.")
        return create_response(endpoint_name, data={"result": result})

    except Exception as e:
        logging.error(f"Exception during /climate/start route:", exc_info=True)
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/climate/stop', methods=['POST'])
async def route_climate_stop():
    endpoint_name = "climate_stop"
    try:
        if not vm: raise ConnectionError("VehicleManager not initialized.")
        vm.check_and_refresh_token()
        vehicle = find_vehicle()
        vehicle_internal_id = vehicle.id
        if not vehicle_internal_id:
             return create_response(endpoint_name, success=False, error_message="Could not find internal vehicle ID.", status_code=500)

        logging.debug(f"Calling vm.stop_climate for Vehicle ID {vehicle_internal_id} (VIN {VIN})...")
        result = vm.stop_climate(vehicle_id=vehicle_internal_id) # This is SYNCHRONOUS
        logging.debug("vm.stop_climate executed.")
        return create_response(endpoint_name, data={"result": result})
    except Exception as e:
        logging.error(f"Exception during /climate/stop route:", exc_info=True)
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/charge/start', methods=['POST'])
async def route_charge_start():
    endpoint_name = "charge_start"
    try:
        result = await execute_vehicle_action("start_charge")
        return create_response(endpoint_name, data={"result": result})
    except Exception as e:
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/charge/stop', methods=['POST'])
async def route_charge_stop():
    endpoint_name = "charge_stop"
    try:
        result = await execute_vehicle_action("stop_charge")
        return create_response(endpoint_name, data={"result": result})
    except Exception as e:
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/odometer', methods=['GET'])
async def route_odometer():
    endpoint_name = "odometer"
    try:
        vehicle = await force_refresh_and_get_vehicle()
        odometer = getattr(vehicle, 'odometer_in_km', None)
        if odometer is None:
            return create_response(endpoint_name, success=False, error_message="Odometer data not available.", status_code=404)
        return create_response(endpoint_name, data={"odometer": odometer, "unit": "km"})
    except Exception as e:
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/location', methods=['GET'])
async def route_location():
    endpoint_name = "location"
    try:
        vehicle = await force_refresh_and_get_vehicle()
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

@app.errorhandler(404)
def route_not_found(e):
    return create_response("route_not_found", success=False, error_message="The requested endpoint does not exist. See /info.", status_code=404)

# Add a general error handler for unexpected server errors (500)
@app.errorhandler(Exception)
def handle_exception(e):
    # Log the full traceback for server-side debugging
    logging.error(f"Unhandled Exception: {e}", exc_info=True)
    # Return a generic 500 error response to the client
    return create_response("internal_server_error", success=False, error_message="An internal server error occurred.", status_code=500)


# --- Main Execution ---
if __name__ == '__main__':
    logging.info(f"Starting Flask server on http://0.0.0.0:{SERVER_PORT}...")
    # Consider using a production-ready WSGI server like waitress or gunicorn
    # For development/simple deployment, Flask's server is okay
    # Example using waitress (install with 'pip install waitress'):
    # from waitress import serve
    # serve(app, host='0.0.0.0', port=SERVER_PORT)
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False)