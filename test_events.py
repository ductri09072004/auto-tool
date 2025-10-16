from service_manager import ServiceManager

sm = ServiceManager()
events = list(sm.db.service_events.find().sort('timestamp', -1).limit(5))

print("Recent events:")
for e in events:
    print(f"Service: {e['service_name']}")
    print(f"  Type: {e['event_type']}")
    print(f"  Time: {e['timestamp']}")
    print()
