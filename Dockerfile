FROM python:3.11-slim

# Install system dependencies for Flet/Python if needed
RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Flet uses PORT environment variable provided by Cloud Run
ENV PORT 8080

# Run the application
CMD ["python", "main.py"]
