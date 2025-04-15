#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[+]${NC} $1"
}

print_error() {
    echo -e "${RED}[!]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[*]${NC} $1"
}

check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check for docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker not found. Please install Docker first."
        print_warning "Visit: https://docs.docker.com/engine/install/"
        return 1
    fi
    print_status "Docker: Found"

    # Check for docker-compose
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose not found. Please install Docker Compose first."
        print_warning "Visit: https://docs.docker.com/compose/install/"
        return 1
    fi
    print_status "Docker Compose: Found"

    # Check for nvidia-docker
    if ! docker info 2>/dev/null | grep -q "Runtimes.*nvidia"; then
        print_error "NVIDIA Docker runtime not found. Please install nvidia-docker2."
        print_warning "Visit: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
        return 1
    fi
    print_status "NVIDIA Docker Runtime: Found"

    # Check for NVIDIA GPU
    if ! command -v nvidia-smi &> /dev/null; then
        print_error "NVIDIA GPU driver not found."
        print_warning "Please install NVIDIA drivers first."
        return 1
    fi
    print_status "NVIDIA GPU: Found"
    
    # Check for SQLite3 (only for local development, container has it installed)
    if ! command -v sqlite3 &> /dev/null; then
        print_warning "SQLite3 not found on the local system."
        print_warning "This is only needed for local development, the container includes SQLite3."
    else
        print_status "SQLite3: Found"
    fi

    return 0
}

start_service() {
    print_status "Starting GPU Monitor..."
    docker-compose up -d
    
    if [ $? -eq 0 ]; then
        print_status "GPU Monitor started successfully!"
        print_status "Dashboard available at: http://localhost:8081"
        print_status "To check logs: docker-compose logs -f"
    else
        print_error "Failed to start GPU Monitor."
        print_warning "Check logs with: docker-compose logs"
        return 1
    fi
}

stop_service() {
    print_status "Stopping GPU Monitor..."
    docker-compose down
}

restart_service() {
    print_status "Restarting GPU Monitor..."
    docker-compose restart
}

show_status() {
    docker-compose ps
}

show_logs() {
    docker-compose logs -f
}

case "$1" in
    start)
        check_prerequisites && start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        restart_service
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        echo
        echo "Commands:"
        echo "  start    - Check prerequisites and start the service"
        echo "  stop     - Stop the service"
        echo "  restart  - Restart the service"
        echo "  status   - Show service status"
        echo "  logs     - Show service logs"
        exit 1
        ;;
esac