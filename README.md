
# Hyundai/Kia Connect API Server (Python) - v1.2.0

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Supported-2496ED.svg)](https://www.docker.com/)
[![Buy Me A Coffee](https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png)](https://www.buymeacoffee.com/bausi2k)

**Navigation / Sprache wählen:**
[🇺🇸 **English Version**](#-english-version) | [🇦🇹 **Deutsche Version**](#-deutsche-version)

---

<a name="english-version"></a>
## 🇺🇸 English Version

### 1. Overview
This project provides a robust Python Flask API server to interact with Hyundai and Kia vehicles via their Bluelink/UVO Connect services. It leverages the **`hyundai_kia_connect_api`** library and is designed to run as a **Docker container** on a Raspberry Pi or any Linux system.

**Key Features:**
* **Status Retrieval:** Get cached status (fast) or force a live refresh from the car (slow).
* **Remote Control:** Lock/Unlock, Climate Control, Start/Stop Charging.
* **Reliability:** Automatic token management and session refreshing.
* **Monitoring:** Integrated **Synology Chat** webhooks for critical error alerts.
* **Dockerized:** Easy deployment via Docker Compose.

### 2. Prerequisites
* A system with Docker & Docker Compose installed.
* Valid Hyundai Bluelink or Kia Connect credentials.
* (Optional) Synology Chat Webhook URL for notifications.

### 3. Installation & Setup (Docker)

This is the recommended way to run the server.

#### 3.1 Clone Repository
```bash
git clone [https://github.com/bausi2k/hyundai-python-server.git](https://github.com/bausi2k/hyundai-python-server.git)
cd hyundai-python-server
````

#### 3.2 Configuration (`.env`)

Create a `.env` file in the project directory:

```bash
vi .env
```

Paste the following content and adapt it to your needs:

```ini
# --- Credentials ---
BLUELINK_USERNAME=your_email@example.com
BLUELINK_PASSWORD=YourPassword
BLUELINK_PIN=1234
BLUELINK_VIN=YOUR_17_DIGIT_VIN

# --- Configuration ---
# 1 = Europe, 2 = USA, 3 = Canada
BLUELINK_REGION_ID=1
# 1 = Kia, 2 = Hyundai
BLUELINK_BRAND_ID=2
# Internal container port (keep as 8080)
PORT=8080
# Logging (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO

# --- Synology Chat Alerts (Optional) ---
SYNOLOGY_CHAT_ENABLED=true
SYNOLOGY_CHAT_URL=https://your-synology-url/webapi/entry.cgi?api=SYNO.Chat.External&method=incoming&version=2&token=...
```

#### 3.3 Start Server

```bash
docker compose up -d --build
```

The server will be accessible at `http://<YOUR-PI-IP>:8444` (default external port defined in `docker-compose.yml`).

#### 3.4 View Logs

```bash
docker compose logs -f
```

### 4\. API Endpoints

You can check available endpoints via `GET /info`.

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/info` | Returns API info and version. |
| `GET` | `/status` | Returns **cached** vehicle status (fast response). |
| `GET` | `/status/refresh` | Forces a **live update** from the car (takes \~20s). |
| `POST` | `/lock` | Locks the vehicle. |
| `POST` | `/unlock` | Unlocks the vehicle. |
| `POST` | `/climate/start` | Starts climate. JSON Body: `{"temperature": 21, "defrost": false}` |
| `POST` | `/climate/stop` | Stops climate. |
| `POST` | `/charge/start` | Starts charging. |
| `POST` | `/charge/stop` | Stops charging. |
| `GET` | `/odometer` | Returns odometer reading (cached). |
| `GET` | `/odometer/refresh`| Returns odometer reading (live). |
| `GET` | `/location` | Returns GPS location (live). |

### 5\. Node-RED Integration

The API returns JSON responses containing a `"command_invoked"` field. Typical flow:

1.  **Inject Node:** Trigger every 15 minutes.
2.  **HTTP Request:** GET `http://localhost:8444/status` (use `/status/refresh` sparingly to save 12V battery).
3.  **Function Node:** Parse payload.
4.  **Output:** Save to InfluxDB or send via MQTT.

-----

-----

<a name="deutsche-version"\></a>

## 🇦🇹 Deutsche Version

### 1\. Übersicht

Dieser Python-Server bietet eine einfache HTTP-Schnittstelle (API) zur Steuerung von Hyundai und Kia Fahrzeugen über die Bluelink/UVO-Dienste. Er basiert auf der **`hyundai_kia_connect_api`** Bibliothek und ist primär für den Betrieb als **Docker-Container** auf einem Raspberry Pi konzipiert.

**Funktionen:**

  * **Statusabfrage:** Abruf aus dem Cache (schnell) oder Live-Update vom Fahrzeug (langsam).
  * **Fernsteuerung:** Verriegeln/Entriegeln, Klimaanlage, Laden starten/stoppen.
  * **Zuverlässigkeit:** Automatisches Token-Management und Re-Login.
  * **Monitoring:** Integration von **Synology Chat** für Benachrichtigungen bei kritischen Fehlern.
  * **Docker:** Einfache Installation mittels Docker Compose.

### 2\. Voraussetzungen

  * Ein System mit Docker & Docker Compose (z.B. Raspberry Pi).
  * Zugangsdaten für deinen Hyundai Bluelink / Kia Connect Account.
  * (Optional) Synology Chat Webhook-URL für Alarmmeldungen.

### 3\. Installation & Start (Docker)

Dies ist der empfohlene Weg, den Server zu betreiben.

#### 3.1 Repository klonen

```bash
git clone [https://github.com/bausi2k/hyundai-python-server.git](https://github.com/bausi2k/hyundai-python-server.git)
cd hyundai-python-server
```

#### 3.2 Konfiguration (`.env`)

Erstelle eine Datei namens `.env` im Projektverzeichnis:

```bash
vi .env
```

Füge folgenden Inhalt ein und passe deine Daten an:

```ini
# --- Zugangsdaten ---
BLUELINK_USERNAME=deine_email@example.com
BLUELINK_PASSWORD=DeinPasswort
BLUELINK_PIN=1234
BLUELINK_VIN=DEINE_17_STELLIGE_VIN

# --- Einstellungen ---
# 1 = Europa, 2 = USA, 3 = Kanada
BLUELINK_REGION_ID=1
# 1 = Kia, 2 = Hyundai
BLUELINK_BRAND_ID=2
# Interner Port im Container (auf 8080 lassen)
PORT=8080
# Log Level (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO

# --- Synology Chat Alarme (Optional) ---
SYNOLOGY_CHAT_ENABLED=true
SYNOLOGY_CHAT_URL=https://deine-synology-url/webapi/entry.cgi?api=SYNO.Chat.External&method=incoming&version=2&token=...
```

#### 3.3 Server starten

```bash
docker compose up -d --build
```

Der Server ist nun unter `http://<IP-DEINES-PI>:8444` erreichbar (Port 8444 ist der Standard in der `docker-compose.yml`).

#### 3.4 Logs ansehen

```bash
docker compose logs -f
```

### 4\. API Endpunkte

Eine Übersicht erhältst du auch unter `GET /info`.

| Methode | Pfad | Beschreibung |
| :--- | :--- | :--- |
| `GET` | `/info` | Zeigt API-Informationen und Version. |
| `GET` | `/status` | Ruft den **gecacheten** Status ab (schnell). |
| `GET` | `/status/refresh` | Erzwingt ein **Live-Update** vom Fahrzeug (langsam, ca. 20s). |
| `POST` | `/lock` | Verriegelt das Fahrzeug. |
| `POST` | `/unlock` | Entriegelt das Fahrzeug. |
| `POST` | `/climate/start` | Startet Klima. Body: `{"temperature": 21, "defrost": false}` |
| `POST` | `/climate/stop` | Stoppt Klima. |
| `POST` | `/charge/start` | Startet Laden. |
| `POST` | `/charge/stop` | Stoppt Laden. |
| `GET` | `/odometer` | Kilometerstand (Cache). |
| `GET` | `/odometer/refresh`| Kilometerstand (Live). |
| `GET` | `/location` | Fahrzeugposition (Live). |

### 5\. Integration mit Node-RED

Die API antwortet mit JSON. Ein typischer Flow:

1.  **Inject Node:** Alle 15 Min triggern.
2.  **HTTP Request:** `GET http://localhost:8444/status` (Nutze `/status/refresh` sparsam, um die 12V Batterie zu schonen).
3.  **Function Node:** Extrahiert `msg.payload.data`.
4.  **Output:** Speichern in InfluxDB oder MQTT.

### 6\. Manuelle Installation (Ohne Docker)

Falls du den Server direkt als Python-Skript laufen lassen willst (z.B. zur Entwicklung):

1.  **Setup:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```
2.  **Starten:**
    ```bash
    python3 hyundai_server.py
    ```

### 7\. Troubleshooting

  * **Login Failed / 400 Bad Request:** Überprüfe Benutzername und Passwort in der `.env`. Logge dich einmal manuell in der offiziellen Bluelink App ein.
  * **429 Too Many Requests:** Du sendest zu viele Befehle zu schnell hintereinander. Warte eine Minute (Cool-down Phase der API).
  * **500 Internal Server Error:** Prüfe die Logs (`docker compose logs`). Wenn `SYNOLOGY_CHAT_ENABLED=true`, solltest du eine Nachricht erhalten haben.

## 🤝 Credits

**#kiassisted** 🤖
This project was created with the assistance of AI.
Code architecture, logic, and documentation support provided by Gemini.

---
<a href="https://www.buymeacoffee.com/bausi2k" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 60px !important;width: 217px !important;" ></a>
