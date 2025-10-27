#!/usr/bin/env python3
"""Test script to check aemo-v2 service data"""

from service_manager import ServiceManager
import os
import json

def test_aemo_v2():
    print("🔍 Testing aemo-v2 service...")
    
    # Connect to MongoDB
    mongo_uri = os.environ.get('MONGO_URI', 'mongodb+srv://BlueDuck2:Fcsunny0907@tpexpress.zjf26.mongodb.net/?retryWrites=true&w=majority&appName=TPExpress')
    mongo_db = os.environ.get('MONGO_DB', 'AutoToolDevOPS')
    service_manager = ServiceManager(mongo_uri, mongo_db)

    # Get all services
    services = service_manager.get_services()
    print(f"📋 Total services in MongoDB: {len(services)}")
    
    print("\n📋 All services:")
    for svc in services:
        name = svc.get('name') or svc.get('service_name')
        print(f"  - {name}")

    # Look for aemo-v2
    print(f"\n🔍 Looking for aemo-v2...")
    aemo_v2 = None
    for svc in services:
        name = svc.get('name') or svc.get('service_name')
        if name == 'aemo-v2':
            aemo_v2 = svc
            break

    if aemo_v2:
        print("✅ Found aemo-v2 service:")
        print(f"  Name: {aemo_v2.get('name')}")
        print(f"  Port: {aemo_v2.get('port')}")
        print(f"  Description: {aemo_v2.get('description')}")
        print(f"  Created: {aemo_v2.get('created_at')}")
        metadata = aemo_v2.get('metadata', {})
        print(f"  Metadata keys: {list(metadata.keys()) if metadata else 'None'}")
        
        # Test ArgoCD API access
        print(f"\n🔗 Testing ArgoCD API access...")
        try:
            from app import _get_argocd_session_token
            from config import ARGOCD_SERVER_URL
            import requests
            
            session_token = _get_argocd_session_token()
            if session_token:
                print(f"✅ Got ArgoCD session token")
                
                headers = {
                    'Authorization': f'Bearer {session_token}',
                    'ngrok-skip-browser-warning': 'true'
                }
                
                # Test getting application info
                app_response = requests.get(f"{ARGOCD_SERVER_URL}/api/v1/applications/aemo-v2", 
                                         headers=headers, timeout=10, verify=False)
                
                if app_response.status_code == 200:
                    app_data = app_response.json()
                    print(f"✅ ArgoCD API working - got application data")
                    print(f"  Health: {app_data.get('status', {}).get('health', {}).get('status', 'Unknown')}")
                    print(f"  Sync: {app_data.get('status', {}).get('sync', {}).get('status', 'Unknown')}")
                else:
                    print(f"❌ ArgoCD API returned status {app_response.status_code}")
                    print(f"  Response: {app_response.text[:200]}")
            else:
                print(f"❌ Could not get ArgoCD session token")
                
        except Exception as e:
            print(f"❌ Error testing ArgoCD API: {e}")
            
    else:
        print("❌ aemo-v2 service not found in MongoDB")

if __name__ == "__main__":
    test_aemo_v2()
