from flask import Flask, jsonify
import requests
import json

app = Flask(__name__)

# Service mapping - map UI service names to actual service URLs
SERVICE_MAPPING = {
    'aemo-v6': 'http://127.0.0.1:5001',  # aemo-v6 service running on port 5001
    'aemo-v6y': 'http://127.0.0.1:5001',  # if you have different UI name
    # Add more services as needed
}

@app.route('/api/<service_name>/api/health')
def proxy_health(service_name):
    """Proxy health endpoint to actual service"""
    try:
        # Get the actual service URL
        service_url = SERVICE_MAPPING.get(service_name)
        if not service_url:
            print(f"❌ Service {service_name} not found in mapping")
            return jsonify({
                "health_status": "unknown",
                "error": f"Service {service_name} not configured"
            }), 404
        
        # Call the actual service health endpoint
        health_url = f"{service_url}/api/health"
        print(f"🔄 Proxying {service_name} -> {health_url}")
        
        response = requests.get(health_url, timeout=5)
        
        if response.status_code == 200:
            raw_data = response.json()
            
            # Convert aemo-v6 format to tool expected format
            cpu_pct = raw_data.get('cpu_pct', 0)
            mem_total_mb = raw_data.get('mem_total_mb', 1)
            mem_used_mb = raw_data.get('mem_used_mb', 0)
            uptime_s = raw_data.get('uptime_s', 0)
            
            # Calculate memory percentage
            mem_percent = (mem_used_mb / mem_total_mb * 100) if mem_total_mb > 0 else 0
            
            # Convert uptime seconds to readable format
            hours = int(uptime_s // 3600)
            minutes = int((uptime_s % 3600) // 60)
            uptime_str = f"{hours}h {minutes}m"
            
            # Format data for tool
            formatted_data = {
                "health_status": "operational",
                "service_name": service_name,
                "uptime": uptime_str,
                "system_metrics": {
                    "cpu_usage": f"{cpu_pct:.1f}%",
                    "memory_usage": f"{mem_percent:.1f}%",
                    "disk_usage": "55.0%",  # Default since not provided
                    "process_memory_mb": f"{mem_used_mb:.1f}"
                },
                "service_metrics": {
                    "total_requests": 123,  # Default since not provided
                    "avg_response_time_ms": "12.4ms"  # Default since not provided
                },
                "timestamp": raw_data.get('timestamp', 1234567890)
            }
            
            print(f"✅ Got real metrics from {service_name}: CPU={cpu_pct:.1f}%, Memory={mem_percent:.1f}%")
            return jsonify(formatted_data), 200
        else:
            print(f"⚠️ Service {service_name} returned {response.status_code}")
            return jsonify({
                "health_status": "error",
                "error": f"Service returned {response.status_code}"
            }), response.status_code
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to service {service_name}")
        return jsonify({
            "health_status": "unreachable",
            "error": f"Cannot connect to {service_name}"
        }), 503
    except Exception as e:
        print(f"❌ Error proxying {service_name}: {e}")
        return jsonify({
            "health_status": "error",
            "error": str(e)
        }), 500

@app.route('/api/<service_name>/api/hello')
def proxy_hello(service_name):
    """Proxy hello endpoint to actual service"""
    try:
        service_url = SERVICE_MAPPING.get(service_name)
        if not service_url:
            return jsonify({"error": f"Service {service_name} not configured"}), 404
        
        hello_url = f"{service_url}/api/hello"
        response = requests.get(hello_url, timeout=3)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def gateway_health():
    """Gateway health check"""
    return jsonify({
        "status": "healthy",
        "service": "Mock Gateway",
        "mapped_services": list(SERVICE_MAPPING.keys())
    })

if __name__ == '__main__':
    print("🚀 Starting Mock Gateway on http://127.0.0.1:5005")
    print("📋 Mapped services:")
    for service, url in SERVICE_MAPPING.items():
        print(f"   {service} -> {url}")
    print("\n🔗 Test URLs:")
    print("   Gateway health: http://127.0.0.1:5005/health")
    print("   Service health: http://127.0.0.1:5005/api/aemo-v6/api/health")
    print("   Service hello:  http://127.0.0.1:5005/api/aemo-v6/api/hello")
    
    app.run(host='127.0.0.1', port=5005, debug=True)
