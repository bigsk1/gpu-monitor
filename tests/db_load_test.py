#!/usr/bin/env python3
"""
GPU Monitor Database Load Test

This script generates synthetic GPU metrics data and populates the SQLite
database to test CPU usage during database trimming operations.

Usage:
    python3 db_load_test.py [--db-path PATH] [--hours HOURS] [--interval SECONDS]
    
Options:
    --db-path PATH      Path to the SQLite database (default: ../history/gpu_metrics.db)
    --hours HOURS       Hours of data to generate (default: 30)
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
    parser = argparse.ArgumentParser(description='GPU Monitor Database Load Test')
    parser.add_argument('--db-path', default='../history/gpu_metrics.db',
                        help='Path to the SQLite database')
    parser.add_argument('--hours', type=float, default=30,
                        help='Hours of data to generate')
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
    """Generate synthetic GPU metrics data"""
    current_time = start_time
    metrics = []
    
    print(f"Generating metrics from {start_time} to {end_time}...")
    print(f"Total time span: {(end_time - start_time).total_seconds() / 3600:.2f} hours")
    
    # Create some patterns for more realistic data
    temp_base = random.uniform(30, 50)
    util_base = random.uniform(10, 30)
    mem_base = random.uniform(1000, 3000)
    power_base = random.uniform(30, 100)
    
    # Simulate some "gaming sessions" with higher values
    gaming_sessions = []
    current_session = start_time
    while current_session < end_time:
        session_length = timedelta(minutes=random.randint(30, 180))
        gaming_sessions.append((current_session, current_session + session_length))
        current_session += session_length + timedelta(minutes=random.randint(60, 300))
    
    count = 0
    while current_time < end_time:
        # Check if we're in a gaming session
        in_gaming = any(start <= current_time <= end for start, end in gaming_sessions)
        
        # Generate values with some randomness and patterns
        if in_gaming:
            temp = temp_base + random.uniform(20, 40) + random.uniform(-2, 2)
            util = util_base + random.uniform(50, 90) + random.uniform(-5, 5)
            mem = mem_base + random.uniform(3000, 8000) + random.uniform(-100, 100)
            power = power_base + random.uniform(100, 200) + random.uniform(-10, 10)
        else:
            temp = temp_base + random.uniform(-5, 5)
            util = util_base + random.uniform(-10, 20)
            mem = mem_base + random.uniform(-500, 500)
            power = power_base + random.uniform(-10, 20)
        
        # Ensure values are within reasonable ranges
        temp = max(20, min(95, temp))
        util = max(0, min(100, util))
        mem = max(500, min(12000, mem))
        power = max(10, min(350, power))
        
        # Format timestamp like the original script (mm-dd HH:MM:SS)
        timestamp = current_time.strftime("%m-%d %H:%M:%S")
        timestamp_epoch = int(current_time.timestamp())
        
        metrics.append((timestamp, timestamp_epoch, temp, util, mem, power))
        
        current_time += timedelta(seconds=interval)
        count += 1
        
        # Show progress
        if count % 5000 == 0:
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

def create_history_json(conn, output_path):
    """Create a history.json file from the database data"""
    print(f"Creating history.json at {output_path}...")
    
    cutoff_time = int((datetime.now() - timedelta(hours=24, minutes=10)).timestamp())
    
    # Query the database for the last 24 hours + 10 minutes of data
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
    
    # Calculate start and end times
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=args.hours)
    
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
        create_history_json(conn, history_path)
        
        print("\nTest database populated successfully!")
        print(f"Database: {db_path}")
        print(f"History JSON: {history_path}")
        print("\nNow you can run the monitor_gpu.sh script and observe CPU usage during trimming operations.")
    finally:
        conn.close()

if __name__ == '__main__':
    main() 