FROM python:3.11-slim

# System-Tools installieren
RUN apt-get update && apt-get install -y \
    curl \
    unzip \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libatk-bridge2.0-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libgtk-3-0 \
    wget \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Google Chrome installieren (Version 138)
RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt-get update && \
    apt-get install -y ./google-chrome-stable_current_amd64.deb && \
    rm google-chrome-stable_current_amd64.deb

# Passenden ChromeDriver (v138) installieren
RUN wget https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/138.0.7204.94/linux64/chromedriver-linux64.zip -O chromedriver.zip && \
    unzip chromedriver.zip && \
    mv chromedriver-linux64/chromedriver /usr/local/bin/chromedriver && \
    chmod +x /usr/local/bin/chromedriver && \
    rm -rf chromedriver*

# Arbeitsverzeichnis setzen
WORKDIR /app

# Projektdateien hinzufügen
COPY . /app

# Abhängigkeiten installieren
RUN pip install --no-cache-dir -r requirements.txt

# Umgebungsvariablen für headless Chrome (falls nötig)
ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROMEDRIVER=/usr/local/bin/chromedriver

# Startbefehl
CMD ["python", "snc.py"]