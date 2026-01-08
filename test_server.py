import os
import pytest
import sys
from unittest.mock import MagicMock, patch

# --- 1. SETUP VOR DEM IMPORT ---
# Wir müssen Env-Vars setzen, bevor wir den Server importieren,
# sonst beendet sich das Skript sofort mit exit().
os.environ['BLUELINK_USERNAME'] = 'test'
os.environ['BLUELINK_PASSWORD'] = 'test'
os.environ['BLUELINK_PIN'] = '1234'
os.environ['BLUELINK_VIN'] = 'TESTVIN1234567890'
os.environ['BLUELINK_REGION_ID'] = '1'
os.environ['BLUELINK_BRAND_ID'] = '2'
os.environ['SYNOLOGY_CHAT_ENABLED'] = 'false'

# Wir müssen verhindern, dass 'hyundai_server' beim Import 
# wirklich versucht, sich bei Hyundai einzuloggen.
with patch('hyundai_kia_connect_api.VehicleManager') as MockVM:
    # Wir erstellen einen Mock für die Instanz
    mock_instance = MockVM.return_value
    mock_instance.vehicles = {} # Leeres Dict verhindern Fehler beim Init
    
    # JETZT erst importieren wir den Server
    from hyundai_server import app, find_vehicle, ClimateRequestOptions
    
    # Wir überschreiben die globale 'vm' Variable im Server mit unserem Mock
    import hyundai_server
    hyundai_server.vm = mock_instance

# --- 2. TESTS ---

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def mock_vm():
    # Zugriff auf den Mock, den wir oben injiziert haben
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
    
    # Der Request (so wie wir ihn jetzt senden wollen)
    payload = {
        "temperature": 21.5,
        "duration": 30,
        "defrost": True,
        "heating": True
    }
    
    response = client.post('/climate/start', json=payload)
    
    # Prüfung
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data['success'] is True
    
    # WICHTIG: Prüfen, ob die Library mit den richtigen Optionen aufgerufen wurde
    mock_vm.start_climate.assert_called_once()
    
    # Argumente abrufen, mit denen start_climate aufgerufen wurde
    call_args = mock_vm.start_climate.call_args
    # call_args.kwargs['options'] ist das ClimateRequestOptions Objekt
    options_obj = call_args.kwargs['options']
    
    # Prüfen ob Duration und Temp korrekt übernommen wurden
    assert options_obj.set_temp == 21.5
    assert options_obj.duration == 30
    assert options_obj.defrost is True
    # Hinweis: Da wir side_mirror entfernt haben, prüfen wir das hier NICHT.

def test_climate_start_ignored_library_error(client, mock_vm):
    """Testet, ob der Server stabil bleibt, wenn unbekannte Parameter gesendet werden"""
    mock_vehicle = MagicMock()
    mock_vehicle.VIN = "TESTVIN1234567890"
    mock_vm.vehicles = {"id": mock_vehicle}
    
    payload = {
        "temperature": 21,
        "side_mirror": True, # Das kennt die alte Library nicht
        "duration": 15
    }
    
    response = client.post('/climate/start', json=payload)
    
    # Der Server sollte das 'side_mirror' einfach ignorieren und trotzdem 200 OK geben,
    # da wir es im Code ausgefiltert haben.
    assert response.status_code == 200
    assert response.get_json()['success'] is True