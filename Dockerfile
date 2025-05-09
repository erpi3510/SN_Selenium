# Verwenden des offiziellen Python-Images
FROM python:3.11

# Installiere benötigte Pakete
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    unzip \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    jq \
    google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Installiere Chrome und lade den passenden ChromeDriver
RUN CHROME_VERSION=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+') && \
    DRIVER_VERSION=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json" \
    | jq -r --arg v "$CHROME_VERSION" '.channels.Stable.version') && \
    curl -Lo /tmp/chromedriver.zip "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/${DRIVER_VERSION}/linux64/chromedriver-linux64.zip" && \
    unzip /tmp/chromedriver.zip -d /usr/local/bin && \
    chmod +x /usr/local/bin/chromedriver && \
    rm /tmp/chromedriver.zip

# Setze das Arbeitsverzeichnis
WORKDIR /app

# Kopiere requirements.txt in das Arbeitsverzeichnis
COPY requirements.txt .

# Installiere Python-Abhängigkeiten
RUN pip install --no-cache-dir -r requirements.txt

# Kopiere den Rest der Anwendung
COPY . .

# Setze den Startbefehl (kann später nach Bedarf angepasst werden)
CMD ["python", "snc.py"]