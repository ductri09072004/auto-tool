#!/usr/bin/env python3
"""Test webhook for all services"""

import requests
import json
from service_manager import ServiceManager

def test_webhook_for_service(service_name, commit_id="abc123"):
    """Test webhook for a specific service"""
    # Simulate GitHub webhook payload
    webhook_payload = {
        "repository": {
            "name": service_name,
            "full_name": f"ductri09072004/{service_name}"
        },
        "ref": "refs/heads/main",
        "head_commit": {
            "id": commit_id
        },
        "pusher": {
            "name": "ductri09072004"
        }
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": "push",
        "X-Hub-Signature-256": "sha256=dummy"  # Skip verification for testing
    }
    
    try:
        response = requests.post(
            "http://localhost:3050/api/github/webhook",
            headers=headers,
            json=webhook_payload,
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("SUCCESS: Webhook processed successfully!")
            return True
        else:
            print("FAILED: Webhook failed")
            return False
            
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_all_services():
    """Test webhook for all services in MongoDB"""
    try:
        # Connect to MongoDB
        sm = ServiceManager('mongodb+srv://BlueDuck2:Fcsunny0907@tpexpress.zjf26.mongodb.net/?retryWrites=true&w=majority&appName=TPExpress', 'AutoToolDevOPS')
        
        # Get all services
        services = sm.mongo_ops.db.services.find({}, {'name': 1})
        
        print(f"Testing webhook for {len(list(services))} services...")
        services.rewind()  # Reset cursor
        
        success_count = 0
        total_count = 0
        
        for service in services:
            service_name = service['name']
            total_count += 1
            
            print(f"\n{'='*50}")
            print(f"Testing webhook for: {service_name}")
            print(f"{'='*50}")
            
            success = test_webhook_for_service(service_name)
            if success:
                success_count += 1
        
        print(f"\n{'='*50}")
        print(f"SUMMARY: {success_count}/{total_count} webhooks processed successfully")
        print(f"{'='*50}")
        
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        # Test specific service
        service_name = sys.argv[1]
        test_webhook_for_service(service_name)
    else:
        # Test all services
        test_all_services()
