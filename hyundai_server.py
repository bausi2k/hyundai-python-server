import os
import asyncio
import json
import traceback
import logging
import threading
import requests
from logging.handlers import TimedRotatingFileHandler
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from hyundai_kia_connect_api import VehicleManager, ClimateRequestOptions, exceptions as hke

# --- Configuration Load ---
load_dotenv()

# --- Logging Setup ---
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
log_file = "hyundai_server.log"

log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

file_handler = TimedRotatingFileHandler(log_file, when='midnight', backupCount=7, encoding='utf-8')
file_handler.setFormatter(log_formatter)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)

logger = logging.getLogger()
logger.setLevel(log_level)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

logging.info(f"Log level set to: {log_level}")

# --- Env Vars ---
USERNAME = os.getenv("BLUELINK_USERNAME")
PASSWORD = os.getenv("BLUELINK_PASSWORD")
PIN = os.getenv("BLUELINK_PIN")
VIN = os.getenv("BLUELINK_VIN")
region_id_str = os.getenv("BLUELINK_REGION_ID", "1")
brand_id_str = os.getenv("BLUELINK_BRAND_ID", "2")
SERVER_PORT_STR = os.getenv("PORT", "8080")

# --- Synology Config ---
SYNOLOGY_CHAT_ENABLED = os.getenv("SYNOLOGY_CHAT_ENABLED", "false").lower() == "true"
SYNOLOGY_CHAT_URL = os.getenv("SYNOLOGY_CHAT_URL", "")

REGION_ID, BRAND_ID, SERVER_PORT = None, None, None

# --- Helper: Synology Alert ---
def send_synology_alert(message):
    if not SYNOLOGY_CHAT_ENABLED or not SYNOLOGY_CHAT_URL:
        return
    def _send():
        try:
            payload = {"text": f"🚨 **Hyundai Server Alert**\n\n{message}"}
            requests.post(SYNOLOGY_CHAT_URL, data={'payload': json.dumps(payload)}, timeout=10)
        except Exception as e:
            logging.error(f"Failed to send Synology alert: {e}")
    threading.Thread(target=_send).start()

# --- Validation ---
if not all([USERNAME, PASSWORD, PIN, VIN]):
    msg = "❌ FATAL ERROR: Missing essential environment variables!"
    logging.error(msg)
    send_synology_alert(msg)
    exit()

try:
    REGION_ID = int(region_id_str)
    BRAND_ID = int(brand_id_str)
    SERVER_PORT = int(SERVER_PORT_STR)
except ValueError as e:
    msg = f"❌ FATAL ERROR: Invalid numeric value in .env file: {e}"
    logging.error(msg)
    send_synology_alert(msg)
    exit()

# --- Global Vehicle Manager Instance ---
vm = None

def initialize_vehicle_manager():
    global vm
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
            msg = f"⚠️ WARNING: Vehicle with VIN {VIN} not found in initial cache."
            logging.warning(msg)
            send_synology_alert(msg)

    except hke.AuthenticationError as auth_err:
        msg = f"[FATAL] Authentication failed during startup! Error: {auth_err}"
        logging.error(msg)
        send_synology_alert(msg)
        exit()
    except Exception as e:
        msg = f"[FATAL] Failed to initialize VehicleManager during startup! Error: {e}"
        logging.error(msg, exc_info=True)
        send_synology_alert(msg)
        exit()

initialize_vehicle_manager()

# --- Flask App ---
app = Flask(__name__)

def create_response(endpoint_name, success=True, data=None, error_message=None, status_code=200):
    response_body = { "success": success, "command_invoked": endpoint_name }
    if success:
        response_body["message"] = f"{endpoint_name} successful."
        if data is not None: response_body["data"] = data
    else:
        response_body["error"] = f"Error during {endpoint_name}."
        if error_message: response_body["details"] = str(error_message)
    
    if not success:
        log_msg = f"API Error ({status_code}) for '{endpoint_name}': {error_message}"
        if 400 <= status_code < 500:
            logging.warning(log_msg)
        else:
            logging.error(log_msg)
            send_synology_alert(f"Error on endpoint `{endpoint_name}`:\n```{error_message}```")
            
    return jsonify(response_body), status_code

def find_vehicle(vin_to_find=VIN):
    global vm
    if not vm or not vm.vehicles: raise ConnectionError("VM not initialized")
    for v in vm.vehicles.values():
        if getattr(v, 'VIN', None) == vin_to_find: return v
    raise ValueError(f"Vehicle with VIN {vin_to_find} not found.")

async def force_refresh():
    global vm
    if not vm: raise ConnectionError("VM not initialized")
    vm.check_and_refresh_token()
    vehicle = find_vehicle()
    vehicle_internal_id = vehicle.id
    logging.debug(f"Forcing refresh via vm.force_refresh_vehicle_state({vehicle_internal_id})...")
    await vm.force_refresh_vehicle_state(vehicle_internal_id)
    logging.debug("Refresh complete.")
    return find_vehicle()

# --- Routes ---
@app.route('/', methods=['GET'])
def route_root():
    return create_response("root", data={"message": "Hyundai Server running."})

@app.route('/info', methods=['GET'])
def route_info():
    return create_response("info", data={"version": "1.2.1", "endpoints": ["/status", "/status/refresh", "/lock", "/unlock", "/climate/start", "/climate/stop", "/charge/start", "/charge/stop"]})

@app.route('/status', methods=['GET'])
async def route_status_cached():
    try:
        if not vm: raise ConnectionError("VM not initialized")
        vm.check_and_refresh_token()
        vm.update_all_vehicles_with_cached_state()
        vehicle = find_vehicle()
        return create_response("status_cached", data=vehicle.data)
    except Exception as e:
        return create_response("status_cached", success=False, error_message=e, status_code=500)

@app.route('/status/refresh', methods=['GET'])
async def route_status_refresh():
    try:
        vehicle = await force_refresh()
        return create_response("status_live", data=vehicle.data)
    except hke.DuplicateRequestError:
        return create_response("status_live", success=False, error_message="Duplicate request. Wait.", status_code=429)
    except Exception as e:
        return create_response("status_live", success=False, error_message=e, status_code=500)

@app.route('/lock', methods=['POST'])
async def route_lock():
    try:
        if not vm: raise ConnectionError("VM not initialized")
        vm.check_and_refresh_token()
        vehicle = find_vehicle()
        logging.debug(f"Calling vm.lock for {vehicle.id}...")
        # FIX: Aufruf direkt auf vm
        result = vm.lock(vehicle.id)
        return create_response("lock", data={"result": result})
    except hke.DuplicateRequestError:
        return create_response("lock", success=False, error_message="Wait.", status_code=429)
    except Exception as e:
        return create_response("lock", success=False, error_message=e, status_code=500)

@app.route('/unlock', methods=['POST'])
async def route_unlock():
    try:
        if not vm: raise ConnectionError("VM not initialized")
        vm.check_and_refresh_token()
        vehicle = find_vehicle()
        logging.debug(f"Calling vm.unlock for {vehicle.id}...")
        # FIX: Aufruf direkt auf vm
        result = vm.unlock(vehicle.id)
        return create_response("unlock", data={"result": result})
    except hke.DuplicateRequestError:
        return create_response("unlock", success=False, error_message="Wait.", status_code=429)
    except Exception as e:
        return create_response("unlock", success=False, error_message=e, status_code=500)

@app.route('/climate/start', methods=['POST'])
async def route_climate_start():
    try:
        if not vm: raise ConnectionError("VM not initialized")
        vm.check_and_refresh_token()
        data = request.get_json(silent=True) or {}
        set_temp = data.get('temperature')
        defrost = data.get('defrost', False)
        climate = data.get('climate', True)
        heating = data.get('heating', False)

        temp_val = None
        if 'temperature' in data:
            if not isinstance(set_temp, (int, float)) or not (16 <= set_temp <= 30):
                 return create_response("climate_start", success=False, error_message="Invalid temp (16-30).", status_code=400)
            temp_val = float(set_temp)

        options = ClimateRequestOptions(set_temp=temp_val, defrost=bool(defrost), climate=bool(climate), heating=bool(heating))
        vehicle = find_vehicle()
        result = vm.start_climate(vehicle_id=vehicle.id, options=options)
        return create_response("climate_start", data={"result": result})
    except hke.DuplicateRequestError:
        return create_response("climate_start", success=False, error_message="Wait.", status_code=429)
    except Exception as e:
        return create_response("climate_start", success=False, error_message=e, status_code=500)

@app.route('/climate/stop', methods=['POST'])
async def route_climate_stop():
    try:
        if not vm: raise ConnectionError("VM not initialized")
        vm.check_and_refresh_token()
        vehicle = find_vehicle()
        result = vm.stop_climate(vehicle_id=vehicle.id)
        return create_response("climate_stop", data={"result": result})
    except hke.DuplicateRequestError:
        return create_response("climate_stop", success=False, error_message="Wait.", status_code=429)
    except Exception as e:
        return create_response("climate_stop", success=False, error_message=e, status_code=500)

@app.route('/charge/start', methods=['POST'])
async def route_charge_start():
    try:
        if not vm: raise ConnectionError("VM not initialized")
        vm.check_and_refresh_token()
        vehicle = find_vehicle()
        logging.debug(f"Calling vm.start_charge for {vehicle.id}...")
        # FIX: Aufruf direkt auf vm
        result = vm.start_charge(vehicle.id)
        return create_response("charge_start", data={"result": result})
    except hke.DuplicateRequestError:
        return create_response("charge_start", success=False, error_message="Wait.", status_code=429)
    except Exception as e:
        return create_response("charge_start", success=False, error_message=e, status_code=500)

@app.route('/charge/stop', methods=['POST'])
async def route_charge_stop():
    try:
        if not vm: raise ConnectionError("VM not initialized")
        vm.check_and_refresh_token()
        vehicle = find_vehicle()
        logging.debug(f"Calling vm.stop_charge for {vehicle.id}...")
        # FIX: Aufruf direkt auf vm
        result = vm.stop_charge(vehicle.id)
        return create_response("charge_stop", data={"result": result})
    except hke.DuplicateRequestError:
        return create_response("charge_stop", success=False, error_message="Wait.", status_code=429)
    except Exception as e:
        return create_response("charge_stop", success=False, error_message=e, status_code=500)

@app.route('/odometer', methods=['GET'])
async def route_odometer_cached():
    try:
        if not vm: raise ConnectionError("VM not initialized")
        vm.check_and_refresh_token()
        vm.update_all_vehicles_with_cached_state()
        vehicle = find_vehicle()
        odometer = getattr(vehicle, 'odometer_in_km', None)
        if odometer is None: return create_response("odometer_cached", success=False, error_message="No data.", status_code=404)
        return create_response("odometer_cached", data={"odometer": odometer, "unit": "km"})
    except Exception as e:
        return create_response("odometer_cached", success=False, error_message=e, status_code=500)

@app.route('/odometer/refresh', methods=['GET'])
async def route_odometer_refresh():
    try:
        vehicle = await force_refresh()
        odometer = getattr(vehicle, 'odometer_in_km', None)
        if odometer is None: return create_response("odometer_live", success=False, error_message="No data.", status_code=404)
        return create_response("odometer_live", data={"odometer": odometer, "unit": "km"})
    except hke.DuplicateRequestError:
        return create_response("odometer_live", success=False, error_message="Wait.", status_code=429)
    except Exception as e:
        return create_response("odometer_live", success=False, error_message=e, status_code=500)

@app.route('/location', methods=['GET'])
async def route_location():
    try:
        vehicle = await force_refresh()
        loc_time = getattr(vehicle, 'location_last_updated_at', None)
        coords = getattr(vehicle, 'location_coordinate', None)
        if not loc_time or not coords: return create_response("location", success=False, error_message="No data.", status_code=404)
        data = {"latitude": coords.latitude, "longitude": coords.longitude, "altitude": coords.altitude, "last_updated": loc_time.isoformat()}
        return create_response("location", data=data)
    except hke.DuplicateRequestError:
        return create_response("location", success=False, error_message="Wait.", status_code=429)
    except Exception as e:
        return create_response("location", success=False, error_message=e, status_code=500)


@app.errorhandler(Exception)
def handle_exception(e):
    logging.error(f"Unhandled Exception: {e}", exc_info=True)
    send_synology_alert(f"Unhandled Exception:\n```{e}```")
    return create_response("internal_server_error", success=False, error_message="Internal Server Error", status_code=500)

if __name__ == '__main__':
    logging.info(f"Starting Flask server on http://0.0.0.0:{SERVER_PORT}...")
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False)