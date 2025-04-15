#!/usr/bin/env python3
"""
GPU Monitor Database Load Test - 3 Days

This script generates synthetic GPU metrics data for 3 days and populates the SQLite
database to test the 3-day history feature.

Usage:
    python3 db_load_3d_test.py [--db-path PATH] [--interval SECONDS]
    
Options:
    --db-path PATH      Path to the SQLite database (default: ../history/gpu_metrics.db)
    --interval SECONDS  Interval between data points in seconds (default: 4)
"""

import argparse
import os
import random
import sqlite3
import sys
import time
from datetime import datetime, timedelta

def parse_args():
    parser = argparse.ArgumentParser(description='GPU Monitor Database Load Test - 3 Days')
    parser.add_argument('--db-path', default='../history/gpu_metrics.db',
                        help='Path to the SQLite database')
    parser.add_argument('--interval', type=float, default=4,
                        help='Interval between data points in seconds')
    parser.add_argument('--batch-size', type=int, default=1000,
                        help='Number of records to insert in a single transaction')
    return parser.parse_args()

def create_db_schema(conn):
    """Create the database schema if it doesn't exist"""
    print("Ensuring database schema exists...")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS gpu_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        timestamp_epoch INTEGER NOT NULL,
        temperature REAL NOT NULL,
        utilization REAL NOT NULL,
        memory REAL NOT NULL,
        power REAL NOT NULL
    );
    
    CREATE INDEX IF NOT EXISTS idx_gpu_metrics_timestamp_epoch ON gpu_metrics(timestamp_epoch);
    """)
    conn.commit()

def generate_metrics(start_time, end_time, interval):
    """Generate synthetic GPU metrics data with realistic usage patterns"""
    current_time = start_time
    metrics = []
    
    print(f"Generating metrics from {start_time} to {end_time}...")
    print(f"Total time span: {(end_time - start_time).total_seconds() / 3600 / 24:.1f} days")
    
    # Create some patterns for more realistic data
    # Base values that change slightly each day to simulate different use patterns
    daily_temp_base = {}
    daily_util_base = {}
    daily_mem_base = {}
    daily_power_base = {}
    
    # Setup daily variations
    for day_offset in range(4):  # 3 days + 1 for partial days
        day_date = (start_time + timedelta(days=day_offset)).date()
        daily_temp_base[day_date] = random.uniform(30, 50)
        daily_util_base[day_date] = random.uniform(10, 30)
        daily_mem_base[day_date] = random.uniform(1000, 3000)
        daily_power_base[day_date] = random.uniform(30, 100)
    
    # Simulate gaming sessions throughout the week (higher values)
    gaming_sessions = []
    # Weekday evenings and weekend sessions
    for day_offset in range(4):  # 3 days + 1 for partial days
        day = start_time + timedelta(days=day_offset)
        # Weekday (1-2 sessions in evening)
        if day.weekday() < 5:  # Monday-Friday
            # Evening session
            session_start = day.replace(hour=random.randint(18, 20), minute=random.randint(0, 30))
            session_length = timedelta(minutes=random.randint(60, 180))
            if session_start >= start_time and session_start <= end_time:
                gaming_sessions.append((session_start, session_start + session_length))
            
            # Maybe a late night session
            if random.random() > 0.5:
                session_start = day.replace(hour=random.randint(21, 23), minute=random.randint(0, 30))
                session_length = timedelta(minutes=random.randint(30, 120))
                if session_start >= start_time and session_start <= end_time:
                    gaming_sessions.append((session_start, session_start + session_length))
        
        # Weekend (3-4 sessions throughout day)
        else:
            for _ in range(random.randint(3, 4)):
                session_start = day.replace(hour=random.randint(10, 22), minute=random.randint(0, 45))
                session_length = timedelta(minutes=random.randint(45, 240))
                if session_start >= start_time and session_start <= end_time:
                    gaming_sessions.append((session_start, session_start + session_length))
    
    # Add mining sessions (constant high usage for extended periods)
    mining_sessions = []
    for day_offset in range(4):  # 3 days + 1 for partial days
        if random.random() > 0.8:  # 20% chance of mining that day
            day = start_time + timedelta(days=day_offset)
            # Usually overnight
            session_start = day.replace(hour=random.randint(0, 3), minute=random.randint(0, 30))
            session_length = timedelta(hours=random.randint(4, 8))
            if session_start >= start_time and session_start <= end_time:
                mining_sessions.append((session_start, session_start + session_length))
    
    count = 0
    while current_time < end_time:
        # Get the base values for this day
        day_date = current_time.date()
        temp_base = daily_temp_base.get(day_date, 40)
        util_base = daily_util_base.get(day_date, 20)
        mem_base = daily_mem_base.get(day_date, 2000)
        power_base = daily_power_base.get(day_date, 50)
        
        # Check if we're in a gaming or mining session
        in_gaming = any(start <= current_time <= end for start, end in gaming_sessions)
        in_mining = any(start <= current_time <= end for start, end in mining_sessions)
        
        # Generate values based on current activity
        if in_mining:
            # Mining - high steady utilization, high power, high memory
            temp = temp_base + random.uniform(25, 30) + random.uniform(-1, 1)
            util = 95 + random.uniform(-5, 5)
            mem = mem_base + random.uniform(5000, 8000) + random.uniform(-100, 100)
            power = power_base + random.uniform(150, 200) + random.uniform(-5, 5)
        elif in_gaming:
            # Gaming - variable but high
            temp = temp_base + random.uniform(20, 40) + random.uniform(-3, 3)
            util = util_base + random.uniform(50, 90) + random.uniform(-10, 10)
            mem = mem_base + random.uniform(3000, 6000) + random.uniform(-200, 200)
            power = power_base + random.uniform(100, 180) + random.uniform(-15, 15)
        else:
            # Normal desktop use
            # Time of day factors - higher during day, lower at night
            hour = current_time.hour
            if 8 <= hour <= 18:  # Daytime
                activity_factor = random.uniform(0.6, 1.0)
            elif 19 <= hour <= 23:  # Evening
                activity_factor = random.uniform(0.3, 0.7)
            else:  # Night/early morning
                activity_factor = random.uniform(0.1, 0.3)
            
            temp = temp_base + random.uniform(-5, 15) * activity_factor
            util = util_base + random.uniform(-10, 40) * activity_factor
            mem = mem_base + random.uniform(-500, 1500) * activity_factor
            power = power_base + random.uniform(-20, 60) * activity_factor
        
        # Ensure values are within reasonable ranges
        temp = max(20, min(95, temp))
        util = max(0, min(100, util))
        mem = max(500, min(12000, mem))
        power = max(10, min(350, power))
        
        # Add occasional N/A values for power to simulate disconnects/issues
        if random.random() > 0.995:  # 0.5% chance
            power = "N/A"
        
        # Format timestamp like the original script (mm-dd HH:MM:SS)
        timestamp = current_time.strftime("%m-%d %H:%M:%S")
        timestamp_epoch = int(current_time.timestamp())
        
        # Handle power values that might be N/A
        if power == "N/A":
            power = 0
        
        metrics.append((timestamp, timestamp_epoch, temp, util, mem, power))
        
        current_time += timedelta(seconds=interval)
        count += 1
        
        # Show progress
        if count % 10000 == 0:
            progress = (current_time - start_time) / (end_time - start_time) * 100
            print(f"Generated {count} records ({progress:.1f}% complete)")
    
    print(f"Generated {len(metrics)} metrics records")
    return metrics

def populate_database(conn, metrics, batch_size):
    """Insert metrics into the database in batches"""
    print(f"Inserting {len(metrics)} records into database in batches of {batch_size}...")
    
    # First, clear existing data
    print("Clearing existing data from database...")
    conn.execute("DELETE FROM gpu_metrics")
    conn.commit()
    
    start_time = time.time()
    total_records = len(metrics)
    records_inserted = 0
    
    for i in range(0, total_records, batch_size):
        batch = metrics[i:i+batch_size]
        
        conn.execute("BEGIN TRANSACTION")
        conn.executemany(
            "INSERT INTO gpu_metrics (timestamp, timestamp_epoch, temperature, utilization, memory, power) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            batch
        )
        conn.commit()
        
        records_inserted += len(batch)
        elapsed = time.time() - start_time
        records_per_sec = records_inserted / elapsed if elapsed > 0 else 0
        
        progress = records_inserted / total_records * 100
        print(f"Inserted {records_inserted}/{total_records} records ({progress:.1f}% complete, {records_per_sec:.1f} records/sec)")
    
    print(f"Database population complete. {records_inserted} records inserted in {time.time() - start_time:.2f} seconds")

def create_history_json(conn, output_path, history_days=3):
    """Create a history.json file from the database data"""
    print(f"Creating history.json at {output_path} with {history_days} days of data...")
    
    cutoff_time = int((datetime.now() - timedelta(days=history_days, minutes=10)).timestamp())
    
    # Query the database for the specified days + 10 minutes of data
    cur = conn.cursor()
    cur.execute('''
        SELECT timestamp, temperature, utilization, memory, power
        FROM gpu_metrics
        WHERE timestamp_epoch > ?
        ORDER BY timestamp_epoch ASC
    ''', (cutoff_time,))
    
    # Prepare data structure
    result = {
        "timestamps": [],
        "temperatures": [],
        "utilizations": [],
        "memory": [],
        "power": []
    }
    
    # Process each row
    for row in cur.fetchall():
        timestamp, temp, util, mem, power = row
        result["timestamps"].append(timestamp)
        result["temperatures"].append(temp)
        result["utilizations"].append(util)
        result["memory"].append(mem)
        result["power"].append(power)
    
    import json
    # Create the directory if it doesn't exist
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Write the JSON
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=4)
    
    print(f"Created history.json with {len(result['timestamps'])} records")

def main():
    args = parse_args()
    
    # Calculate start and end times for 3 days
    end_time = datetime.now()
    start_time = end_time - timedelta(days=3)
    
    # Connect to database
    db_path = os.path.abspath(args.db_path)
    if not os.path.exists(os.path.dirname(db_path)):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    print(f"Connecting to database at {db_path}")
    conn = sqlite3.connect(db_path)
    
    try:
        # Create schema if needed
        create_db_schema(conn)
        
        # Generate and insert metrics
        metrics = generate_metrics(start_time, end_time, args.interval)
        populate_database(conn, metrics, args.batch_size)
        
        # Create history.json
        history_path = os.path.join(os.path.dirname(db_path), "history.json")
        create_history_json(conn, history_path, history_days=3)
        
        print("\nTest database populated successfully!")
        print(f"Database: {db_path}")
        print(f"History JSON: {history_path}")
        
        # Calculate database size
        db_size_mb = os.path.getsize(db_path) / (1024 * 1024)
        print(f"Database size: {db_size_mb:.2f} MB")
        
        # Calculate JSON size if exists
        if os.path.exists(history_path):
            json_size_mb = os.path.getsize(history_path) / (1024 * 1024)
            print(f"JSON size: {json_size_mb:.2f} MB")
        
        print("\nNow you can run the monitor_gpu.sh script with the 3-day history setting.")
    finally:
        conn.close()

if __name__ == '__main__':
    main() 