#!/usr/bin/env python3
"""
Test recreate YAML endpoint directly
"""
import requests
import json

def test_recreate_yaml():
    """Test recreate YAML endpoint"""
    
    try:
        print("Testing recreate YAML endpoint...")
        
        response = requests.post(
            'http://localhost:3050/api/service/recreate-yaml/demo-v107',
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("SUCCESS: Recreate YAML test successful!")
        else:
            print("FAILED: Recreate YAML test failed!")
            
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_recreate_yaml()
