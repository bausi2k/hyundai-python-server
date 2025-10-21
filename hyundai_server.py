import os
import asyncio
import json
import traceback
import logging # NEU: Logging-Modul importieren
from logging.handlers import TimedRotatingFileHandler # NEU: Für rotierende Logs
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from hyundai_kia_connect_api import VehicleManager, ClimateRequestOptions, exceptions as hke

# --- Logging Konfiguration ---
log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO) # Konvertiere String zu logging Level
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
log_file = "/home/pi/hyundai-python-server/hyundai_server.log" # Pfad zur Log-Datei

# Rotiert jeden Tag um Mitternacht, behält 7 alte Logs
file_handler = TimedRotatingFileHandler(log_file, when='midnight', backupCount=7, encoding='utf-8')
file_handler.setFormatter(log_formatter)

# Optional: Auch auf Konsole ausgeben (nützlich für direktes Debugging)
# stream_handler = logging.StreamHandler()
# stream_handler.setFormatter(log_formatter)

logger = logging.getLogger()
logger.setLevel(log_level)
logger.addHandler(file_handler)
# logger.addHandler(stream_handler) # Bei Bedarf einkommentieren

logging.info(f"Log level set to: {log_level_str}")
# --- Ende Logging Konfiguration ---


# --- Configuration ---
load_dotenv()
USERNAME = os.getenv("BLUELINK_USERNAME")
PASSWORD = os.getenv("BLUELINK_PASSWORD")
PIN = os.getenv("BLUELINK_PIN")
VIN = os.getenv("BLUELINK_VIN")
region_id_str = os.getenv("BLUELINK_REGION_ID", "1")
brand_id_str = os.getenv("BLUELINK_BRAND_ID", "2")
SERVER_PORT_STR = os.getenv("PORT", "8080")

REGION_ID, BRAND_ID, SERVER_PORT = None, None, None

if not all([USERNAME, PASSWORD, PIN, VIN]):
    logging.error("❌ FATAL ERROR: Missing essential environment variables! Exiting.")
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
    vm.update_all_vehicles_with_cached_state()
    logging.info("✅ SUCCESS: VehicleManager initialized and logged in.")
    vehicle_found = any(getattr(v, 'VIN', None) == VIN for v in vm.vehicles.values()) if vm.vehicles else False
    if not vehicle_found:
        logging.warning(f"⚠️ WARNING: Vehicle with VIN {VIN} not found in initial cache.")

except hke.AuthenticationError as auth_err:
    logging.error(f"[FATAL] Authentication failed during startup! Check credentials.", exc_info=False)
    exit()
except Exception as e:
    logging.error(f"[FATAL] Failed to initialize VehicleManager during startup!", exc_info=True)
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
    log_method = logging.warning if 400 <= status_code < 500 else logging.error
    if not success: log_method(f"API Error ({status_code}) for '{endpoint_name}': {error_message}")
    return jsonify(response_body), status_code

# --- Helper: Find Vehicle ---
def find_vehicle(vin_to_find=VIN):
    global vm
    if not vm or not vm.vehicles:
        logging.warning("find_vehicle called but vm or vm.vehicles not initialized.")
        raise ConnectionError("VehicleManager not initialized or vehicles not loaded.")
    logging.debug(f"find_vehicle: Searching for VIN {vin_to_find}...")
    for vehicle_obj in vm.vehicles.values():
        if getattr(vehicle_obj, 'VIN', None) == vin_to_find:
            logging.debug(f"find_vehicle: Found match: {getattr(vehicle_obj, 'name', 'N/A')}")
            return vehicle_obj
    logging.error(f"find_vehicle: Vehicle with VIN {vin_to_find} not found.")
    raise ValueError(f"Vehicle with VIN {vin_to_find} not found.")

# --- Helper: Force Refresh ---
async def force_refresh():
    global vm
    if not vm: raise ConnectionError("VehicleManager not initialized.")
    vm.check_and_refresh_token()
    vehicle = find_vehicle()
    vehicle_internal_id = vehicle.id
    logging.debug(f"Forcing refresh via vm.force_refresh_vehicle_state({vehicle_internal_id})...")
    await vm.force_refresh_vehicle_state(vehicle_internal_id)
    logging.debug("Refresh complete.")
    return find_vehicle() # Find again to get updated object

# --- Helper: Execute Async Vehicle Action ---
async def execute_vehicle_action(command, *args, **kwargs):
    global vm;
    if not vm: raise ConnectionError("VehicleManager not initialized.")
    try:
        logging.debug(f"execute_action: Refreshing token for command '{command}'...")
        vm.check_and_refresh_token()
        vehicle = find_vehicle()
        method_to_call = getattr(vehicle, command)
        if not callable(method_to_call): raise AttributeError(f"'{command}' is not callable.")
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
        raise e

# --- API Endpoints ---
apiInfo = { # Behalte die Endpunkte, die du wirklich brauchst
    "description": "Hyundai/Kia Connect API Server (Python)",
    "version": "1.2.0", # <-- HIER ÄNDERN
    "endpoints": [
    { "path": "/", "method": "GET", "description": "Welcome message." },
    { "path": "/info", "method": "GET", "description": "API Information." },
    { "path": "/status", "method": "GET", "description": "Cached vehicle status." },
    { "path": "/status/refresh", "method": "GET", "description": "Live vehicle status." },
    { "path": "/lock", "method": "POST", "description": "Locks vehicle." },
    { "path": "/unlock", "method": "POST", "description": "Unlocks vehicle." },
    { "path": "/climate/start", "method": "POST", "description": "Starts climate.", "body_example": {"temperature": 21}},
    { "path": "/climate/stop", "method": "POST", "description": "Stops climate." },
    { "path": "/charge/start", "method": "POST", "description": "Starts charging." },
    { "path": "/charge/stop", "method": "POST", "description": "Stops charging." },
    { "path": "/odometer", "method": "GET", "description": "Cached odometer." },
    { "path": "/odometer/refresh", "method": "GET", "description": "Live odometer." },
    { "path": "/location", "method": "GET", "description": "Live vehicle location." }
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
        vm.update_all_vehicles_with_cached_state()
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
        vehicle = await force_refresh()
        return create_response(endpoint_name, data=vehicle.data)
    except hke.DuplicateRequestError as dre:
        logging.warning(f"DuplicateRequestError during /status/refresh: {dre}. Tell user to wait.")
        return create_response(endpoint_name, success=False, error_message="Duplicate request. Wait before retrying.", status_code=429)
    except Exception as e:
        logging.error(f"Exception during /status/refresh route:", exc_info=True)
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/lock', methods=['POST'])
async def route_lock():
    endpoint_name = "lock"
    try:
        if not vm: raise ConnectionError("VehicleManager not initialized.")
        vm.check_and_refresh_token()
        vehicle = find_vehicle(); vehicle_internal_id = vehicle.id;
        if not vehicle_internal_id: return create_response(endpoint_name, success=False, error_message="Internal ID not found.", status_code=500)
        logging.debug(f"Calling vm.lock for Vehicle ID {vehicle_internal_id}...")
        result = vm.lock(vehicle_id=vehicle_internal_id) # Sync
        logging.debug("vm.lock executed.")
        return create_response(endpoint_name, data={"result": result})
    except hke.DuplicateRequestError as dre:
        logging.warning(f"DuplicateRequestError during /lock: {dre}.")
        return create_response(endpoint_name, success=False, error_message="Duplicate request. Wait before retrying.", status_code=429)
    except Exception as e: logging.error(f"Exception during /lock route:", exc_info=True); return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/unlock', methods=['POST'])
async def route_unlock():
    endpoint_name = "unlock"
    try:
        if not vm: raise ConnectionError("VehicleManager not initialized.")
        vm.check_and_refresh_token()
        vehicle = find_vehicle(); vehicle_internal_id = vehicle.id;
        if not vehicle_internal_id: return create_response(endpoint_name, success=False, error_message="Internal ID not found.", status_code=500)
        logging.debug(f"Calling vm.unlock for Vehicle ID {vehicle_internal_id}...")
        result = vm.unlock(vehicle_id=vehicle_internal_id) # Sync
        logging.debug("vm.unlock executed.")
        return create_response(endpoint_name, data={"result": result})
    except hke.DuplicateRequestError as dre:
        logging.warning(f"DuplicateRequestError during /unlock: {dre}.")
        return create_response(endpoint_name, success=False, error_message="Duplicate request. Wait before retrying.", status_code=429)
    except Exception as e: logging.error(f"Exception during /unlock route:", exc_info=True); return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/climate/start', methods=['POST'])
async def route_climate_start():
    endpoint_name = "climate_start"
    try:
        if not vm: raise ConnectionError("VehicleManager not initialized.")
        vm.check_and_refresh_token()
        data = request.get_json(silent=True) or {}
        set_temp = data.get('temperature'); defrost = data.get('defrost', False); climate = data.get('climate', True); heating = data.get('heating', False)
        temp_value_for_options = None
        if 'temperature' in data:
            if not isinstance(set_temp, (int, float)) or not (16 <= set_temp <= 30): return create_response(endpoint_name, success=False, error_message="Invalid temperature (16-30).", status_code=400)
            temp_value_for_options = float(set_temp)
        climate_options = ClimateRequestOptions(set_temp=temp_value_for_options, defrost=bool(defrost), climate=bool(climate), heating=bool(heating))
        vehicle = find_vehicle(); vehicle_internal_id = vehicle.id;
        if not vehicle_internal_id: return create_response(endpoint_name, success=False, error_message="Internal ID not found.", status_code=500)
        logging.debug(f"Calling vm.start_climate for ID {vehicle_internal_id} with options: {climate_options}")
        result = vm.start_climate(vehicle_id=vehicle_internal_id, options=climate_options) # Sync
        logging.debug("vm.start_climate executed.")
        return create_response(endpoint_name, data={"result": result})
    except hke.DuplicateRequestError as dre:
        logging.warning(f"DuplicateRequestError during /climate/start: {dre}.")
        return create_response(endpoint_name, success=False, error_message="Duplicate request. Wait before retrying.", status_code=429)
    except Exception as e: logging.error(f"Exception during /climate/start route:", exc_info=True); return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/climate/stop', methods=['POST'])
async def route_climate_stop():
    endpoint_name = "climate_stop"
    try:
        if not vm: raise ConnectionError("VehicleManager not initialized.")
        vm.check_and_refresh_token()
        vehicle = find_vehicle(); vehicle_internal_id = vehicle.id;
        if not vehicle_internal_id: return create_response(endpoint_name, success=False, error_message="Internal ID not found.", status_code=500)
        logging.debug(f"Calling vm.stop_climate for Vehicle ID {vehicle_internal_id}...")
        result = vm.stop_climate(vehicle_id=vehicle_internal_id) # Sync
        logging.debug("vm.stop_climate executed.")
        return create_response(endpoint_name, data={"result": result})
    except hke.DuplicateRequestError as dre:
        logging.warning(f"DuplicateRequestError during /climate/stop: {dre}.")
        return create_response(endpoint_name, success=False, error_message="Duplicate request. Wait before retrying.", status_code=429)
    except Exception as e: logging.error(f"Exception during /climate/stop route:", exc_info=True); return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/charge/start', methods=['POST'])
async def route_charge_start():
    endpoint_name = "charge_start"
    try:
        result = await execute_vehicle_action("start_charge")
        return create_response(endpoint_name, data={"result": result})
    except hke.DuplicateRequestError as dre:
        logging.warning(f"DuplicateRequestError during /charge/start: {dre}.")
        return create_response(endpoint_name, success=False, error_message="Duplicate request. Wait before retrying.", status_code=429)
    except Exception as e: return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/charge/stop', methods=['POST'])
async def route_charge_stop():
    endpoint_name = "charge_stop"
    try:
        result = await execute_vehicle_action("stop_charge")
        return create_response(endpoint_name, data={"result": result})
    except hke.DuplicateRequestError as dre:
        logging.warning(f"DuplicateRequestError during /charge/stop: {dre}.")
        return create_response(endpoint_name, success=False, error_message="Duplicate request. Wait before retrying.", status_code=429)
    except Exception as e: return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/odometer', methods=['GET'])
async def route_odometer_cached():
    endpoint_name = "odometer_cached"
    try:
        if not vm: raise ConnectionError("VehicleManager not initialized.")
        vm.check_and_refresh_token()
        vm.update_all_vehicles_with_cached_state()
        vehicle = find_vehicle()
        odometer = getattr(vehicle, 'odometer_in_km', None)
        last_update_time = getattr(vehicle, 'last_updated_at', None)
        if odometer is None: return create_response(endpoint_name, success=False, error_message="Odometer data not available in cache.", status_code=404)
        data = {"odometer": odometer, "unit": "km", "last_updated": last_update_time.isoformat() if last_update_time else None}
        return create_response(endpoint_name, data=data)
    except Exception as e:
        logging.error(f"Exception during /odometer route:", exc_info=True)
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/odometer/refresh', methods=['GET'])
async def route_odometer_refresh():
    endpoint_name = "odometer_live"
    try:
        vehicle = await force_refresh()
        odometer = getattr(vehicle, 'odometer_in_km', None)
        last_update_time = getattr(vehicle, 'last_updated_at', None)
        if odometer is None: return create_response(endpoint_name, success=False, error_message="Odometer data not available after refresh.", status_code=404)
        data = {"odometer": odometer, "unit": "km", "last_updated": last_update_time.isoformat() if last_update_time else None}
        return create_response(endpoint_name, data=data)
    except hke.DuplicateRequestError as dre:
        logging.warning(f"DuplicateRequestError during /odometer/refresh: {dre}.")
        return create_response(endpoint_name, success=False, error_message="Duplicate request. Wait before retrying.", status_code=429)
    except Exception as e:
        logging.error(f"Exception during /odometer/refresh route:", exc_info=True)
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.route('/location', methods=['GET'])
async def route_location():
    endpoint_name = "location"
    try:
        vehicle = await force_refresh()
        location_time = getattr(vehicle, 'location_last_updated_at', None)
        coords = getattr(vehicle, 'location_coordinate', None)
        if not location_time or not coords: return create_response(endpoint_name, success=False, error_message="Location data not available.", status_code=404)
        location_data = {"latitude": coords.latitude, "longitude": coords.longitude, "altitude": coords.altitude, "last_updated": location_time.isoformat() if location_time else None }
        return create_response(endpoint_name, data=location_data)
    except hke.DuplicateRequestError as dre:
        logging.warning(f"DuplicateRequestError during /location: {dre}.")
        return create_response(endpoint_name, success=False, error_message="Duplicate request. Wait before retrying.", status_code=429)
    except Exception as e:
        logging.error(f"Exception during /location route:", exc_info=True)
        return create_response(endpoint_name, success=False, error_message=e, status_code=500)

@app.errorhandler(404)
def route_not_found(e):
    logging.warning(f"404 Not Found for request: {request.method} {request.path}")
    return create_response("route_not_found", success=False, error_message="The requested endpoint does not exist. See /info.", status_code=404)

@app.errorhandler(Exception)
def handle_exception(e):
    logging.error(f"Unhandled Exception for request: {request.method} {request.path}", exc_info=True)
    return create_response("internal_server_error", success=False, error_message="An internal server error occurred.", status_code=500)

# --- Main Execution ---
if __name__ == '__main__':
    logging.info(f"Starting Flask server on http://0.0.0.0:{SERVER_PORT}...")
    # Consider using waitress or gunicorn for production
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False)