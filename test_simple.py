#!/usr/bin/env python3
"""
Test simple endpoint
"""
import requests
import json

def test_simple():
    """Test simple endpoint"""
    
    payload = {"test": "data"}
    
    try:
        print("Testing simple endpoint...")
        
        response = requests.post(
            'http://localhost:3050/api/test-simple',
            json=payload,
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("SUCCESS: Simple test successful!")
        else:
            print("FAILED: Simple test failed!")
            
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_simple()
