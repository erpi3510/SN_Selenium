FROM python:3.11

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    unzip \
    gnupg \
    ca-certificates \
    fonts-liberation \
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
    libu2f-udev \
    libvulkan1 \
    libxshmfence1

# Install Google Chrome for Testing (Version 136)
RUN wget -O /tmp/chrome.deb https://storage.googleapis.com/chrome-for-testing-public/136.0.7103.92/linux64/chrome-linux64.zip && \
    unzip /tmp/chrome.deb -d /opt/google/chrome && \
    rm /tmp/chrome.deb

# Install matching ChromeDriver (Version 136 for Chrome for Testing)
RUN wget -O /tmp/chromedriver.zip https://storage.googleapis.com/chrome-for-testing-public/136.0.7103.92/linux64/chromedriver-linux64.zip && \
    unzip /tmp/chromedriver.zip -d /usr/local/bin/ && \
    chmod +x /usr/local/bin/chromedriver && \
    rm /tmp/chromedriver.zip

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your application
COPY . .

# Set the entry point (Python script to run)
CMD ["python", "snc.py"]
