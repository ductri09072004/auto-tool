from flask import Flask, jsonify
from data.mock_data import get_system_info, get_user_profile, get_health_status, get_products_data, get_orders_data
import time
import random
import psutil
import os
import platform

app = Flask(__name__)

# Metrics variables
request_count = 0
response_times = []

@app.route('/api/base')
def hello():
    """API endpoint trả về thông tin hệ thống"""
    global request_count, response_times  # noqa: F824
    start_time = time.time()
    request_count += 1
    result = jsonify(get_system_info())
    response_times.append(time.time() - start_time)
    # Keep only last 100 response times to prevent memory leak
    if len(response_times) > 100:
        response_times.pop(0)
    return result

@app.route('/api/user')
def api_hello():
    """API endpoint trả về thông tin người dùng"""
    global request_count, response_times  # noqa: F824
    start_time = time.time()
    request_count += 1
    result = jsonify(get_user_profile())
    response_times.append(time.time() - start_time)
    # Keep only last 100 response times to prevent memory leak
    if len(response_times) > 100:
        response_times.pop(0)
    return result

@app.route('/api/health')
def health_check():
    """API endpoint kiểm tra trạng thái server với dữ liệu thật"""
    global request_count, response_times  # noqa: F824
    start_time = time.time()
    request_count += 1
    
    # Thu thập thông tin hệ thống thực tế
    try:
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_used_gb = memory.used / (1024**3)
        memory_total_gb = memory.total / (1024**3)
        
        # Disk usage
        disk = psutil.disk_usage('/')
        disk_percent = (disk.used / disk.total) * 100
        disk_used_gb = disk.used / (1024**3)
        disk_total_gb = disk.total / (1024**3)
        
        # Network I/O
        network = psutil.net_io_counters()
        
        # System info
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time
        uptime_hours = uptime_seconds / 3600
        
        # Process info
        process = psutil.Process(os.getpid())
        process_memory_mb = process.memory_info().rss / (1024**2)
        process_cpu_percent = process.cpu_percent()
        
        # Load average (Linux/Mac only)
        try:
            load_avg = os.getloadavg()
            load_1min, load_5min, load_15min = load_avg
        except AttributeError:
            # Windows doesn't support loadavg
            load_1min = load_5min = load_15min = 0
        
        real_health_data = {
            "status": "healthy",
            "timestamp": time.time(),
            "service_name": "{SERVICE_NAME}",
            "namespace": "{NAMESPACE}",
            "version": "1.0.0",
            "system": {
                "platform": platform.system(),
                "platform_version": platform.version(),
                "architecture": platform.architecture()[0],
                "hostname": platform.node(),
                "python_version": platform.python_version(),
                "uptime_hours": round(uptime_hours, 2)
            },
            "resources": {
                "cpu": {
                    "usage_percent": round(cpu_percent, 2),
                    "count": psutil.cpu_count(),
                    "process_cpu_percent": round(process_cpu_percent, 2)
                },
                "memory": {
                    "usage_percent": round(memory_percent, 2),
                    "used_gb": round(memory_used_gb, 2),
                    "total_gb": round(memory_total_gb, 2),
                    "process_memory_mb": round(process_memory_mb, 2)
                },
                "disk": {
                    "usage_percent": round(disk_percent, 2),
                    "used_gb": round(disk_used_gb, 2),
                    "total_gb": round(disk_total_gb, 2)
                },
                "network": {
                    "bytes_sent": network.bytes_sent,
                    "bytes_recv": network.bytes_recv,
                    "packets_sent": network.packets_sent,
                    "packets_recv": network.packets_recv
                }
            },
            "load_average": {
                "1min": round(load_1min, 2),
                "5min": round(load_5min, 2),
                "15min": round(load_15min, 2)
            },
            "response_time_ms": round((time.time() - start_time) * 1000, 2)
        }
        
        result = jsonify(real_health_data)
        
    except Exception as e:
        # Fallback to mock data if real data collection fails
        error_data = {
            "status": "error",
            "message": f"Failed to collect real system data: {str(e)}",
            "timestamp": time.time(),
            "service_name": "{SERVICE_NAME}",
            "fallback_data": get_health_status()
        }
        result = jsonify(error_data)
    
    response_times.append(time.time() - start_time)
    # Keep only last 100 response times to prevent memory leak
    if len(response_times) > 100:
        response_times.pop(0)
    return result

@app.route('/api/products')
def get_products():
    """API endpoint trả về danh sách sản phẩm"""
    global request_count, response_times  # noqa: F824
    start_time = time.time()
    request_count += 1
    result = jsonify(get_products_data())
    response_times.append(time.time() - start_time)
    # Keep only last 100 response times to prevent memory leak
    if len(response_times) > 100:
        response_times.pop(0)
    return result

@app.route('/api/orders')
def get_orders():
    """API endpoint trả về danh sách đơn hàng"""
    global request_count, response_times  # noqa: F824
    start_time = time.time()
    request_count += 1
    result = jsonify(get_orders_data())
    response_times.append(time.time() - start_time)
    # Keep only last 100 response times to prevent memory leak
    if len(response_times) > 100:
        response_times.pop(0)
    return result

@app.route('/api/name')
def get_service_name():
    """API endpoint trả về tên service"""
    global request_count, response_times  # noqa: F824
    start_time = time.time()
    request_count += 1
    result = jsonify({
        "service_name": "{SERVICE_NAME}",
        "namespace": "{NAMESPACE}",
        "version": "1.0.0",
        "timestamp": time.time()
    })
    response_times.append(time.time() - start_time)
    # Keep only last 100 response times to prevent memory leak
    if len(response_times) > 100:
        response_times.pop(0)
    return result

@app.route('/metrics')
def metrics():
    """Prometheus metrics endpoint với dữ liệu thực tế"""
    global request_count, response_times  # noqa: F824
    
    # Calculate real metrics
    avg_response_time = sum(response_times[-10:]) / len(response_times[-10:]) if response_times else 0
    
    try:
        # Real system metrics
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_used_bytes = memory.used
        memory_total_bytes = memory.total
        
        # Process metrics
        process = psutil.Process(os.getpid())
        process_memory_bytes = process.memory_info().rss
        process_cpu_percent = process.cpu_percent()
        
        # Network metrics
        network = psutil.net_io_counters()
        
        # Load average (Linux/Mac only)
        try:
            load_avg = os.getloadavg()
            load_1min, _, _ = load_avg
        except AttributeError:
            load_1min = 0
        
        # Active connections (approximate from network stats)
        active_connections = network.connections if hasattr(network, 'connections') else 0
        
        metrics_text = """# HELP {SERVICE_NAME}_requests_total Total number of requests
# TYPE {SERVICE_NAME}_requests_total counter
{SERVICE_NAME}_requests_total {request_count}

# HELP {SERVICE_NAME}_response_time_seconds Average response time
# TYPE {SERVICE_NAME}_response_time_seconds gauge
{SERVICE_NAME}_response_time_seconds {avg_response_time:.3f}

# HELP {SERVICE_NAME}_cpu_usage_percent CPU usage percentage
# TYPE {SERVICE_NAME}_cpu_usage_percent gauge
{SERVICE_NAME}_cpu_usage_percent {cpu_percent:.2f}

# HELP {SERVICE_NAME}_memory_usage_percent Memory usage percentage
# TYPE {SERVICE_NAME}_memory_usage_percent gauge
{SERVICE_NAME}_memory_usage_percent {memory_percent:.2f}

# HELP {SERVICE_NAME}_memory_usage_bytes Memory usage in bytes
# TYPE {SERVICE_NAME}_memory_usage_bytes gauge
{SERVICE_NAME}_memory_usage_bytes {memory_used_bytes}

# HELP {SERVICE_NAME}_process_memory_bytes Process memory usage in bytes
# TYPE {SERVICE_NAME}_process_memory_bytes gauge
{SERVICE_NAME}_process_memory_bytes {process_memory_bytes}

# HELP {SERVICE_NAME}_process_cpu_percent Process CPU usage percentage
# TYPE {SERVICE_NAME}_process_cpu_percent gauge
{SERVICE_NAME}_process_cpu_percent {process_cpu_percent:.2f}

# HELP {SERVICE_NAME}_network_bytes_sent Network bytes sent
# TYPE {SERVICE_NAME}_network_bytes_sent counter
{SERVICE_NAME}_network_bytes_sent {network_bytes_sent}

# HELP {SERVICE_NAME}_network_bytes_recv Network bytes received
# TYPE {SERVICE_NAME}_network_bytes_recv counter
{SERVICE_NAME}_network_bytes_recv {network_bytes_recv}

# HELP {SERVICE_NAME}_load_average_1min System load average (1 minute)
# TYPE {SERVICE_NAME}_load_average_1min gauge
{SERVICE_NAME}_load_average_1min {load_1min:.2f}

# HELP {SERVICE_NAME}_active_connections Current active connections
# TYPE {SERVICE_NAME}_active_connections gauge
{SERVICE_NAME}_active_connections {active_connections}
""".format(
            SERVICE_NAME="{SERVICE_NAME}",
            request_count=request_count,
            avg_response_time=avg_response_time,
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_used_bytes=memory_used_bytes,
            process_memory_bytes=process_memory_bytes,
            process_cpu_percent=process_cpu_percent,
            network_bytes_sent=network.bytes_sent,
            network_bytes_recv=network.bytes_recv,
            load_1min=load_1min,
            active_connections=active_connections
        )
        
    except Exception as e:
        # Fallback to basic metrics if system metrics fail
        metrics_text = """# HELP {SERVICE_NAME}_requests_total Total number of requests
# TYPE {SERVICE_NAME}_requests_total counter
{SERVICE_NAME}_requests_total {request_count}

# HELP {SERVICE_NAME}_response_time_seconds Average response time
# TYPE {SERVICE_NAME}_response_time_seconds gauge
{SERVICE_NAME}_response_time_seconds {avg_response_time:.3f}

# HELP {SERVICE_NAME}_metrics_error System metrics collection error
# TYPE {SERVICE_NAME}_metrics_error gauge
{SERVICE_NAME}_metrics_error 1
""".format(
            SERVICE_NAME="{SERVICE_NAME}",
            request_count=request_count,
            avg_response_time=avg_response_time
        )
    
    return metrics_text, 200, {'Content-Type': 'text/plain'}


if __name__ == '__main__':
    print("🚀 Starting Demo FISS API...")
    print("📍 Available endpoints:")
    print("   - GET /api/base (system information)")
    print("   - GET /api/user (user profile)")
    print("   - GET /api/health (system health check)")
    print("   - GET /api/products (products list)")
    print("   - GET /api/orders (orders list)")
    print("   - GET /api/name (service name)")
    print("🌐 Server running at: http://localhost:5001")
    app.run(debug=True, host='0.0.0.0', port=5001)
