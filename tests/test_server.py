import pytest
import pytest_asyncio
from flask import Flask
# Use direct import assuming pytest runs from root with PYTHONPATH=.
from hyundai_server import app as flask_app
from hyundai_server import find_vehicle, ClimateRequestOptions
from unittest.mock import MagicMock, AsyncMock

# --- Fixtures ---
@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    flask_app.config['DEBUG'] = False
    with flask_app.test_client() as client:
        yield client

@pytest_asyncio.fixture
async def mock_vm(mocker):
    # Create a mock Vehicle object
    mock_vehicle = MagicMock()
    mock_vehicle.VIN = "TESTVIN1234567890"
    mock_vehicle.name = "TestCar"
    mock_vehicle.id = "test-vehicle-id-123"
    mock_vehicle.data = {
        "engine": {"odometer": {"unit": 0, "value": 1234}},
        "last_updated_at": "2025-10-20T10:00:00Z",
        "location_coordinate": MagicMock(latitude=48.2, longitude=16.3, altitude=200),
        "location_last_updated_at": MagicMock(isoformat=lambda: "2025-10-20T10:00:00Z"),
        "soc_in_percent": 65,
        "odometer_in_km": 1234,
        "ev_driving_range_in_km": 250,
    }
    # Mock specific attributes accessed directly
    mock_vehicle.soc_in_percent = 65
    mock_vehicle.odometer_in_km = 1234
    mock_vehicle.ev_driving_range_in_km = 250
    mock_vehicle.location_last_updated_at = MagicMock(isoformat=lambda: "2025-10-20T10:00:00Z")
    mock_vehicle.location_coordinate = MagicMock(latitude=48.2, longitude=16.3, altitude=200)

    # Mock vehicle methods that are ASYNC
    mock_vehicle.start_charge = AsyncMock(return_value="Charge started simulated")
    mock_vehicle.stop_charge = AsyncMock(return_value="Charge stopped simulated")
    # Add mocks for other vehicle actions if needed

    # Create a mock VehicleManager
    mock_vm_instance = MagicMock()
    mock_vm_instance.vehicles = {"test-vehicle-id-123": mock_vehicle}
    # Mock methods used directly in routes or helpers
    mock_vm_instance.check_and_refresh_token = MagicMock()
    mock_vm_instance.update_all_vehicles_with_cached_state = MagicMock()
    # Mock manager methods that are ASYNC
    mock_vm_instance.force_refresh_vehicle_state = AsyncMock(return_value=None)
    # Mock manager methods that are SYNC but return something
    mock_vm_instance.lock = MagicMock(return_value="Lock action simulated")
    mock_vm_instance.unlock = MagicMock(return_value="Unlock action simulated")
    mock_vm_instance.start_climate = MagicMock(return_value="Climate started simulated")
    mock_vm_instance.stop_climate = MagicMock(return_value="Climate stopped simulated")

    # Patch the global 'vm' instance in hyundai_server module with our mock
    mocker.patch('hyundai_server.vm', mock_vm_instance)
    # Patch the VIN constant to match our mock vehicle
    mocker.patch('hyundai_server.VIN', "TESTVIN1234567890")

    yield mock_vm_instance

# --- Test Cases ---

# Test GET endpoints (Marked async because they call async routes)
@pytest.mark.asyncio
async def test_info_endpoint(client):
    response = client.get('/info') # REMOVED await
    assert response.status_code == 200
    json_data = response.get_json() # REMOVED await
    assert json_data['success'] is True
    assert 'endpoints' in json_data['data']

@pytest.mark.asyncio
async def test_status_cached_endpoint(client, mock_vm):
    response = client.get('/status') # REMOVED await
    assert response.status_code == 200
    json_data = response.get_json() # REMOVED await
    assert json_data['success'] is True
    assert json_data['command_invoked'] == 'status_cached'
    assert 'soc_in_percent' in json_data['data']
    mock_vm.check_and_refresh_token.assert_called()
    mock_vm.update_all_vehicles_with_cached_state.assert_called()

@pytest.mark.asyncio
async def test_status_refresh_endpoint(client, mock_vm):
    response = client.get('/status/refresh') # REMOVED await
    assert response.status_code == 200
    json_data = response.get_json() # REMOVED await
    assert json_data['success'] is True
    assert json_data['command_invoked'] == 'status_live'
    assert 'soc_in_percent' in json_data['data']
    mock_vm.check_and_refresh_token.assert_called()
    mock_vm.force_refresh_vehicle_state.assert_awaited_once_with("test-vehicle-id-123")

@pytest.mark.asyncio
async def test_odometer_cached_endpoint(client, mock_vm):
    response = client.get('/odometer') # REMOVED await
    assert response.status_code == 200
    json_data = response.get_json() # REMOVED await
    assert json_data['success'] is True
    assert json_data['command_invoked'] == 'odometer_cached'
    assert json_data['data']['odometer'] == 1234
    mock_vm.update_all_vehicles_with_cached_state.assert_called()

@pytest.mark.asyncio
async def test_odometer_refresh_endpoint(client, mock_vm):
    response = client.get('/odometer/refresh') # REMOVED await
    assert response.status_code == 200
    json_data = response.get_json() # REMOVED await
    assert json_data['success'] is True
    assert json_data['command_invoked'] == 'odometer_live'
    assert json_data['data']['odometer'] == 1234
    mock_vm.force_refresh_vehicle_state.assert_awaited_with("test-vehicle-id-123")

@pytest.mark.asyncio
async def test_location_endpoint(client, mock_vm):
    response = client.get('/location') # REMOVED await
    assert response.status_code == 200
    json_data = response.get_json() # REMOVED await
    assert json_data['success'] is True
    assert json_data['command_invoked'] == 'location'
    assert json_data['data']['latitude'] == 48.2
    assert json_data['data']['longitude'] == 16.3
    mock_vm.force_refresh_vehicle_state.assert_awaited_with("test-vehicle-id-123")

# Test find_vehicle helper (NO asyncio mark needed)
def test_find_vehicle_success(mock_vm):
    found_vehicle = find_vehicle(vin_to_find="TESTVIN1234567890")
    assert found_vehicle is not None
    assert found_vehicle.VIN == "TESTVIN1234567890"

def test_find_vehicle_fail(mock_vm):
    with pytest.raises(ValueError, match="not found"):
        find_vehicle(vin_to_find="NONEXISTENTVIN")

# Test POST action endpoints (Marked async)
@pytest.mark.asyncio
async def test_lock_endpoint(client, mock_vm):
    mock_vehicle_id = mock_vm.vehicles["test-vehicle-id-123"].id
    response = client.post('/lock') # REMOVED await
    assert response.status_code == 200
    json_data = response.get_json() # REMOVED await
    assert json_data['success'] is True
    mock_vm.check_and_refresh_token.assert_called()
    mock_vm.lock.assert_called_once_with(vehicle_id=mock_vehicle_id)

@pytest.mark.asyncio
async def test_unlock_endpoint(client, mock_vm):
    mock_vehicle_id = mock_vm.vehicles["test-vehicle-id-123"].id
    response = client.post('/unlock') # REMOVED await
    assert response.status_code == 200
    json_data = response.get_json() # REMOVED await
    assert json_data['success'] is True
    mock_vm.check_and_refresh_token.assert_called()
    mock_vm.unlock.assert_called_once_with(vehicle_id=mock_vehicle_id)

@pytest.mark.asyncio
async def test_climate_start_endpoint(client, mock_vm):
    mock_vehicle_id = mock_vm.vehicles["test-vehicle-id-123"].id
    test_data = {"temperature": 22.5, "defrost": True, "heating": True, "climate": True}
    response = client.post('/climate/start', json=test_data) # REMOVED await
    assert response.status_code == 200
    json_data = response.get_json() # REMOVED await
    assert json_data['success'] is True
    mock_vm.check_and_refresh_token.assert_called()
    mock_vm.start_climate.assert_called_once()
    args, kwargs = mock_vm.start_climate.call_args
    assert kwargs['vehicle_id'] == mock_vehicle_id
    assert isinstance(kwargs['options'], ClimateRequestOptions)
    assert kwargs['options'].set_temp == 22.5
    assert kwargs['options'].defrost is True
    assert kwargs['options'].heating is True
    assert kwargs['options'].climate is True

@pytest.mark.asyncio
async def test_climate_start_invalid_temp(client, mock_vm):
    response = client.post('/climate/start', json={"temperature": 5}) # REMOVED await
    assert response.status_code == 400
    json_data = response.get_json() # REMOVED await
    assert json_data['success'] is False
    assert 'Invalid temperature' in json_data['details']
    mock_vm.start_climate.assert_not_called()

@pytest.mark.asyncio
async def test_climate_stop_endpoint(client, mock_vm):
    mock_vehicle_id = mock_vm.vehicles["test-vehicle-id-123"].id
    response = client.post('/climate/stop') # REMOVED await
    assert response.status_code == 200
    json_data = response.get_json() # REMOVED await
    assert json_data['success'] is True
    mock_vm.check_and_refresh_token.assert_called()
    mock_vm.stop_climate.assert_called_once_with(vehicle_id=mock_vehicle_id)

@pytest.mark.asyncio
async def test_charge_start_endpoint(client, mock_vm):
    response = client.post('/charge/start') # REMOVED await
    assert response.status_code == 200
    json_data = response.get_json() # REMOVED await
    assert json_data['success'] is True
    mock_vm.check_and_refresh_token.assert_called()
    mock_vm.vehicles["test-vehicle-id-123"].start_charge.assert_awaited_once()

@pytest.mark.asyncio
async def test_charge_stop_endpoint(client, mock_vm):
    response = client.post('/charge/stop') # REMOVED await
    assert response.status_code == 200
    json_data = response.get_json() # REMOVED await
    assert json_data['success'] is True
    mock_vm.check_and_refresh_token.assert_called()
    mock_vm.vehicles["test-vehicle-id-123"].stop_charge.assert_awaited_once()

# Test 404 handler (Marked async)
@pytest.mark.asyncio
async def test_not_found(client):
    response = client.get('/nonexistent/route') # REMOVED await
    assert response.status_code == 404
    json_data = response.get_json() # REMOVED await
    assert json_data['success'] is False
    assert json_data['command_invoked'] == 'route_not_found'