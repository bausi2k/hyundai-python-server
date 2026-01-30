# Wir nutzen ein schlankes Python 3.11 Image
FROM python:3.11-slim

# Umgebungsvariablen setzen (verhindert .pyc Dateien und Pufferung)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Arbeitsverzeichnis im Container
WORKDIR /app

# System-Abhängigkeiten installieren (git wird für die Installation der Library benötigt)
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Requirements kopieren und installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Den restlichen Code kopieren
COPY . .

# Ordner für Logs erstellen (wichtig für deinen Code!)
RUN mkdir -p logs

# Port freigeben
EXPOSE 8444

# Server starten
CMD ["python", "hyundai_server.py"]