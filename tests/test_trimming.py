#!/usr/bin/env python3
"""
GPU Monitor Database Trimming Test

This script tests the trimming operation on an existing database to measure CPU usage
during the trim process. It adds a large number of old records and then performs the
trimming operation, allowing you to observe CPU usage.

Usage:
    python3 test_trimming.py [--db-path PATH]
    
Options:
    --db-path PATH      Path to the SQLite database (default: ../history/gpu_metrics.db)
"""

import argparse
import os
import sqlite3
import sys
import time
import psutil
from datetime import datetime, timedelta

def parse_args():
    parser = argparse.ArgumentParser(description='GPU Monitor Database Trimming Test')
    parser.add_argument('--db-path', default='../history/gpu_metrics.db',
                        help='Path to the SQLite database')
    return parser.parse_args()

def get_db_size(db_path):
    """Get the size of the database file in MB"""
    if not os.path.exists(db_path):
        return 0
    return os.path.getsize(db_path) / (1024 * 1024)

def count_records(conn):
    """Count the number of records in the database"""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM gpu_metrics")
    return cur.fetchone()[0]

def add_old_records(conn, num_records=500000):
    """Add a large number of old records to the database"""
    print(f"Adding {num_records} old records to the database...")
    
    # Create records from 2 days ago to ensure they will be trimmed
    end_time = datetime.now() - timedelta(days=2)
    start_time = end_time - timedelta(days=7)  # A week's worth of old data
    
    # Calculate the interval to spread records over the time period
    interval_seconds = (end_time - start_time).total_seconds() / num_records
    
    current_time = start_time
    records = []
    batch_size = 10000
    
    for i in range(num_records):
        # Generate random-ish values
        temp = 50 + (i % 20)
        util = 30 + (i % 50)
        mem = 2000 + (i % 4000)
        power = 100 + (i % 150)
        
        # Format timestamp
        timestamp = current_time.strftime("%m-%d %H:%M:%S")
        timestamp_epoch = int(current_time.timestamp())
        
        records.append((timestamp, timestamp_epoch, temp, util, mem, power))
        current_time += timedelta(seconds=interval_seconds)
        
        # Insert in batches
        if len(records) >= batch_size or i == num_records - 1:
            conn.execute("BEGIN TRANSACTION")
            conn.executemany(
                "INSERT INTO gpu_metrics (timestamp, timestamp_epoch, temperature, utilization, memory, power) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                records
            )
            conn.commit()
            
            # Show progress
            progress = (i + 1) / num_records * 100
            print(f"Inserted {i + 1}/{num_records} old records ({progress:.1f}% complete)")
            records = []
    
    print(f"Added {num_records} old records successfully")

def perform_trim_operation(conn):
    """Perform the trim operation and measure CPU usage"""
    print("\nPerforming trim operation...")
    
    # Get current process
    process = psutil.Process(os.getpid())
    
    # Cutoff time (24 hours + 10 minutes ago, matching the original script)
    cutoff_time = int((datetime.now() - timedelta(hours=24, minutes=10)).timestamp())
    
    # Count records before trim
    before_count = count_records(conn)
    
    # Measure time and CPU
    start_time = time.time()
    start_cpu = process.cpu_percent()
    
    # Trim operation (similar to the clean_old_data function in the main script)
    print(f"Deleting records older than {datetime.fromtimestamp(cutoff_time)}")
    conn.execute(f"DELETE FROM gpu_metrics WHERE timestamp_epoch < {cutoff_time}")
    conn.commit()
    
    # Vacuum to reclaim space and optimize
    print("Running VACUUM operation...")
    conn.execute("VACUUM")
    conn.commit()
    
    # Measure results
    elapsed = time.time() - start_time
    cpu_percent = process.cpu_percent()
    after_count = count_records(conn)
    deleted_count = before_count - after_count
    
    print("\nTrim operation complete!")
    print(f"Time taken: {elapsed:.2f} seconds")
    print(f"CPU usage: {cpu_percent:.1f}%")
    print(f"Records before: {before_count}")
    print(f"Records after: {after_count}")
    print(f"Records deleted: {deleted_count}")

def main():
    args = parse_args()
    db_path = os.path.abspath(args.db_path)
    
    if not os.path.exists(db_path):
        print(f"Error: Database file not found at {db_path}")
        print("Run db_load_test.py first to populate the database")
        return 1
    
    print(f"Testing trimming operation on database: {db_path}")
    print(f"Initial database size: {get_db_size(db_path):.2f} MB")
    
    conn = sqlite3.connect(db_path)
    
    try:
        # Count existing records
        initial_count = count_records(conn)
        print(f"Initial record count: {initial_count}")
        
        # Add a large number of old records to simulate a full database
        add_old_records(conn)
        
        # Count after adding old records
        middle_count = count_records(conn)
        print(f"Record count after adding old data: {middle_count}")
        print(f"Database size before trim: {get_db_size(db_path):.2f} MB")
        
        # Perform and measure the trim operation
        perform_trim_operation(conn)
        
        # Final size
        print(f"Final database size: {get_db_size(db_path):.2f} MB")
        
    finally:
        conn.close()
    
    print("\nTest complete!")
    print("Note: This test simulates the database trimming operation that occurs")
    print("periodically in the monitor_gpu.sh script. The CPU usage during the")
    print("VACUUM operation is particularly relevant to your original issue.")
    
    return 0

if __name__ == '__main__':
    sys.exit(main()) 