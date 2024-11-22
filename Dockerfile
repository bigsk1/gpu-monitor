FROM python:3.12-slim

# Install required packages
RUN apt-get update && apt-get install -y \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Install aiohttp
RUN pip install aiohttp

# Create app directory
WORKDIR /app

# Create necessary directories
RUN mkdir -p /app/history /app/logs /app/images

# Copy application files
COPY gpu-stats.html /app/
COPY monitor_gpu.sh /app/
COPY server.py /app/
COPY images/ /app/images/
COPY sounds/ /app/sounds/

# Make scripts executable
RUN chmod +x /app/monitor_gpu.sh

# Expose port for web server
EXPOSE 8081

# Start the application
CMD ["./monitor_gpu.sh"]