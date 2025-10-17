#!/usr/bin/env python3
"""
Test webhook với ngrok URL
"""

import requests
import json

def test_ngrok_webhook():
    """Test webhook với ngrok URL"""
    
    ngrok_url = "https://meagan-submucronate-telephonically.ngrok-free.dev"
    webhook_url = f"{ngrok_url}/api/github/webhook"
    
    payload = {
        "repository": {
            "name": "demo-v107",
            "full_name": "ductri09072004/demo-v107"
        },
        "ref": "refs/heads/main",
        "head_commit": {
            "id": "abc123",
            "message": "Test commit from ngrok"
        }
    }
    
    headers = {
        'Content-Type': 'application/json',
        'X-GitHub-Event': 'push'
    }
    
    print("=== TESTING NGROK WEBHOOK ===")
    print(f"Ngrok URL: {ngrok_url}")
    print(f"Webhook URL: {webhook_url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(webhook_url, json=payload, headers=headers, timeout=30)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("SUCCESS: Ngrok webhook working!")
            try:
                data = response.json()
                print(f"Service: {data.get('service_name')}")
                print(f"Image Tag: {data.get('image_tag')}")
                print(f"YAML Recreation: {data.get('yaml_recreation_success')}")
            except:
                pass
        else:
            print(f"FAILED: Got status {response.status_code}")
            
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_ngrok_webhook()
