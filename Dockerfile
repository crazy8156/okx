# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /app

# Install system dependencies required for TA-Lib and building Python packages
RUN apt-get update && apt-get install -y \
    gcc \
    build-essential \
    wget \
    tar \
    && rm -rf /var/lib/apt/lists/*

# Download and compile TA-Lib (C Library)
# TA-Lib python wrapper needs this C library installed in the system
RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar -xzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib && \
    ./configure --prefix=/usr && \
    make && \
    make install && \
    cd .. && \
    rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose port (Render sets PORT env va, but good to document)
EXPOSE 8000

# Run the application
# Use shell form to allow variable expansion if needed, but array form is safer.
# We bind to 0.0.0.0 and use the PORT environment variable provided by Render (defaulting to 8000)
CMD ["sh", "-c", "uvicorn okx_bot.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
