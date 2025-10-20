# Hyundai/Kia Connect API Server (Python)

## 1. Übersicht

Dieser Python-Server bietet eine einfache HTTP-API zur Interaktion mit Hyundai/Kia Fahrzeugen über die Bluelink/Connect-Dienste. Er nutzt die **`hyundai_kia_connect_api`** Python-Bibliothek ([GitHub](https://github.com/Hyundai-Kia-Connect/hyundai_kia_connect_api)) und ist für den Betrieb auf einem Raspberry Pi (oder einem ähnlichen Linux-System) konzipiert. Der Server kann als `systemd`-Dienst eingerichtet werden, um automatisch beim Systemstart zu laufen.

Die API-Antworten enthalten ein `command_invoked`-Feld, um die Weiterverarbeitung in Tools wie Node-RED zu erleichtern.

## 2. Voraussetzungen

* Ein Raspberry Pi oder ein anderes Linux-System.
* Python 3 (z.B. 3.9 oder neuer).
* `pip` (Python Package Installer).
* `git` (optional, für Klonen oder Versionierung).
* Zugangsdaten für deinen Hyundai Bluelink / Kia Connect Account (Benutzername, Passwort, PIN, FIN/VIN).

## 3. Setup und Installation

### 3.1. Projektverzeichnis und Umgebung

1.  **Verzeichnis erstellen und wechseln:**
    ```bash
    mkdir -p /home/pi/hyundai-python-server 
    cd /home/pi/hyundai-python-server
    ```
2.  **Python Virtual Environment erstellen & aktivieren:**
    ```bash
    sudo apt update && sudo apt install python3-venv -y # Falls venv fehlt
    python3 -m venv venv
    source venv/bin/activate
    ```
    *(Dein Prompt sollte nun `(venv)` anzeigen)*

### 3.2. Abhängigkeiten installieren

1.  **Erstelle eine `requirements.txt`-Datei** (`vi requirements.txt`) mit folgendem Inhalt (oder den Versionen, die bei dir funktionieren):
    ```text
    hyundai-kia-connect-api>=3.48.1 # Mindestens diese Version oder neuer
    Flask[async]>=3.0.0 # Flask mit Async-Support
    python-dotenv>=1.0.0
    # Optional für besseren Production-Server:
    # waitress
    ```
2.  **Installiere die Abhängigkeiten:**
    ```bash
    pip install -r requirements.txt
    ```

### 3.3. Server-Skript

1.  **Erstelle die Datei `hyundai_server.py`** (`vi hyundai_server.py`).
2.  **Füge den Python-Code** für den Flask-Server (siehe letzte Code-Version oben) in diese Datei ein.

### 3.4. Konfigurationsdatei (`.env`)

1.  **Erstelle die Datei `.env`** (`vi .env`) im Projektverzeichnis.
2.  **Füge deine Zugangsdaten ein:**
    ```ini
    BLUELINK_USERNAME=dein_benutzername@example.com
    BLUELINK_PASSWORD=DeinPasswort # Anführungszeichen meist nicht nötig, außer bei speziellen Shell-Zeichen
    BLUELINK_PIN=1234
    BLUELINK_VIN=DEINE17STELLIGEVINXYZ
    # Numerische IDs verwenden!
    BLUELINK_REGION_ID=1 # 1 = Europe
    BLUELINK_BRAND_ID=2  # 1 = Kia, 2 = Hyundai
    BLUELINK_LANGUAGE=de # Optional: z.B. en, de, fr ...
    PORT=8080 # Optionaler Port für den Server
    # LOG_LEVEL=DEBUG # Optional für mehr Logs
    ```
3.  **Berechtigungen setzen:**
    ```bash
    chmod 600 .env
    ```

## 4. Server manuell starten (zum Testen)

1.  **Aktiviere die virtuelle Umgebung:** `source venv/bin/activate`
2.  **Starte den Server:** `python3 hyundai_server.py`
3.  Der Server sollte starten und auf Port 8080 (oder dem in `.env` definierten Port) lauschen. Mit `Strg+C` beenden.

## 5. API Endpunkte

Eine Übersicht der verfügbaren Endpunkte erhältst du über den `/info`-Endpunkt des laufenden Servers (z.B. `http://<IP_DEINES_RASPBERRY_PI>:8080/info`). Die wichtigsten sind:

* `GET /info`: Übersicht der API.
* `GET /status`: Gecachter Fahrzeugstatus (aktualisiert Cache vor dem Lesen).
* `GET /status/refresh`: Erzwingt Update vom Auto und gibt aktuellen Status zurück.
* `POST /lock`, `POST /unlock`: Türen ver-/entriegeln.
* `POST /climate/start`, `POST /climate/stop`: Klimaanlage steuern. (Body für start: `{"temperature": 21, "defrost": false, "climate": true, "heating": false}`)
* `POST /charge/start`, `POST /charge/stop`: Laden steuern.
* `GET /odometer`: Kilometerstand (erzwingt Update).
* `GET /location`: Position (erzwingt Update).

*(Hinweis: Die Endpunkte `/status/soc` und `/status/range` wurden entfernt, da diese Informationen im `/status/refresh`-Endpunkt enthalten sind.)*

## 6. Server als `systemd`-Dienst einrichten (Automatischer Start auf dem Pi)

### 6.1. `systemd`-Service-Unit-Datei erstellen
Erstelle/Bearbeite die Service-Datei (z.B. `hyundai-server.service`) mit `sudo vi /etc/systemd/system/hyundai-server.service`:
```ini
[Unit]
Description=Hyundai/Kia Connect API Server (Python)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=/home/pi/hyundai-python-server

# Wichtig: Pfad zum Python-Interpreter IN DER VENV verwenden!
ExecStart=/home/pi/hyundai-python-server/venv/bin/python3 /home/pi/hyundai-python-server/hyundai_server.py

EnvironmentFile=/home/pi/hyundai-python-server/.env
Restart=on-failure
RestartSec=10
# RuntimeMaxSec=6h # Optional: Periodischen Neustart wieder aktivieren, wenn gewünscht

StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target