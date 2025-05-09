FROM python:3.11

ENV DEBIAN_FRONTEND=noninteractive

# Systemabhängigkeiten installieren
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    unzip \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libgdk-pixbuf2.0-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
    libvulkan1 \
    && rm -rf /var/lib/apt/lists/*

# Google Chrome installieren
RUN wget -q -O google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt-get update && apt-get install -y ./google-chrome.deb && \
    rm google-chrome.deb

# Automatisch passende ChromeDriver-Version zur installierten Chrome-Version holen
RUN CHROME_VERSION=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+') && \
    echo "Installed Chrome version: $CHROME_VERSION" && \
    DRIVER_VERSION=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json" \
        | python3 -c "import sys, json; print(json.load(sys.stdin)['channels']['Stable']['version'])") && \
    echo "Fetching ChromeDriver version: $DRIVER_VERSION" && \
    wget -q -O /tmp/chromedriver.zip "https://storage.googleapis.com/chrome-for-testing-public/${DRIVER_VERSION}/linux64/chromedriver-linux64.zip" && \
    unzip /tmp/chromedriver.zip -d /tmp/ && \
    mv /tmp/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver && \
    chmod +x /usr/local/bin/chromedriver && \
    rm -rf /tmp/chromedriver*

# Python-Abhängigkeiten installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Arbeitsverzeichnis
WORKDIR /app
COPY . .

# Standardausführung
CMD ["python", "snc.py"]