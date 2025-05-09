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
    apt-get install -y ./google-chrome.deb && \
    rm google-chrome.deb

# Automatisch passende ChromeDriver-Version zur installierten Chrome-Version installieren
RUN CHROME_VERSION=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+') && \
    echo "Detected Chrome version: $CHROME_VERSION" && \
    MAJOR_VERSION=$(echo $CHROME_VERSION | cut -d '.' -f 1) && \
    DRIVER_URL=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json" \
        | python3 -c "import sys, json; print([v['downloads']['chromedriver'][0]['url'] for k,v in json.load(sys.stdin)['versions'].items() if v['version'].startswith('$CHROME_VERSION') or v['version'].startswith('$MAJOR_VERSION.')][0])") && \
    echo "Downloading ChromeDriver from $DRIVER_URL" && \
    wget -q -O /tmp/chromedriver.zip "$DRIVER_URL" && \
    unzip /tmp/chromedriver.zip -d /tmp/ && \
    mv /tmp/chromedriver*/chromedriver /usr/local/bin/chromedriver && \
    chmod +x /usr/local/bin/chromedriver && \
    rm -rf /tmp/chromedriver*

# Python-Abhängigkeiten installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Arbeitsverzeichnis setzen
WORKDIR /app
COPY . .

# Standardausführung
CMD ["python", "snc.py"]