#!/bin/bash

# File paths - everything in the web root
BASE_DIR="/app"
LOG_FILE="$BASE_DIR/gpu_stats.log"
STATS_FILE="$BASE_DIR/gpu_24hr_stats.txt"
JSON_FILE="$BASE_DIR/gpu_current_stats.json"
HISTORY_DIR="$BASE_DIR/history"

# Create required directories
mkdir -p "$HISTORY_DIR"

# Get GPU name and save to config
GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' || echo "GPU")

CONFIG_FILE="$BASE_DIR/gpu_config.json"

# Create config JSON with GPU name
cat > "$CONFIG_FILE" << EOF
{
    "gpu_name": "${GPU_NAME}"
}
EOF

# Function to process historical data for different timeframes
function process_historical_data() {
    local hours=$1
    local output_file="$HISTORY_DIR/history_${hours}h.json"
    local cutoff_time=$(date -d "-$hours hours" +%s)

    # Create a temporary Python script for JSON formatting
    cat > /tmp/format_json.py << 'PYTHONSCRIPT'
import sys
import json
from datetime import datetime

data = {
    "timestamps": [],
    "temperatures": [],
    "utilizations": [],
    "memory": [],
    "power": []
}

for line in sys.stdin:
    try:
        timestamp, temp, util, mem, power = line.strip().split(',')
        data["timestamps"].append(timestamp)
        data["temperatures"].append(float(temp))
        data["utilizations"].append(float(util))
        data["memory"].append(float(mem))
        data["power"].append(float(power))
    except:
        continue

print(json.dumps(data, indent=4))
PYTHONSCRIPT

    python3 /tmp/format_json.py < "$LOG_FILE" > "$output_file"
    rm /tmp/format_json.py
}

# Function to process 24-hour stats
process_24hr_stats() {
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
    
    # Get all metrics in a single call
    local gpu_stats=$(nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,memory.used,power.draw \
                     --format=csv,noheader,nounits 2>/dev/null)
    
    if [[ -n "$gpu_stats" ]]; then
        # Parse the comma-separated values
        local temp=$(echo "$gpu_stats" | cut -d',' -f1 | tr -d ' ')
        local util=$(echo "$gpu_stats" | cut -d',' -f2 | tr -d ' ')
        local mem=$(echo "$gpu_stats" | cut -d',' -f3 | tr -d ' ')
        local power=$(echo "$gpu_stats" | cut -d',' -f4 | tr -d ' ')

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
            echo "Invalid GPU stats values, retrying in 5 seconds..."
        fi
    else
        echo "Failed to get GPU stats, retrying in 5 seconds..."
    fi
}

# Start web server in background
cd /app && python3 -m http.server 8081 &

# Main loop
while true; do
    update_stats
    sleep 5
done