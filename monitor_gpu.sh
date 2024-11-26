#!/bin/bash

BASE_DIR="/app"
LOG_FILE="$BASE_DIR/gpu_stats.log"
STATS_FILE="$BASE_DIR/gpu_24hr_stats.txt"
JSON_FILE="$BASE_DIR/gpu_current_stats.json"
HISTORY_DIR="$BASE_DIR/history"
LOG_DIR="$BASE_DIR/logs"
ERROR_LOG="$LOG_DIR/error.log"
WARNING_LOG="$LOG_DIR/warning.log"
DEBUG_LOG="$LOG_DIR/debug.log"
BUFFER_FILE="/tmp/stats_buffer"
INTERVAL=4  # update interval seconds
BUFFER_SIZE=15  # 60 seconds / 4 second interval = 15 readings

# Debug toggle (comment out to disable debug logging)
# DEBUG=true

# Create required directories
mkdir -p "$LOG_DIR"

# Function to log messages
log_error() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] ERROR: $1" | tee -a "$ERROR_LOG"
}

log_warning() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] WARNING: $1" | tee -a "$WARNING_LOG"
}

log_debug() {
    if [ "${DEBUG:-}" = "true" ]; then
        local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
        echo "[$timestamp] DEBUG: $1" >> "$DEBUG_LOG"
    fi
}

# Get GPU name and save to config
GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' || echo "GPU")
CONFIG_FILE="$BASE_DIR/gpu_config.json"

# Create config JSON with GPU name
cat > "$CONFIG_FILE" << EOF
{
    "gpu_name": "${GPU_NAME}"
}
EOF

# Function to process historical data
function process_historical_data() {
    local output_file="$HISTORY_DIR/history.json"
    local temp_file="${output_file}.tmp"

    if [ ! -f "$LOG_FILE" ]; then
        log_warning "No log file found when processing historical data"
        return
    fi

    # Create the Python script - note the closing PYTHONSCRIPT must be at start of line
cat > /tmp/format_json.py << 'PYTHONSCRIPT'
import sys
import json
from datetime import datetime
import os

def load_existing_data(file_path):
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except:
            return None
    return None

data = {
    "timestamps": [],
    "temperatures": [],
    "utilizations": [],
    "memory": [],
    "power": []
}

existing_data = load_existing_data(sys.argv[1])
if existing_data:
    data = existing_data

BATCH_SIZE = 10
data_buffer = []

for line in sys.stdin:
    try:
        timestamp, temp, util, mem, power = line.strip().split(',')
        try:
            power_val = float(power) if power.strip() != 'N/A' else 0
        except (ValueError, AttributeError):
            power_val = 0

        data_buffer.append({
            "timestamp": timestamp,
            "temperature": float(temp),
            "utilization": float(util),
            "memory": float(mem),
            "power": power_val
        })
        
        if len(data_buffer) >= BATCH_SIZE:
            for entry in data_buffer:
                if entry["timestamp"] not in data["timestamps"]:
                    data["timestamps"].append(entry["timestamp"])
                    data["temperatures"].append(entry["temperature"])
                    data["utilizations"].append(entry["utilization"])
                    data["memory"].append(entry["memory"])
                    data["power"].append(entry["power"])
            data_buffer = []
    except Exception as e:
        continue

for entry in data_buffer:
    if entry["timestamp"] not in data["timestamps"]:
        data["timestamps"].append(entry["timestamp"])
        data["temperatures"].append(entry["temperature"])
        data["utilizations"].append(entry["utilization"])
        data["memory"].append(entry["memory"])
        data["power"].append(entry["power"])

print(json.dumps(data, indent=4))
PYTHONSCRIPT

    python3 /tmp/format_json.py "$output_file" < "$LOG_FILE" > "$temp_file"

    if [ -s "$temp_file" ]; then
        mv "$temp_file" "$output_file"
        chmod 666 "$output_file"
        log_debug "Updated history file"
    else
        log_error "Failed to create history file"
        rm -f "$temp_file"
    fi

    rm -f /tmp/format_json.py
}

# Function to process 24-hour stats
process_24hr_stats() {
    if [ ! -f "$LOG_FILE" ]; then
        log_warning "No log file found when processing 24hr stats"
        return
    fi

 cat > /tmp/process_stats.py << 'EOF'
import sys
from datetime import datetime, timedelta
import json

cutoff_time = datetime.now() - timedelta(hours=24)
current_year = datetime.now().year

temp_min, temp_max = float('inf'), float('-inf')
util_min, util_max = float('inf'), float('-inf')
mem_min, mem_max = float('inf'), float('-inf')
power_min, power_max = float('inf'), float('-inf')

for line in sys.stdin:
    try:
        timestamp, temp, util, mem, power = line.strip().split(',')
        dt = datetime.strptime(f"{current_year} {timestamp}", "%Y %m-%d %H:%M:%S")
        
        if dt >= cutoff_time:
            temp = float(temp)
            util = float(util)
            mem = float(mem)
            # Handle N/A power values
            try:
                power = float(power) if power.strip() != 'N/A' else 0
            except (ValueError, AttributeError):
                power = 0
            
            temp_min = min(temp_min, temp)
            temp_max = max(temp_max, temp)
            util_min = min(util_min, util)
            util_max = max(util_max, util)
            mem_min = min(mem_min, mem)
            mem_max = max(mem_max, mem)
            if power > 0:  # Only update power min/max if power is reported
                power_min = min(power_min, power)
                power_max = max(power_max, power)
    except:
        continue

# Handle case where no data was processed
if temp_min == float('inf'):
    temp_min = temp_max = util_min = util_max = mem_min = mem_max = 0

# Special handling for power stats when not available
if power_min == float('inf') or power_max == float('-inf'):
    power_min = power_max = 0

stats = {
    "stats": {
        "temperature": {"min": temp_min, "max": temp_max},
        "utilization": {"min": util_min, "max": util_max},
        "memory": {"min": mem_min, "max": mem_max},
        "power": {"min": power_min, "max": power_max}
    }
}

print(json.dumps(stats, indent=4))
EOF

    python3 /tmp/process_stats.py < "$LOG_FILE" > "$STATS_FILE"
    chmod 666 "$STATS_FILE"
    rm /tmp/process_stats.py
}

# Function to rotate logs
rotate_logs() {
    local max_size=$((10 * 1024 * 1024))  # 10MB
    local max_age=$((2 * 24 * 3600))      # 2 days in seconds
    local current_time=$(date +%s)

    # Function to check and rotate a specific log file
    rotate_log_file() {
        local log_file=$1
        local timestamp=$(date '+%Y%m%d-%H%M%S')

        # Check file size
        if [[ -f "$log_file" && $(stat -f%z "$log_file" 2>/dev/null || stat -c%s "$log_file") -gt $max_size ]]; then
            mv "$log_file" "${log_file}.${timestamp}"
            touch "$log_file"
            log_debug "Rotated $log_file due to size"
        fi

        # Remove old rotated logs
        find "$(dirname "$log_file")" -name "$(basename "$log_file").*" -type f | while read rotated_log; do
            local file_time=$(stat -f%m "$rotated_log" 2>/dev/null || stat -c%Y "$rotated_log")
            if (( current_time - file_time > max_age )); then
                rm "$rotated_log"
                log_debug "Removed old log: $rotated_log"
            fi
        done
    }

    # Rotate error and warning logs
    rotate_log_file "$ERROR_LOG"
    rotate_log_file "$WARNING_LOG"
    rotate_log_file "$LOG_FILE"
}

# Update the update_stats function
update_stats() {
    # Get current stats
    local timestamp=$(date '+%m-%d %H:%M:%S')
    # For testing, replace the nvidia-smi command with:
    # local gpu_stats="44, 0, 3, [N/A]"
    local gpu_stats=$(nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,memory.used,power.draw \
                     --format=csv,noheader,nounits 2>/dev/null)
    
    if [[ -n "$gpu_stats" ]]; then
        # Append to buffer
        echo "$timestamp,$gpu_stats" >> "$BUFFER_FILE"

        # Update current stats JSON for real-time display
        local temp=$(echo "$gpu_stats" | cut -d',' -f1 | tr -d ' ')
        local util=$(echo "$gpu_stats" | cut -d',' -f2 | tr -d ' ')
        local mem=$(echo "$gpu_stats" | cut -d',' -f3 | tr -d ' ')
        local power=$(echo "$gpu_stats" | cut -d',' -f4 | tr -d ' []')  # Remove both [ and ]

        # Handle N/A power value - now handles both N/A and [N/A]
        if [[ "$power" == "N/A" || -z "$power" || "$power" == "[N/A]" ]]; then
            power="0"  # Using 0 as default for N/A power values
        fi

        cat > "$JSON_FILE" << EOF
{
    "timestamp": "$timestamp",
    "temperature": $temp,
    "utilization": $util,
    "memory": $mem,
    "power": $power
}
EOF
        chmod 666 "$JSON_FILE"

        # Process buffer when full (15 readings = 1 minute)
        if [[ -f "$BUFFER_FILE" ]] && [[ $(wc -l < "$BUFFER_FILE") -ge $BUFFER_SIZE ]]; then
            cat "$BUFFER_FILE" >> "$LOG_FILE"
            process_historical_data
            process_24hr_stats
            > "$BUFFER_FILE"  # Clear buffer
            log_debug "Processed buffered data"
        fi
    else
        log_error "Failed to get GPU stats output"
    fi
}

# Start web server in background using the new Python server
cd /app && python3 server.py &

# Main loop
while true; do
    update_stats
    
    # Run log rotation every hour
    if [ $(date +%M) -eq 0 ]; then
        rotate_logs
    fi
    
    sleep $INTERVAL
done