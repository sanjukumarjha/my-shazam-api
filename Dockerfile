# Use a lightweight Python base image
FROM python:3.11-slim

# Install system dependencies (ffmpeg and chromaprint for AcoustID)
RUN apt-get update && \
    apt-get install -y ffmpeg libchromaprint-tools && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy files
COPY requirements.txt .
COPY main.py .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Start the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]
