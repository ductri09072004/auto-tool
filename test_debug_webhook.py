#!/usr/bin/env python3
"""
Test debug webhook endpoint
"""
import requests
import json

def test_debug_webhook():
    """Test debug webhook with minimal payload"""
    
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
        'Content-Type': 'application/json'
    }
    
    try:
        print("Testing debug webhook endpoint...")
        
        response = requests.post(
            'http://localhost:3050/api/github/webhook-debug',
            headers=headers,
            json=payload,
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("SUCCESS: Debug webhook test successful!")
        else:
            print("FAILED: Debug webhook test failed!")
            
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_debug_webhook()
