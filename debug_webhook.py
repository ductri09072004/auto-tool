#!/usr/bin/env python3
"""
Debug webhook endpoint
"""
import requests
import json

def test_webhook_simple():
    """Test webhook with minimal payload"""
    
    # Simple webhook payload
    payload = {
        "repository": {
            "name": "demo-v107",
            "full_name": "ductri09072004/demo-v107"
        },
        "ref": "refs/heads/main",
        "head_commit": {
            "id": "abc123def456"
        }
    }
    
    headers = {
        'Content-Type': 'application/json',
        'X-GitHub-Event': 'push',
        'X-Hub-Signature-256': 'sha256=dummy'
    }
    
    try:
        print("Testing webhook endpoint...")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(
            'http://localhost:3050/api/github/webhook',
            headers=headers,
            json=payload,
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("✅ Webhook test successful!")
        else:
            print("❌ Webhook test failed!")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_webhook_simple()
