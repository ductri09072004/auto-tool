#!/usr/bin/env python3
"""Setup webhooks for all services in MongoDB"""

import requests
import json
from service_manager import ServiceManager

def setup_webhooks():
    """Setup webhooks for all services"""
    try:
        # Connect to MongoDB
        sm = ServiceManager('mongodb+srv://BlueDuck2:Fcsunny0907@tpexpress.zjf26.mongodb.net/?retryWrites=true&w=majority&appName=TPExpress', 'AutoToolDevOPS')
        
        # Get all services
        services = sm.mongo_ops.db.services.find({}, {'name': 1, 'repo_url': 1})
        
        print(f"Found {len(list(services))} services in database")
        services.rewind()  # Reset cursor
        
        webhook_url = "http://localhost:3050/api/github/webhook"
        
        print(f"\nWebhook URL: {webhook_url}")
        print("=" * 60)
        
        for service in services:
            service_name = service['name']
            repo_url = service.get('repo_url', '')
            
            print(f"\nService: {service_name}")
            print(f"Repo URL: {repo_url}")
            
            # Extract owner/repo from URL
            if repo_url:
                if 'github.com' in repo_url:
                    parts = repo_url.replace('.git', '').split('/')
                    if len(parts) >= 2:
                        owner = parts[-2]
                        repo = parts[-1]
                        github_repo = f"{owner}/{repo}"
                        
                        print(f"GitHub Repo: {github_repo}")
                        print(f"Webhook URL: {webhook_url}")
                        print("✅ Ready for webhook setup")
                        
                        # Instructions for manual setup
                        print(f"\n📋 Manual Setup Instructions:")
                        print(f"1. Go to: https://github.com/{github_repo}/settings/hooks")
                        print(f"2. Click 'Add webhook'")
                        print(f"3. Payload URL: {webhook_url}")
                        print(f"4. Content type: application/json")
                        print(f"5. Events: Just the push event")
                        print(f"6. Secret: (optional for development)")
                        print(f"7. Click 'Add webhook'")
                    else:
                        print("❌ Invalid GitHub URL format")
                else:
                    print("⚠️ Not a GitHub repository")
            else:
                print("❌ No repo URL configured")
            
            print("-" * 40)
        
        print(f"\n🎉 Webhook setup instructions generated for all services!")
        print(f"\n💡 Test webhook with:")
        print(f"curl -X POST {webhook_url} \\")
        print(f"  -H 'Content-Type: application/json' \\")
        print(f"  -H 'X-GitHub-Event: push' \\")
        print(f"  -d '{{\"repository\":{{\"name\":\"demo-v107\"}},\"ref\":\"refs/heads/main\",\"head_commit\":{{\"id\":\"abc123\"}}}}'")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    setup_webhooks()
