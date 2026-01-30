import os
import pytest
import sys
from unittest.mock import MagicMock, patch

# --- SETUP VOR IMPORT ---
os.environ['BLUELINK_USERNAME'] = 'test'
os.environ['BLUELINK_PASSWORD'] = 'test'
os.environ['BLUELINK_PIN'] = '1234'
os.environ['BLUELINK_VIN'] = 'TESTVIN1234567890'
os.environ['BLUELINK_REGION_ID'] = '1'
os.environ['BLUELINK_BRAND_ID'] = '2'
os.environ['SYNOLOGY_CHAT_ENABLED'] = 'false'

with patch('hyundai_kia_connect_api.VehicleManager') as MockVM:
    mock_instance = MockVM.return_value
    mock_instance.vehicles = {}
    
    # Import erst NACHDEM der Mock aktiv ist
    from hyundai_server import app, find_vehicle, ClimateRequestOptions
    import hyundai_server
    hyundai_server.vm = mock_instance

# --- TESTS ---

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def mock_vm():
    return hyundai_server.vm

def test_info_endpoint(client):
    response = client.get('/info')
    assert response.status_code == 200
    assert "version" in response.get_json()['data']

def test_climate_start_with_duration(client, mock_vm):
    # Setup des Mock-Autos
    mock_vehicle = MagicMock()
    mock_vehicle.id = "car_id_123"
    mock_vehicle.VIN = "TESTVIN1234567890"
    mock_vm.vehicles = {"car_id_123": mock_vehicle}
    
    # WICHTIG: Wir müssen definieren, was die Funktion zurückgibt,
    # damit JSON es verarbeiten kann (kein MagicMock Objekt!)
    mock_vm.start_climate.return_value = "fake-request-id-123"

    payload = {
        "temperature": 21.5,
        "duration": 30,
        "defrost": True,
        "heating": True
    }
    
    response = client.post('/climate/start', json=payload)
    
    # Debugging Info falls es schief geht
    if response.status_code != 200:
        print(response.get_json())

    assert response.status_code == 200
    assert response.get_json()['success'] is True
    
    mock_vm.start_climate.assert_called_once()
    call_args = mock_vm.start_climate.call_args
    options_obj = call_args.kwargs['options']
    
    assert options_obj.set_temp == 21.5
    assert options_obj.duration == 30
    assert options_obj.defrost is True

def test_climate_start_ignored_library_error(client, mock_vm):
    """Testet, ob der Server stabil bleibt, wenn unbekannte Parameter gesendet werden"""
    mock_vehicle = MagicMock()
    mock_vehicle.VIN = "TESTVIN1234567890"
    mock_vm.vehicles = {"id": mock_vehicle}
    
    # WICHTIG: Auch hier einen Return-Value setzen
    mock_vm.start_climate.return_value = "fake-request-id-456"
    
    payload = {
        "temperature": 21,
        "side_mirror": True,
        "duration": 15
    }
    
    response = client.post('/climate/start', json=payload)
    
    assert response.status_code == 200
    assert response.get_json()['success'] is True
