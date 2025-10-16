from service_manager import ServiceManager

sm = ServiceManager()
services = sm.get_services()

print("Services details:")
for s in services:
    print(f"Service: {s['name']}")
    print(f"  Created: {s.get('created_at', 'N/A')}")
    print(f"  Metadata: {s.get('metadata', {})}")
    print(f"  Source: {s.get('metadata', {}).get('created_by', 'N/A')}")
    print()
