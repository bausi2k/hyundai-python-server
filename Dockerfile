# Verwende ein schlankes Python-Image als Basis
FROM python:3.11-slim

# Setze das Arbeitsverzeichnis im Container
WORKDIR /app

# Kopiere requirements.txt zuerst, um Docker-Cache zu nutzen
COPY requirements.txt .

# Installiere Abhängigkeiten
# --no-cache-dir hält das Image klein
RUN pip install --no-cache-dir -r requirements.txt

# Kopiere den restlichen Code
COPY . .

# Exponiere den Port (dokumentarisch)
EXPOSE 8444

# Definiere den Startbefehl
# Unbuffered output sorgt dafür, dass Logs sofort in 'docker logs' erscheinen
CMD ["python", "-u", "hyundai_server.py"]