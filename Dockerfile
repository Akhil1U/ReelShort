FROM python:3.12-slim

# System deps: ffmpeg, Node.js, Chromium (for puppeteer inside po-token-generator)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    npm \
    chromium \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libxshmfence1 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Tell puppeteer to use the system Chromium and skip downloading its own
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV CHROME_PATH=/usr/bin/chromium

RUN npm install -g youtube-po-token-generator

# Copy puppeteer config so --no-sandbox is always passed (required in Docker)
COPY .puppeteerrc.cjs /root/.puppeteerrc.cjs

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY ui.py .

EXPOSE 8501

ENTRYPOINT ["streamlit", "run", "ui.py", "--server.address=0.0.0.0", "--server.port=8501"]
