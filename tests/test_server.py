import pytest
from flask import Flask
# Assuming your server script is named hyundai_server.py and is in the parent directory
from ..hyundai_server import app as flask_app # Use .. for parent directory
from ..hyundai_server import find_vehicle   # Use .. for parent directory
from unittest.mock import MagicMock  # For creating mock objects


# --- Fixtures ---
# Fixture to create a test client for Flask
@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as client:
        yield client


# Fixture to mock the global 'vm' (VehicleManager) object
@pytest.fixture
def mock_vm(mocker):  # mocker comes from pytest-mock
    # Create a mock Vehicle object
    mock_vehicle = MagicMock()
    mock_vehicle.VIN = "TESTVIN1234567890"
    mock_vehicle.name = "TestCar"
    mock_vehicle.id = "test-vehicle-id-123"
    mock_vehicle.data = {"soc_in_percent": 50, "odometer_in_km": 1000}  # Add sample data
    # Mock methods used by find_vehicle
    mock_vehicle.configure_mock(name="TestCar", VIN="TESTVIN1234567890", id="test-vehicle-id-123")

    # Create a mock VehicleManager
    mock_vm_instance = MagicMock()
    # Configure the 'vehicles' attribute to return a dictionary containing the mock vehicle
    mock_vm_instance.vehicles = {"test-vehicle-id-123": mock_vehicle}
    # Mock methods used directly in routes or helpers
    mock_vm_instance.check_and_refresh_token = MagicMock()
    mock_vm_instance.update_all_vehicles_with_cached_state = MagicMock()
    mock_vm_instance.lock = MagicMock(return_value="Lock action simulated")  # Mock action return

    # Patch the global 'vm' instance in hyundai_server module with our mock
    mocker.patch('hyundai_server.vm', mock_vm_instance)
    # Patch the VIN constant to match our mock vehicle
    mocker.patch('hyundai_server.VIN', "TESTVIN1234567890")

    return mock_vm_instance


# --- Test Cases ---

# 1. Test the /info endpoint
def test_info_endpoint(client):
    """Test if the /info endpoint returns success and contains expected keys."""
    response = client.get('/info')
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data['success'] is True
    assert json_data['command_invoked'] == 'info'
    assert 'description' in json_data['data']
    assert 'endpoints' in json_data['data']


# 2. Test the find_vehicle helper function (using the mock_vm)
def test_find_vehicle_success(mock_vm):
    """Test if find_vehicle successfully finds the mock vehicle by VIN."""
    # Note: We don't need 'client' here, just the mocked 'vm'
    found_vehicle = find_vehicle(vin_to_find="TESTVIN1234567890")
    assert found_vehicle is not None
    assert found_vehicle.VIN == "TESTVIN1234567890"
    assert found_vehicle.name == "TestCar"


def test_find_vehicle_fail(mock_vm):
    """Test if find_vehicle raises an error for a non-existent VIN."""
    with pytest.raises(ValueError, match="not found"):
        find_vehicle(vin_to_find="NONEXISTENTVIN")


# 3. Test the /lock endpoint (check if the correct vm method is called)
def test_lock_endpoint(client, mock_vm):
    """Test if POST /lock calls vm.lock with the correct vehicle ID."""
    # Find the mock vehicle's internal ID
    mock_vehicle_id = mock_vm.vehicles["test-vehicle-id-123"].id

    response = client.post('/lock')
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data['success'] is True
    assert json_data['command_invoked'] == 'lock'

    # Check if vm.lock was called correctly
    mock_vm.check_and_refresh_token.assert_called_once()
    mock_vm.lock.assert_called_once_with(vehicle_id=mock_vehicle_id)

# Add more tests here for other endpoints (e.g., /status, /climate/start)
# For async endpoints, you might need pytest-asyncio: pip install pytest-asyncio
# and mark tests with @pytest.mark.asyncio