#!/usr/bin/env python3

"""
GPU Monitor Installation Script
------------------------------
This script provides a non-Docker installation method for the GPU Monitor application.
It handles installation, configuration, and service management.

Usage:
    sudo python3 no_docker.py --start    # Install and start the service
    sudo python3 no_docker.py --stop     # Stop the service
    sudo python3 no_docker.py --status   # Check service status
    sudo python3 no_docker.py --uninstall # Remove the service and clean up

Requirements:
    - Python 3.8 or higher
    - Root privileges
    - NVIDIA GPU with drivers installed
    - Debian-based Linux distribution (Ubuntu/Debian)
"""

import os
import sys
import argparse
import subprocess
import venv
import shutil
import pwd
import grp
import textwrap
from pathlib import Path
import logging
import time
from datetime import datetime
import json
from typing import Dict, List, Optional, Tuple

class GPUMonitorInstaller:
    """
    Handles the installation and management of GPU Monitor without Docker.
    
    This class manages:
    - System dependencies
    - Directory structure
    - Virtual environment
    - Service configuration
    - Process management
    """

    def __init__(self):
        """Initialize installer with paths and configuration."""
        self.current_dir = Path.cwd()
        self.user = os.getenv('SUDO_USER', os.getenv('USER'))
        self.user_home = str(Path.home())
        self.app_dir = Path('/opt/gpu-monitor')
        self.venv_dir = self.app_dir / 'venv'
        self.log_dir = self.app_dir / 'logs'
        self.history_dir = self.app_dir / 'history'
        self.systemd_service_path = Path('/etc/systemd/system/gpu-monitor.service')
        self.nvidia_smi_path = None
        
        # Required system commands
        self.required_commands = [
            'tr', 'cut', 'chmod', 'wc', 'date', 'sleep',
            'systemctl'
        ]
        
        # Required system packages
        self.required_packages = [
            'coreutils',   # Basic command line utilities
            'util-linux',  # System utilities
            'procps',      # Process utilities
            'python3-venv' # Python virtual environment
        ]

        # Setup logging
        self.setup_logging()
        
        # Verify running as root
        if os.geteuid() != 0:
            self.logger.error("This script must be run with root privileges (sudo)")
            sys.exit(1)

    def setup_logging(self) -> None:
        """
        Configure logging with both file and console output.
        
        Creates:
        - Console handler with INFO level
        - File handler with DEBUG level
        - Timestamp-based log files
        """
        # Create logs directory if it doesn't exist
        os.makedirs('/var/log/gpu-monitor', exist_ok=True)
        
        # Setup basic logging format
        log_format = '%(asctime)s - %(levelname)s - %(message)s'
        
        # Configure root logger
        logging.basicConfig(
            level=logging.INFO,
            format=log_format
        )
        
        self.logger = logging.getLogger('gpu-monitor-installer')
        self.logger.setLevel(logging.DEBUG)

        # Add file handler
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = f'/var/log/gpu-monitor/install_{timestamp}.log'
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(log_format))
        
        self.logger.addHandler(file_handler)
        self.logger.info(f"Logging initialized. Install log: {log_file}")

    def detect_environment(self) -> str:
        """
        Detect the current operating environment.
        
        Returns:
            str: Environment type ('wsl', 'ubuntu', 'debian', or 'unknown')
        """
        try:
            # Check for WSL
            with open('/proc/version', 'r') as f:
                version_info = f.read().lower()
                if 'microsoft' in version_info or 'wsl' in version_info:
                    return 'wsl'
            
            # Check for Ubuntu/Debian
            if os.path.exists('/etc/debian_version'):
                with open('/etc/os-release', 'r') as f:
                    os_info = f.read().lower()
                    if 'ubuntu' in os_info:
                        return 'ubuntu'
                    return 'debian'
            
            return 'unknown'
        except Exception as e:
            self.logger.error(f"Error detecting environment: {e}")
            return 'unknown'

    def check_nvidia_paths(self) -> Optional[str]:
        """
        Find the NVIDIA SMI executable path based on environment.
        
        Returns:
            Optional[str]: Path to nvidia-smi if found, None otherwise
        """
        env_type = self.detect_environment()
        self.logger.info(f"Checking NVIDIA paths for environment: {env_type}")
        
        # Define possible nvidia-smi paths
        nvidia_smi_paths = [
            '/usr/bin/nvidia-smi',
            '/usr/local/bin/nvidia-smi',
            '/opt/nvidia/bin/nvidia-smi'
        ]

        # Add WSL-specific paths
        if env_type == 'wsl':
            nvidia_smi_paths.extend([
                '/usr/lib/wsl/lib/nvidia-smi',
                '/usr/lib/wsl/nvidia-smi'
            ])

        # Check each path
        for path in nvidia_smi_paths:
            if os.path.exists(path):
                try:
                    result = subprocess.run(
                        [path], 
                        capture_output=True, 
                        text=True
                    )
                    if result.returncode == 0:
                        self.logger.info(f"Found working nvidia-smi at: {path}")
                        return path
                except Exception as e:
                    self.logger.debug(f"Error checking {path}: {e}")
                    continue

        self.logger.error("No working nvidia-smi found in standard locations")
        return None


    def check_prerequisites(self) -> bool:
        self.ensure_path()  # Ensure PATH is correct
        missing_commands = []
        for cmd in self.required_commands:
            result = subprocess.run(['which', cmd], capture_output=True, text=True)
            if result.returncode != 0:
                missing_commands.append(cmd)
        
        if missing_commands:
            self.logger.error(f"Missing commands: {', '.join(missing_commands)}")
            return False
        """
        Verify all system prerequisites are met.
        
        Checks:
        - Python version
        - Root privileges
        - System commands
        - NVIDIA drivers
        - Systemd availability
        
        Returns:
            bool: True if all prerequisites are met, False otherwise
        """
        try:
            self.logger.info("Checking prerequisites...")
            
            # Check Python version
            if sys.version_info < (3, 8):
                self.logger.error("Python 3.8 or higher is required")
                return False

            # Check systemd
            if not os.path.exists('/run/systemd/system'):
                self.logger.error("Systemd is required but not found")
                return False

            # Test nvidia-smi directly first
            try:
                result = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
                if result.returncode == 0:
                    self.nvidia_smi_path = 'nvidia-smi'
                    self.logger.info("nvidia-smi is available in PATH")
                    return True
            except FileNotFoundError:
                pass

            # If direct command failed, check specific paths
            nvidia_smi = self.check_nvidia_paths()
            if not nvidia_smi:
                self.logger.error("nvidia-smi not found. Please ensure NVIDIA drivers are installed and nvidia-smi is available")
                return False
            
            self.nvidia_smi_path = nvidia_smi
            return True

        except Exception as e:
            self.logger.error(f"Error checking prerequisites: {e}")
            return False

    def check_and_install_dependencies(self) -> bool:
        """
        Check for and install required system packages.
        
        Returns:
            bool: True if all dependencies are installed successfully
        """
        try:
            self.logger.info("Checking system dependencies...")
            
            # Verify we're on a Debian-based system
            if not os.path.exists('/usr/bin/apt-get'):
                self.logger.error("This script requires apt package manager")
                return False

            # Update package list
            self.logger.info("Updating package list...")
            subprocess.run(['apt-get', 'update'], check=True)
            
            # Install required packages
            self.logger.info("Installing required packages...")
            install_cmd = ['apt-get', 'install', '-y'] + self.required_packages.extend(['coreutils', 'util-linux', 'procps', 'build-essential'])

            process = subprocess.run(
                install_cmd,
                capture_output=True,
                text=True
            )
            
            if process.returncode != 0:
                self.logger.error(f"Package installation failed: {process.stderr}")
                return False

            # Verify commands are available
            missing_commands = []
            for cmd in self.required_commands:
                try:
                    subprocess.run(['which', cmd], check=True, capture_output=True)
                except subprocess.CalledProcessError:
                    missing_commands.append(cmd)
            
            if missing_commands:
                self.logger.error(f"Missing commands after install: {', '.join(missing_commands)}")
                return False

            self.logger.info("All dependencies installed successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error installing dependencies: {e}")
            return False

    def setup_directories(self) -> bool:
        """
        Create and configure required directories with proper permissions.
        
        Creates:
        - Application directory
        - Log directory
        - History directory
        - Ensures proper ownership and permissions
        
        Returns:
            bool: True if setup successful
        """
        try:
            self.logger.info("Setting up directories...")
            
            # Track existing directories
            existing_dirs = {
                'images': (self.current_dir / 'images').exists(),
                'sounds': (self.current_dir / 'sounds').exists(),
                'history': (self.current_dir / 'history').exists(),
                'logs': (self.current_dir / 'logs').exists()
            }
            
            self.logger.info(f"Found existing directories: {existing_dirs}")

            # Create required directories
            for directory in [self.app_dir, self.log_dir, self.history_dir]:
                if not directory.exists():
                    self.logger.info(f"Creating directory: {directory}")
                    directory.mkdir(parents=True, exist_ok=True)
                else:
                    self.logger.info(f"Directory exists: {directory}")

            # Set ownership
            uid = pwd.getpwnam(self.user).pw_uid
            gid = grp.getgrnam(self.user).gr_gid
            
            self.logger.info(f"Setting ownership to {self.user} ({uid}:{gid})")
            
            for directory in [self.app_dir, self.log_dir, self.history_dir]:
                os.chown(directory, uid, gid)
                for root, dirs, files in os.walk(directory):
                    for d in dirs:
                        os.chown(os.path.join(root, d), uid, gid)
                    for f in files:
                        os.chown(os.path.join(root, f), uid, gid)

            return True

        except Exception as e:
            self.logger.error(f"Error setting up directories: {e}")
            return False

    def setup_virtual_environment(self) -> bool:
        """
        Create and configure Python virtual environment.
        
        - Creates venv if it doesn't exist
        - Upgrades pip
        - Installs required Python packages
        
        Returns:
            bool: True if setup successful
        """
        try:
            self.logger.info(f"Setting up virtual environment in {self.venv_dir}")
            
            # Create virtual environment
            if not self.venv_dir.exists():
                venv.create(self.venv_dir, with_pip=True)
                self.logger.info("Virtual environment created")
            
            # Get pip path
            pip_path = self.venv_dir / 'bin' / 'pip'
            
            # Upgrade pip
            self.logger.info("Upgrading pip...")
            subprocess.run([str(pip_path), 'install', '--upgrade', 'pip'], check=True)
            
            # Install required packages
            self.logger.info("Installing required Python packages...")
            subprocess.run([str(pip_path), 'install', 'aiohttp'], check=True)
            
            self.logger.info("Virtual environment setup complete")
            return True

        except Exception as e:
            self.logger.error(f"Error setting up virtual environment: {e}")
            return False

    def modify_monitor_script(self) -> bool:
        """
        Modify monitor_gpu.sh script with correct paths and settings.
        
        - Updates nvidia-smi path
        - Updates base directory
        - Sets correct permissions
        
        Returns:
            bool: True if modification successful
        """
        try:
            script_path = self.app_dir / 'monitor_gpu.sh'
            if script_path.exists() and self.nvidia_smi_path:
                with open(script_path, 'r') as f:
                    content = f.read()
                
                # Update paths
                modified_content = content.replace(
                    'nvidia-smi',
                    self.nvidia_smi_path
                ).replace(
                    'BASE_DIR="/app"',
                    f'BASE_DIR="{self.app_dir}"'
                )
                
                # Write modified script
                with open(script_path, 'w') as f:
                    f.write(modified_content)
                
                # Set permissions
                os.chmod(script_path, 0o755)
                
                self.logger.info("Monitor script modified successfully")
                return True

            self.logger.error("Monitor script or nvidia-smi path not found")
            return False

        except Exception as e:
            self.logger.error(f"Error modifying monitor script: {e}")
            return False
        

    def create_systemd_service(self) -> bool:
        """
        Create and configure systemd service file.
        
        Creates a systemd service that:
        - Runs as the correct user
        - Uses virtual environment
        - Has proper PATH settings
        - Includes logging configuration
        
        Returns:
            bool: True if service creation successful
        """
        service_content = f"""[Unit]
Description=GPU Monitor Service
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
User={self.user}
ExecStart=/bin/bash {self.app_dir}/monitor_gpu.sh
WorkingDirectory={self.app_dir}
Restart=always
RestartSec=1
Environment=PYTHONUNBUFFERED=1
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
Environment=VIRTUAL_ENV={self.venv_dir}
Environment=PATH={self.venv_dir}/bin:$PATH

StandardOutput=append:/var/log/gpu-monitor/service.log
StandardError=append:/var/log/gpu-monitor/error.log

[Install]
WantedBy=multi-user.target
"""
        try:
            self.logger.info("Creating systemd service...")
            
            # Write service file
            with open(self.systemd_service_path, 'w') as f:
                f.write(service_content)
            
            # Reload systemd and enable service
            subprocess.run(['systemctl', 'daemon-reload'], check=True)
            subprocess.run(['systemctl', 'enable', 'gpu-monitor'], check=True)
            
            self.logger.info("Systemd service created and enabled")
            return True

        except Exception as e:
            self.logger.error(f"Error creating systemd service: {e}")
            return False

    def copy_application_files(self) -> bool:
        """
        Copy all required application files to installation directory.
        
        Returns:
            bool: True if copy successful
        """
        try:
            self.logger.info("Copying application files...")
            
            # Copy required files
            files_to_copy = ['server.py', 'monitor_gpu.sh', 'gpu-stats.html']
            for file in files_to_copy:
                src = self.current_dir / file
                dst = self.app_dir / file
                if src.exists():
                    shutil.copy2(src, dst)
                    self.logger.info(f"Copied {file}")
                else:
                    self.logger.error(f"Required file not found: {file}")
                    return False

            # Copy directories
            dirs_to_copy = ['images', 'sounds']
            for dir_name in dirs_to_copy:
                src = self.current_dir / dir_name
                dst = self.app_dir / dir_name
                if src.exists():
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                    self.logger.info(f"Copied directory {dir_name}")

            # Set permissions
            for root, dirs, files in os.walk(self.app_dir):
                for d in dirs:
                    os.chmod(os.path.join(root, d), 0o755)
                for f in files:
                    os.chmod(os.path.join(root, f), 0o644)

            # Make script executable
            monitor_script = self.app_dir / 'monitor_gpu.sh'
            os.chmod(monitor_script, 0o755)

            return True

        except Exception as e:
            self.logger.error(f"Error copying application files: {e}")
            return False

    def check_service_status(self) -> bool:
        """Check if service is running and collecting data."""
        try:
            self.logger.info("Checking service status...")
            
            # Check systemd service status
            status_result = subprocess.run(
                ['systemctl', 'status', 'gpu-monitor.service'],
                capture_output=True,
                text=True
            )
            
            if 'active (running)' not in status_result.stdout:
                self.logger.error("Service is not running")
                return False

            # Check data collection with shorter timeout
            self.logger.info("Checking data collection...")
            for _ in range(6):  # Wait up to 30 seconds (5 seconds * 6)
                if (self.app_dir / 'gpu_current_stats.json').exists():
                    try:
                        with open(self.app_dir / 'gpu_current_stats.json') as f:
                            json.load(f)  # Verify valid JSON
                            self.logger.info("Data collection verified")
                            return True
                    except (json.JSONDecodeError, FileNotFoundError):
                        pass
                time.sleep(5)
            
            # If we get here, show current directory contents for debugging
            try:
                self.logger.info(f"Contents of {self.app_dir}:")
                self.logger.info(str(list(self.app_dir.glob('*'))))
            except Exception as e:
                self.logger.error(f"Error listing directory: {e}")

            self.logger.error("Data collection not verified")
            return False

        except Exception as e:
            self.logger.error(f"Error checking service status: {e}")
            return False

    def start_service(self) -> bool:
        """Start the GPU Monitor service and verify it's running."""
        try:
            self.logger.info("Starting GPU Monitor service...")
            
            script_path = self.app_dir / 'monitor_gpu.sh'
            if not script_path.exists():
                self.logger.error(f"Monitor script not found at {script_path}")
                return False

            # Run the script in its directory
            subprocess.run(
                [str(script_path)],
                cwd=str(self.app_dir),
                env={"PATH": os.environ.get('PATH', '')},
                check=True
            )
            self.logger.info("GPU Monitor started successfully.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to start GPU Monitor: {e}")
            return False
        
        # if:
        #     # If service failed, get detailed logs
        #     self.logger.error("Service failed to start properly")
            
        #     # Get systemd journal logs
        #     logs = subprocess.run(
        #         ['journalctl', '-u', 'gpu-monitor', '--no-pager', '-n', '50'],
        #         capture_output=True,
        #         text=True
        #     )
        #     self.logger.error(f"Service logs:\n{logs.stdout}")
            
        #     # Try to get any Python errors
        #     if os.path.exists('/var/log/gpu-monitor/error.log'):
        #         with open('/var/log/gpu-monitor/error.log', 'r') as f:
        #             self.logger.error(f"Error log contents:\n{f.read()}")
            
        #     return False

        except Exception as e:
            self.logger.error(f"Error starting service: {e}")
            self.logger.exception("Full exception:")
            return False

    def stop_service(self) -> bool:
        """Stop the GPU Monitor service."""
        try:
            subprocess.run(['systemctl', 'stop', 'gpu-monitor'], check=True)
            self.logger.info("GPU Monitor service stopped successfully")
            return True
        except Exception as e:
            self.logger.error(f"Error stopping service: {e}")
            return False

    def cleanup(self) -> bool:
        """
        Clean up installation files and service.
        
        Returns:
            bool: True if cleanup successful
        """
        try:
            if self.systemd_service_path.exists():
                self.logger.info("Stopping and removing service...")
                subprocess.run(['systemctl', 'stop', 'gpu-monitor'], check=True)
                subprocess.run(['systemctl', 'disable', 'gpu-monitor'], check=True)
                self.systemd_service_path.unlink()
                subprocess.run(['systemctl', 'daemon-reload'], check=True)

            if self.app_dir.exists():
                self.logger.info("Removing application files...")
                shutil.rmtree(self.app_dir)

            # Clean up log files
            log_files = [
                '/var/log/gpu-monitor/service.log',
                '/var/log/gpu-monitor/error.log'
            ]
            for log_file in log_files:
                if os.path.exists(log_file):
                    os.remove(log_file)

            self.logger.info("Cleanup completed successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
            return False


def main():
    """Main entry point for the installer."""
    parser = argparse.ArgumentParser(
        description='GPU Monitor Installation Script',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent('''
            Examples:
              sudo python3 no_docker.py --start     # Install and start service
              sudo python3 no_docker.py --stop      # Stop service
              sudo python3 no_docker.py --status    # Check service status
              sudo python3 no_docker.py --uninstall # Remove service
        ''')
    )
    
    parser.add_argument('--start', action='store_true', help='Install and start GPU Monitor')
    parser.add_argument('--stop', action='store_true', help='Stop GPU Monitor')
    parser.add_argument('--status', action='store_true', help='Check GPU Monitor status')
    parser.add_argument('--uninstall', action='store_true', help='Uninstall GPU Monitor')
    parser.add_argument('--skip-path-fix', action='store_true', help='Skip PATH updates')
    args = parser.parse_args()

    installer = GPUMonitorInstaller()

    if args.start:
        print("Starting GPU Monitor installation...")
        if installer.check_prerequisites() and \
           installer.check_and_install_dependencies() and \
           installer.setup_directories() and \
           installer.setup_virtual_environment() and \
           installer.copy_application_files() and \
           installer.modify_monitor_script() and \
           installer.create_systemd_service() and \
           installer.start_service():
            print("\nGPU Monitor installed and started successfully!")
            print("\nDashboard: http://localhost:8081")
            print("Status: sudo systemctl status gpu-monitor")
            print("Logs: sudo journalctl -u gpu-monitor -f")
            print("\nInstallation logs can be found in /var/log/gpu-monitor/")
        else:
            print("\nInstallation failed. Check logs for details.")
            sys.exit(1)
    elif args.stop:
        installer.stop_service()
    elif args.uninstall:
        installer.cleanup()
    elif args.status:
        installer.check_service_status()
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()