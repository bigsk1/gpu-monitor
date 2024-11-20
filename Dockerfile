FROM python:3.12-slim

# Install required packages
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Create necessary directories
RUN mkdir -p /app/data /app/history /app/logs

# Copy application files
COPY gpu_stats.html /app/
COPY monitor_gpu.sh /app/

# Make scripts executable
RUN chmod +x /app/monitor_gpu.sh

# Expose port for web server
EXPOSE 8081

# Start the application
CMD ["./monitor_gpu.sh"]