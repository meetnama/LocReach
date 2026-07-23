FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CHROME_BIN=/usr/bin/google-chrome \
    CHROMIUM_PATH=/usr/bin/google-chrome

# Chrome + fonts (needed for Selenium / undetected-chromedriver parity with local HDD)
RUN apt-get update && apt-get install -y --no-install-recommends \
      wget gnupg ca-certificates unzip curl \
      fonts-liberation fonts-noto-color-emoji \
      libnss3 libatk-bridge2.0-0 libgtk-3-0 libx11-xcb1 \
      libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2 \
      libpangocairo-1.0-0 libpango-1.0-0 libcups2 libdrm2 \
    && wget -qO- https://dl.google.com/linux/linux_signing_key.pub \
      | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
      > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Streamlit on Render's assigned port
CMD ["sh", "-c", "streamlit run Domain_Discovery.py --server.port=${PORT:-8501} --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false"]
