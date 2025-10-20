import os
import asyncio
import json
import traceback
import logging # Using logging module for better log management
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from hyundai_kia_connect_api import VehicleManager, ClimateRequestOptions, exceptions as hke

# --- Basic Logging Setup ---
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=log_level,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logging.info(f"Log level set to: {log_level}")

# --- Configuration ---
load_dotenv()
USERNAME = os.getenv("BLUELINK_USERNAME")
PASSWORD = os.getenv("BLUELINK_PASSWORD")
PIN = os.getenv("BLUELINK_PIN")
VIN = os.getenv("BLUELINK_VIN")
region_id_str = os.getenv("BLUELINK_REGION_ID", "1") # Default to 1 (Europe)
brand_id_str = os.getenv("BLUELINK_BRAND_ID", "2")   # Default to 2 (Hyundai)
SERVER_PORT_STR = os.getenv("PORT", "8080")          # Default to 8080

REGION_ID = None
BRAND_ID = None
SERVER_PORT = None

if not all([USERNAME, PASSWORD, PIN, VIN]):
    logging.error("❌ FATAL ERROR: Missing essential environment variables in .env file (USERNAME, PASSWORD, PIN, VIN)! Exiting.")
    exit()

try:
    REGION_ID = int(region_id_str)
    BRAND_ID = int(brand_id_str)
    SERVER_PORT = int(SERVER_PORT_STR)
    logging.info(f"Region ID: {REGION_ID}, Brand ID: {BRAND_ID}, Port: {SERVER_PORT}")
except ValueError as e:
    logging.error(f"❌ FATAL ERROR: Invalid numeric value in .env file: {e}. Exiting.")
    exit()


# --- Global Vehicle Manager Instance ---
vm = None
try:
    logging.info("Initializing VehicleManager...")
    vm = VehicleManager(region=REGION_ID, brand=BRAND_ID, username=USERNAME, password=PASSWORD, pin=PIN)
    logging.info("Performing initial login/token refresh...")
    vm.check_and_refresh_token()
    logging.info("Performing initial vehicle cache update...")
    vm.update_all_vehicles_with_cached_state() # Initial cache fill
    logging.info("✅ SUCCESS: VehicleManager initialized and logged in.")

    # Check if our specific vehicle was found using the reliable iteration method
    vehicle_found = False
    if vm.vehicles:
        for v in vm.vehicles.values():
            if getattr(v, 'VIN', None) == VIN:
                vehicle_found = True
                logging.info(f"✅ Vehicle with VIN {VIN} found in initial cache.")
                break
    if not vehicle_found:
        logging.warning(f"⚠️ WARNING: Vehicle with VIN {VIN} not found in initial vehicle list after login.")
        if vm.vehicles:
            logging.warning(f"Available VINs found: {[getattr(v, 'VIN', 'N/A') for v in vm.vehicles.values()]}")

except hke.AuthenticationError as auth_err:
    logging.error(f"\n[FATAL] Authentication failed during startup! Check credentials.", exc_info=False) # No need for full trace on auth fail
    exit()
except Exception as e:
    logging.error(f"\n[FATAL] Failed to initialize VehicleManager during startup!", exc_info=True)
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
        # Use warning level for client errors (4xx), error for server errors (5xx)
        log_method = logging.warning if 400 <= status_code < 500 else logging.error
        log_method(f"API Error ({status_code}) for '{endpoint_name}': {error_message}")
    return jsonify(response_body), status_code

# --- Helper: Find Vehicle ---
def find_vehicle(vin_to_find=VIN):
    """Finds the vehicle object by iterating through vm.vehicles and matching VIN."""
    global vm
    if not vm or not vm.vehicles:
        logging.warning("find_vehicle called but vm or vm.vehicles not initialized.")
        raise ConnectionError("VehicleManager not initialized or vehicles not loaded.")

    logging.debug(f"find_vehicle: Searching through {len(vm.vehicles)} cached vehicles for VIN {vin_to_find}...")
    for vehicle_obj in vm.vehicles.values():
        vehicle_vin = getattr(vehicle_obj, 'VIN', None)
        if vehicle_vin and vehicle_vin == vin_to_find:
            logging.debug(f"find_vehicle: Found match: {getattr(vehicle_obj, 'name', 'N/A')}")
            return vehicle_obj

    logging.error(f"find_vehicle: Vehicle with VIN {vin_to_find} not found in vm.vehicles.values().")
    logging.debug("find_vehicle: Available vehicles in cache:")
    for v_id, v_obj in vm.vehicles.items():
         v_vin_log = getattr(v_obj, 'VIN', 'N/A')
         v_name_log = getattr(v_obj, 'name', 'N/A')
         logging.debug(f"  - ID: {v_id}, Name: {v_name_log}, VIN: {v_vin_log}")
    raise ValueError(f"Vehicle with VIN {vin_to_find} not found.")

# --- Helper: Execute Async Vehicle Action ---
async def execute_vehicle_action(command, *args, **kwargs):
    """Refreshes token, finds vehicle, and runs an async action command."""
    global vm
    if not vm: raise ConnectionError("VehicleManager not initialized.")
    try:
        logging.debug(f"execute_vehicle_action: Starting for command '{command}'...")
        vm.check_and_refresh_token()
        logging.debug("execute_vehicle_action: Token refreshed.")
        vehicle = find_vehicle()
        logging.debug(f"execute_vehicle_action: Vehicle '{vehicle.name}' found.")
        method_to_call = getattr(vehicle, command)

        if not callable(method_to_call):
             logging.error(f"execute_vehicle_action: '{command}' is not a callable method on the vehicle object.")
             raise AttributeError(f"Vehicle object does not have a callable method named '{command}'.")

        if asyncio.iscoroutinefunction(method_to_call):
            logging.debug(f"Running ASYNC command on vehicle: {command}")
            result = await method_to_call(*args, **kwargs)
        else:
            logging.debug(f"Running SYNC command on vehicle: {command}")
            result = method_to_call(*args, **kwargs)
        logging.debug(f"Command '{command}' executed successfully.")
        return result

    except Exception as e:
        logging.error(f"!!! EXCEPTION during execute_vehicle_action for '{command}' !!!", exc_info=True)
        raise e # Re-raise for the route handler to catch

# --- API Endpoints ---
apiInfo = {
  "description": "Hyundai/Kia Connect API Server (Python)",
  "version": "1.1.0", # <-- Update this line
  "endpoints": [
    { "path": "/", "method": "GET", "description": "Shows welcome message and link to /info." },
    { "path": "/info", "method": "GET", "description": "Shows this API information." },
    { "path": "/status", "method": "GET", "description": "Gets cached vehicle status (updates cache first)." },
    { "path": "/status/refresh", "method": "GET", "description": "Forces refresh from car and gets live vehicle status." },
    { "path": "/lock", "method": "POST", "description": "Locks the vehicle." },
    { "path": "/unlock", "method": "POST", "description": "Unlocks the vehicle." },
    { "path": "/climate/start", "method": "POST", "description": "Starts climate control.", "body_example": { "temperature": 21, "defrost": False, "climate": True, "heating": True}, "notes": "Temperature in °C (16-30)." },
    { "path": "/climate/stop", "method": "POST", "description": "Stops climate control." },
    { "path": "/charge/start", "method": "POST", "description": "Starts charging (EV/PHEV)." },
    { "path": "/charge/stop", "method": "POST", "description": "Stops charging (EV/PHEV)." }
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
        logging.error(f"Exception during /status route:", exc_info=True)
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/status/refresh', methods=['GET'])
async def route_status_refresh():
    endpoint_name = "status_live"
    try:
        if not vm: raise ConnectionError("VehicleManager not initialized.")
        vm.check_and_refresh_token()

        vehicle = find_vehicle()
        vehicle_internal_id = vehicle.id
        if not vehicle_internal_id:
            return create_response(endpoint_name, success=False, error_message="Could not find internal vehicle ID.", status_code=500)

        logging.debug(f"Forcing refresh via vm.force_refresh_vehicle_state({vehicle_internal_id})...")
        # Call the synchronous method
        vm.force_refresh_vehicle_state(vehicle_internal_id)
        logging.debug("Refresh request initiated. Waiting for car to respond...")

        # Wait for the car/server to process (adjust delay if needed)
        await asyncio.sleep(20) # Increased wait time slightly

        logging.debug("Attempting to update cache after refresh delay...")
        vm.update_all_vehicles_with_cached_state() # Update the cache
        logging.debug("Cache update attempt complete.")

        updated_vehicle = find_vehicle() # Get the potentially updated vehicle data
        return create_response(endpoint_name, data=updated_vehicle.data)

        # --- FIX: Catch DuplicateRequestError using the 'hke' alias ---
    except hke.DuplicateRequestError as dre:
        logging.warning(f"DuplicateRequestError during /status/refresh: {dre}. Tell user to wait.")
        # Return a 429 Too Many Requests status code
        return create_response(endpoint_name, success=False,
                               error_message="Duplicate request detected. Please wait a minute before trying again.",
                               status_code=429)
    # -----------------------------------------------------------
    except Exception as e:
        logging.error(f"Exception during /status/refresh route:", exc_info=True)
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

# --- Action Routes ---
@app.route('/lock', methods=['POST'])
async def route_lock():
    endpoint_name = "lock"
    try:
        if not vm: raise ConnectionError("VehicleManager not initialized.")
        vm.check_and_refresh_token()
        vehicle = find_vehicle()
        vehicle_internal_id = vehicle.id
        if not vehicle_internal_id:
             return create_response(endpoint_name, success=False, error_message="Could not find internal vehicle ID.", status_code=500)

        logging.debug(f"Calling vm.lock for Vehicle ID {vehicle_internal_id} (VIN {VIN})...")
        result = vm.lock(vehicle_id=vehicle_internal_id) # Sync call
        logging.debug("vm.lock executed.")
        return create_response(endpoint_name, data={"result": result})

    # --- FIX: Catch DuplicateRequestError ---
    except hke.DuplicateRequestError as dre:
        logging.warning(f"DuplicateRequestError during /lock: {dre}. Tell user to wait.")
        return create_response(endpoint_name, success=False, error_message="Duplicate request detected. Please wait a minute before trying again.", status_code=429)
    # ----------------------------------------
    except Exception as e:
        logging.error(f"Exception during /lock route:", exc_info=True)
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/unlock', methods=['POST'])
async def route_unlock():
    endpoint_name = "unlock"
    try:
        if not vm: raise ConnectionError("VehicleManager not initialized.")
        vm.check_and_refresh_token()
        vehicle = find_vehicle()
        vehicle_internal_id = vehicle.id
        if not vehicle_internal_id:
             return create_response(endpoint_name, success=False, error_message="Could not find internal vehicle ID.", status_code=500)

        logging.debug(f"Calling vm.unlock for Vehicle ID {vehicle_internal_id} (VIN {VIN})...")
        result = vm.unlock(vehicle_id=vehicle_internal_id) # Sync call
        logging.debug("vm.unlock executed.")
        return create_response(endpoint_name, data={"result": result})

    # --- FIX: Catch DuplicateRequestError ---
    except hke.DuplicateRequestError as dre:
        logging.warning(f"DuplicateRequestError during /unlock: {dre}. Tell user to wait.")
        return create_response(endpoint_name, success=False, error_message="Duplicate request detected. Please wait a minute before trying again.", status_code=429)
    # ----------------------------------------
    except Exception as e:
        logging.error(f"Exception during /unlock route:", exc_info=True)
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
        result = vm.start_climate(vehicle_id=vehicle_internal_id, options=climate_options) # Sync call
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
        result = vm.stop_climate(vehicle_id=vehicle_internal_id) # Sync call
        logging.debug("vm.stop_climate executed.")
        return create_response(endpoint_name, data={"result": result})
    except Exception as e:
        logging.error(f"Exception during /climate/stop route:", exc_info=True)
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/charge/start', methods=['POST'])
async def route_charge_start():
    endpoint_name = "charge_start"
    try:
        # Assuming start_charge is on Vehicle object
        result = await execute_vehicle_action("start_charge")
        return create_response(endpoint_name, data={"result": result})
    except Exception as e:
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/charge/stop', methods=['POST'])
async def route_charge_stop():
    endpoint_name = "charge_stop"
    try:
        # Assuming stop_charge is on Vehicle object
        result = await execute_vehicle_action("stop_charge")
        return create_response(endpoint_name, data={"result": result})
    except Exception as e:
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.errorhandler(404)
def route_not_found(e):
    logging.warning(f"404 Not Found for request: {request.method} {request.path}")
    return create_response("route_not_found", success=False, error_message="The requested endpoint does not exist. See /info.", status_code=404)

@app.errorhandler(Exception)
def handle_exception(e):
    # Log the full traceback for server-side debugging
    logging.error(f"Unhandled Exception for request: {request.method} {request.path}", exc_info=True)
    # Return a generic 500 error response to the client
    return create_response("internal_server_error", success=False, error_message="An internal server error occurred.", status_code=500)

# --- Main Execution ---
if __name__ == '__main__':
    logging.info(f"Starting Flask server on http://0.0.0.0:{SERVER_PORT}...")
    # Consider using waitress or gunicorn for production
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False)