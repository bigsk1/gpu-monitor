#!/bin/bash

# File paths - everything in the web root
BASE_DIR="/app"
LOG_FILE="$BASE_DIR/gpu_stats.log"
STATS_FILE="$BASE_DIR/gpu_24hr_stats.txt"
JSON_FILE="$BASE_DIR/gpu_current_stats.json"
HISTORY_DIR="$BASE_DIR/history"
LOG_DIR="$BASE_DIR/logs"
ERROR_LOG="$LOG_DIR/error.log"
WARNING_LOG="$LOG_DIR/warning.log"
DEBUG_LOG="$LOG_DIR/debug.log"

# Create required directories
# mkdir -p "$HISTORY_DIR"
mkdir -p "$LOG_DIR"

# DEBUG=true  # Uncomment to enable debug logging on host when volume mapping persist logs

# log_debug function to check for DEBUG
log_debug() {
    if [ "${DEBUG:-}" = "true" ]; then
        local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
        echo "[$timestamp] DEBUG: $1" >> "$DEBUG_LOG"
    fi
}


if [ -d "$HISTORY_DIR" ] && [ -n "$(ls -A $HISTORY_DIR)" ]; then
    log_debug "Found existing history data"
else
    log_debug "No existing history data found, starting fresh"
fi

# Function to log messages
log_error() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] ERROR: $1" | tee -a "$ERROR_LOG"
}

log_warning() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] WARNING: $1" | tee -a "$WARNING_LOG"
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

    # Rotate each log file
    rotate_log_file "$ERROR_LOG"
    rotate_log_file "$WARNING_LOG"
    rotate_log_file "$DEBUG_LOG"
    rotate_log_file "$LOG_FILE"
}

# Function to process historical data for different timeframes
function process_historical_data() {
    local hours=$1
    local output_file="$HISTORY_DIR/history_${hours}h.json"
    local temp_file="${output_file}.tmp"

    if [ ! -f "$LOG_FILE" ]; then
        log_warning "No log file found when processing ${hours}h historical data"
        return
    fi

    # Create the Python script
    cat > /tmp/format_json.py << 'PYTHONSCRIPT'
import sys
import json
from datetime import datetime, timedelta
import os

hours = int(sys.argv[1])
output_file = sys.argv[2]
cutoff_time = datetime.now() - timedelta(hours=hours)
current_year = datetime.now().year

def load_existing_data():
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r') as f:
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

# Load existing data
existing_data = load_existing_data()
if existing_data:
    data = existing_data

# Process new data
for line in sys.stdin:
    try:
        timestamp, temp, util, mem, power = line.strip().split(',')
        dt = datetime.strptime(f"{current_year} {timestamp}", "%Y %m-%d %H:%M:%S")
        
        if dt >= cutoff_time and timestamp not in data["timestamps"]:
            data["timestamps"].append(timestamp)
            data["temperatures"].append(float(temp))
            data["utilizations"].append(float(util))
            data["memory"].append(float(mem))
            data["power"].append(float(power))
    except Exception as e:
        continue

# Filter data by timeframe
current_time = datetime.now()
cutoff = current_time - timedelta(hours=hours)
valid_data = {
    "timestamps": [],
    "temperatures": [],
    "utilizations": [],
    "memory": [],
    "power": []
}

for i, timestamp in enumerate(data["timestamps"]):
    try:
        dt = datetime.strptime(f"{current_year} {timestamp}", "%Y %m-%d %H:%M:%S")
        if dt >= cutoff:
            valid_data["timestamps"].append(timestamp)
            valid_data["temperatures"].append(data["temperatures"][i])
            valid_data["utilizations"].append(data["utilizations"][i])
            valid_data["memory"].append(data["memory"][i])
            valid_data["power"].append(data["power"][i])
    except:
        continue

print(json.dumps(valid_data, indent=4))
PYTHONSCRIPT

    # Process data
    python3 /tmp/format_json.py "$hours" "$output_file" < "$LOG_FILE" > "$temp_file"

    # If temp file has valid data, move it to final location
    if [ -s "$temp_file" ]; then
        mv "$temp_file" "$output_file"
        # Ensure file permissions allow host access
        chmod 666 "$output_file"
        log_debug "Updated history file for ${hours}h timeframe"
    else
        log_error "Failed to create history for ${hours}h timeframe"
        rm -f "$temp_file"
    fi

    # Cleanup
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
            power = float(power)
            
            temp_min = min(temp_min, temp)
            temp_max = max(temp_max, temp)
            util_min = min(util_min, util)
            util_max = max(util_max, util)
            mem_min = min(mem_min, mem)
            mem_max = max(mem_max, mem)
            power_min = min(power_min, power)
            power_max = max(power_max, power)
    except:
        continue

# Handle case where no data was processed
if temp_min == float('inf'):
    temp_min = temp_max = util_min = util_max = mem_min = mem_max = power_min = power_max = 0

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
    rm /tmp/process_stats.py
}

# Function to update stats
update_stats() {
    local timestamp=$(date '+%m-%d %H:%M:%S')
    # For testing only
    # local timestamp=$(date -d "-$RANDOM seconds" '+%m-%d %H:%M:%S')
    
    # Get all metrics in a single call
    local gpu_stats=$(nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,memory.used,power.draw \
                     --format=csv,noheader,nounits 2>/dev/null)
    
    if [[ -n "$gpu_stats" ]]; then
        # Parse the comma-separated values
        local temp=$(echo "$gpu_stats" | cut -d',' -f1 | tr -d ' ')
        local util=$(echo "$gpu_stats" | cut -d',' -f2 | tr -d ' ')
        local mem=$(echo "$gpu_stats" | cut -d',' -f3 | tr -d ' ')
        local power=$(echo "$gpu_stats" | cut -d',' -f4 | tr -d ' ')

        log_debug "GPU Stats - temp:$temp util:$util mem:$mem power:$power"

        # Check if we got valid numbers
        if [[ -n "$temp" && -n "$util" && -n "$mem" && -n "$power" ]]; then
            # Log data
            echo "$timestamp,$temp,$util,$mem,$power" >> "$LOG_FILE"

            # Create current stats JSON
            cat > "$JSON_FILE" << EOF
{
    "timestamp": "$timestamp",
    "temperature": $temp,
    "utilization": $util,
    "memory": $mem,
    "power": $power
}
EOF

            # Process 24-hour stats
            process_24hr_stats

            # Update historical data for different timeframes
            process_historical_data 1
            process_historical_data 6
            process_historical_data 12
            process_historical_data 24
        else
            log_error "Invalid GPU stats values - temp:$temp util:$util mem:$mem power:$power"
        fi
    else
        log_error "Failed to get GPU stats output"
    fi
}

# Start web server in background
cd /app && python3 -m http.server 8081 &

# Main loop
while true; do
    update_stats
    
    # Run log rotation every hour
    if [ $(date +%M) -eq 0 ]; then
        rotate_logs
    fi
    
    sleep 5
done