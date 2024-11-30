#!/bin/bash
###############################################################################
# GPU Monitor - Backend Process
# 
# This script monitors NVIDIA GPU metrics and provides real-time data for the
# dashboard. It handles:
# - Real-time GPU metrics collection
# - Historical data management
# - Log rotation and cleanup
# - Data persistence through system updates
# - Error recovery and resilience
#
# Dependencies:
# - nvidia-smi
# - Python 3.12+
# - Basic Unix utilities
###############################################################################

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
INTERVAL=4  # Time between GPU checks (seconds)
BUFFER_SIZE=15  # Number of readings before writing to history (15 * 4s = 1 minute)

# Debug toggle (comment out to disable debug logging)
# DEBUG=true

# Create required directories
mkdir -p "$LOG_DIR"

###############################################################################
# Logging Functions
# These functions handle different levels of logging with timestamps
###############################################################################

# Log error messages to both console and error log file
log_error() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] ERROR: $1" | tee -a "$ERROR_LOG"
}

# Log warning messages to warning log file
log_warning() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] WARNING: $1" | tee -a "$WARNING_LOG"
}

# Log debug messages when debug mode is enabled
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

###############################################################################
# process_historical_data: Manages historical GPU metrics
# Handles data persistence and file permissions across system updates
# Creates and maintains history.json with error recovery
###############################################################################
function process_historical_data() {
    local output_file="$HISTORY_DIR/history.json"
    local temp_file="${output_file}.tmp"

    # Add diagnostic info
    log_debug "File permissions before update:"
    ls -l "$output_file" 2>&1 | log_debug
    ls -l "$HISTORY_DIR" 2>&1 | log_debug

    # Test write permissions explicitly
    if ! touch "$temp_file" 2>/dev/null; then
        log_error "Cannot create temp file in $HISTORY_DIR"
        log_error "Directory permissions: $(ls -ld $HISTORY_DIR)"
        return 1
    fi

    python3 /tmp/format_json.py "$output_file" < "$LOG_FILE" > "$temp_file" 2> >(grep -v "No such file or directory" >> "$ERROR_LOG")
    
    if [ -s "$temp_file" ]; then
        # Compare sizes
        local new_size=$(wc -c < "$temp_file")
        local old_size=$(wc -c < "$output_file" 2>/dev/null || echo '0')
        log_debug "New content size: $new_size"
        log_debug "Old content size: $old_size"
        
        if [ "$new_size" != "$old_size" ]; then
            mv "$temp_file" "$output_file"
            # Check if permissions need updating
            current_perms=$(stat -c "%a" "$output_file")
            if [ "$current_perms" != "666" ]; then
                chmod 666 "$output_file"
                log_debug "Updated file permissions"
            fi
        else
            rm -f "$temp_file"  # Clean up if no changes
        fi
    fi

    # Create the Python script - note the closing PYTHONSCRIPT must be at start of line
cat > /tmp/format_json.py << 'PYTHONSCRIPT'
import sys
import json
from datetime import datetime, timedelta 
import os

def load_existing_data(file_path):
    # Initialize default empty data structure
    default_data = {
        "timestamps": [],
        "temperatures": [],
        "utilizations": [],
        "memory": [],
        "power": []
    }
    
    # If file doesn't exist or is empty, return default data
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return default_data
        
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
            
        # Trim old data while loading
        current_time = datetime.now()
        cutoff = current_time - timedelta(hours=24, minutes=10)
        current_year = current_time.year
        
        # Find index where to start keeping data
        valid_indices = []
        for i, timestamp in enumerate(data['timestamps']):
            dt = datetime.strptime(f"{current_year} {timestamp}", "%Y %m-%d %H:%M:%S")
            if dt >= cutoff:
                valid_indices.append(i)
                
        # Keep only data within our window
        return {
            'timestamps': [data['timestamps'][i] for i in valid_indices],
            'temperatures': [data['temperatures'][i] for i in valid_indices],
            'utilizations': [data['utilizations'][i] for i in valid_indices],
            'memory': [data['memory'][i] for i in valid_indices],
            'power': [data['power'][i] for i in valid_indices]
        }
    except (json.JSONDecodeError, KeyError, FileNotFoundError) as e:
        # If any error occurs during loading/parsing, return default data
        return default_data

# Initialize data structure
data = load_existing_data(sys.argv[1])

# write test, after loading but before processing
try:
    with open(sys.argv[1], 'a') as f:
        f.write("")  # Test write access
except Exception as e:
    print(f"Write test failed restart container to fix: {e}", file=sys.stderr)
    sys.exit(1)

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

     # Process data with better error handling
    if ! python3 /tmp/format_json.py "$output_file" < "$LOG_FILE" > "$temp_file"; then
        log_error "Python processing failed"
        rm -f "$temp_file"
        rm -f "$lock_file"
        return
    fi

    if [ -s "$temp_file" ]; then
        if ! mv "$temp_file" "$output_file"; then
            log_error "Failed to move temp file to output"
            rm -f "$temp_file"
            rm -f "$lock_file"
            return
        fi
        log_debug "Updated history file"
    else
        log_error "Failed to create history file - temp file empty"
        rm -f "$temp_file"
    fi

    rm -f "$lock_file"
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

###############################################################################
# rotate_logs: Manages log file sizes and retention
# Rotates logs based on:
# - Size limit (10MB)
# - Age limit (2 days)
# Handles: error.log, warning.log, gpu_stats.log
###############################################################################
rotate_logs() {
    local max_size=$((10 * 1024 * 1024))  # 10MB size limit
    local max_age=$((2 * 24 * 3600))      # 2 day retention
    local current_time=$(date +%s)

    rotate_log_file() {
        local log_file=$1
        local timestamp=$(date '+%Y%m%d-%H%M%S')
        
        # Size-based rotation
        if [[ -f "$log_file" && $(stat -f%z "$log_file" 2>/dev/null || stat -c%s "$log_file") -gt $max_size ]]; then
            mv "$log_file" "${log_file}.${timestamp}"
            touch "$log_file"
            log_debug "Rotated $log_file due to size"
        fi

        # Age-based cleanup
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

###############################################################################
# safe_write_json: Safely writes JSON data to prevent corruption
# Arguments:
#   $1 - Target file path
#   $2 - JSON content to write
# Returns:
#   0 on success, 1 on failure
###############################################################################
function safe_write_json() {
    local file="$1"
    local content="$2"
    local temp="${file}.tmp"
    local backup="${file}.bak"
    
    # Write to temp file
    echo "$content" > "$temp"
    
    # Verify temp file was written successfully
    if [ -s "$temp" ]; then
        # Create backup of current file if it exists
        [ -f "$file" ] && cp "$file" "$backup"
        
        # Atomic move of temp to real file
        mv "$temp" "$file"
        
        # Clean up backup if everything succeeded
        [ -f "$backup" ] && rm "$backup"
        
        return 0
    else
        log_error "Failed to write to temp file: $temp"
        # Restore from backup if available
        [ -f "$backup" ] && mv "$backup" "$file"
        return 1
    fi
}

###############################################################################
# process_buffer: Safely handles buffered GPU metrics data
# Implements atomic write operations to prevent data loss during system updates
# Returns: 0 on success, 1 on failure
###############################################################################
function process_buffer() {
    local temp_file="${BUFFER_FILE}.tmp"
    local success=0
    
    # Create temp file with buffer contents
    if cp "$BUFFER_FILE" "$temp_file"; then
        # Clear original buffer only after successful copy
        > "$BUFFER_FILE"
        
        # Append temp contents to log file
        if cat "$temp_file" >> "$LOG_FILE"; then
            success=1
        else
            log_error "Failed to append buffer to log file"
        fi
    else
        log_error "Failed to create temp buffer file"
    fi
    
    # Clean up temp file
    rm -f "$temp_file"
    
    # If operation failed, try to restore buffer
    if [ $success -eq 0 ]; then
        cat "$temp_file" >> "$BUFFER_FILE"
    fi
}

###############################################################################
# update_stats: Core function for GPU metrics collection and processing
# Collects GPU metrics every INTERVAL seconds and manages data flow
# Handles:
# - GPU metric collection via nvidia-smi
# - Buffer management
# - JSON updates for real-time display
# - Error recovery for system updates and GPU access issues
# Returns: 0 on success, 1 on failure
###############################################################################
update_stats() {
    local write_failed=0
    
    # Collect current GPU metrics
    local timestamp=$(date '+%m-%d %H:%M:%S')
    local gpu_stats=$(nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,memory.used,power.draw \
                     --format=csv,noheader,nounits 2>/dev/null)
    
    if [[ -n "$gpu_stats" ]]; then
        # Verify write access before proceeding
        if ! touch "$BUFFER_FILE" 2>/dev/null; then
            log_error "Cannot write to buffer file"
            return 1
        fi

        # Buffer write with error handling
        if ! echo "$timestamp,$gpu_stats" >> "$BUFFER_FILE"; then
            log_error "Failed to write to buffer"
            write_failed=1
        fi

        # Detailed error logging for debugging
        if [[ $write_failed -eq 1 ]]; then
            log_error "Buffer write details:"
            ls -l "$BUFFER_FILE" 2>&1 | log_error
            df -h "$(dirname "$BUFFER_FILE")" 2>&1 | log_error
        fi

        # Update current stats JSON for real-time display
        local temp=$(echo "$gpu_stats" | cut -d',' -f1 | tr -d ' ')
        local util=$(echo "$gpu_stats" | cut -d',' -f2 | tr -d ' ')
        local mem=$(echo "$gpu_stats" | cut -d',' -f3 | tr -d ' ')
        local power=$(echo "$gpu_stats" | cut -d',' -f4 | tr -d ' []')

        # Handle N/A power value
        if [[ "$power" == "N/A" || -z "$power" || "$power" == "[N/A]" ]]; then
            power="0"
        fi
        
        # Create JSON content
        local json_content=$(cat << EOF
{
    "timestamp": "$timestamp",
    "temperature": $temp,
    "utilization": $util,
    "memory": $mem,
    "power": $power
}
EOF
)
        # Write JSON safely
        safe_write_json "$JSON_FILE" "$json_content"

        # Process buffer when full
        if [[ -f "$BUFFER_FILE" ]] && [[ $(wc -l < "$BUFFER_FILE") -ge $BUFFER_SIZE ]]; then
            process_buffer
            process_historical_data
            process_24hr_stats
        fi
    else
        log_error "Failed to get GPU stats output"
    fi
}

# Start web server in background using Python server
cd /app && python3 server.py &

###############################################################################
# Main Process Loop
# Manages the continuous monitoring process with:
# - Retry mechanism for failed updates
# - Hourly log rotation
# - Error resilience during system updates
###############################################################################
while true; do
    # Update tracking with retry mechanism
    update_success=0
    max_retries=3
    retry_count=0

    # Retry loop for failed updates
    while [ $update_success -eq 0 ] && [ $retry_count -lt $max_retries ]; do
        if update_stats; then
            update_success=1
        else
            retry_count=$((retry_count + 1))
            log_warning "Update failed, attempt $retry_count of $max_retries"
            sleep 1
        fi
    done

    # Handle complete update failure
    if [ $update_success -eq 0 ]; then
        log_error "Multiple update attempts failed, continuing to next cycle"
    fi
    
    # Hourly log rotation and nightly history cleanup
    if [ $(date +%M) -eq 0 ]; then
        rotate_logs
    fi
    
    sleep $INTERVAL
done