#!/usr/bin/env python3
"""Test Railway dashboard API for aemo-v2"""

import requests
import json

def test_railway_dashboard():
    print("🔍 Testing Railway dashboard API...")
    
    try:
        # Test Railway dashboard API
        railway_url = 'https://auto-tool.up.railway.app/api/services'
        response = requests.get(railway_url, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            services = data.get('services', [])
            print(f"✅ Railway Dashboard API working - found {len(services)} services")
            
            # Look for aemo-v2
            aemo_v2 = None
            for svc in services:
                if svc.get('name') == 'aemo-v2':
                    aemo_v2 = svc
                    break
                    
            if aemo_v2:
                print("✅ Found aemo-v2 in Railway dashboard:")
                print(f"  Name: {aemo_v2.get('name')}")
                print(f"  Status: {aemo_v2.get('status')}")
                print(f"  Health: {aemo_v2.get('health_status')}")
                print(f"  Sync: {aemo_v2.get('sync_status')}")
                print(f"  Port: {aemo_v2.get('port')}")
                print(f"  CPU Usage: {aemo_v2.get('cpu_usage')}")
                print(f"  Memory Usage: {aemo_v2.get('memory_usage')}")
                print(f"  Created: {aemo_v2.get('created_at')}")
                
                # Check if ArgoCD data is being retrieved
                if aemo_v2.get('health_status') != 'Unknown':
                    print("✅ ArgoCD API integration working!")
                else:
                    print("⚠️ ArgoCD API integration may have issues")
                    
            else:
                print("❌ aemo-v2 not found in Railway dashboard")
                print("Available services:")
                for svc in services:
                    print(f"  - {svc.get('name')}")
        else:
            print(f"❌ Railway Dashboard API returned status {response.status_code}")
            print(f"Response: {response.text[:200]}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to Railway dashboard API")
    except Exception as e:
        print(f"❌ Error testing Railway dashboard API: {e}")

if __name__ == "__main__":
    test_railway_dashboard()
