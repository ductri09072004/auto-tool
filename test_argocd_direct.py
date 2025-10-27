#!/usr/bin/env python3
"""Test ArgoCD API directly"""

import requests
import json

def test_argocd_api():
    print("🔍 Testing ArgoCD API directly...")
    
    # ArgoCD configuration
    argocd_url = "https://f6dde8d941f5.ngrok-free.app"
    admin_password = "IG42zHWiFya1XbaR"
    
    try:
        # Step 1: Login to ArgoCD
        print("🔐 Attempting to login to ArgoCD...")
        login_url = f"{argocd_url}/api/v1/session"
        login_data = {
            "username": "admin",
            "password": admin_password
        }
        
        headers = {
            'Content-Type': 'application/json',
            'ngrok-skip-browser-warning': 'true'
        }
        
        login_response = requests.post(login_url, json=login_data, headers=headers, timeout=10, verify=False)
        
        if login_response.status_code == 200:
            login_data = login_response.json()
            session_token = login_data.get('token')
            
            if session_token:
                print("✅ Successfully logged in to ArgoCD")
                print(f"Session token: {session_token[:20]}...")
                
                # Step 2: Get applications list
                print("\n📋 Getting applications list...")
                apps_url = f"{argocd_url}/api/v1/applications"
                auth_headers = {
                    'Authorization': f'Bearer {session_token}',
                    'ngrok-skip-browser-warning': 'true'
                }
                
                apps_response = requests.get(apps_url, headers=auth_headers, timeout=10, verify=False)
                
                if apps_response.status_code == 200:
                    apps_data = apps_response.json()
                    applications = apps_data.get('items', [])
                    print(f"✅ Found {len(applications)} applications")
                    
                    # Look for aemo-v2
                    aemo_v2_app = None
                    for app in applications:
                        if app.get('metadata', {}).get('name') == 'aemo-v2':
                            aemo_v2_app = app
                            break
                    
                    if aemo_v2_app:
                        print("✅ Found aemo-v2 application:")
                        status = aemo_v2_app.get('status', {})
                        health = status.get('health', {})
                        sync = status.get('sync', {})
                        
                        print(f"  Name: {aemo_v2_app.get('metadata', {}).get('name')}")
                        print(f"  Health Status: {health.get('status', 'Unknown')}")
                        print(f"  Sync Status: {sync.get('status', 'Unknown')}")
                        print(f"  Namespace: {aemo_v2_app.get('spec', {}).get('destination', {}).get('namespace', 'Unknown')}")
                        
                        # Test getting specific application
                        print(f"\n🔍 Testing specific application API...")
                        app_url = f"{argocd_url}/api/v1/applications/aemo-v2"
                        app_response = requests.get(app_url, headers=auth_headers, timeout=10, verify=False)
                        
                        if app_response.status_code == 200:
                            print("✅ Specific application API working")
                        else:
                            print(f"❌ Specific application API returned {app_response.status_code}")
                            print(f"Response: {app_response.text[:200]}")
                    else:
                        print("❌ aemo-v2 application not found")
                        print("Available applications:")
                        for app in applications:
                            name = app.get('metadata', {}).get('name')
                            print(f"  - {name}")
                else:
                    print(f"❌ Applications API returned status {apps_response.status_code}")
                    print(f"Response: {apps_response.text[:200]}")
            else:
                print("❌ No session token in login response")
                print(f"Login response: {login_data}")
        else:
            print(f"❌ Login failed with status {login_response.status_code}")
            print(f"Response: {login_response.text[:200]}")
            
    except Exception as e:
        print(f"❌ Error testing ArgoCD API: {e}")

if __name__ == "__main__":
    test_argocd_api()
