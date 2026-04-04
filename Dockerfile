# syntax=docker/dockerfile:1

# Base image
FROM python:3.11-slim

# Install system dependencies for Chromium/Selenium
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Environment variables for Selenium to find Chromium in Debian/Ubuntu
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Expose the port (Render handles this, but good practice)
EXPOSE 10000

# Start the Flask app using Gunicorn
# Using 4 workers and binding to port 10000 (Render's default)
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--workers", "1", "--threads", "8", "--timeout", "0", "app:app"]
