#!/usr/bin/env python3
"""
Setup ArgoCD locally for development
This script starts ArgoCD server locally on port 8080
"""

import subprocess
import sys
import time
import requests
import json
import threading
import os

def check_docker():
    """Check if Docker is running"""
    try:
        subprocess.run(['docker', '--version'], check=True, capture_output=True)
        print("✅ Docker is available")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Docker not found. Please install Docker Desktop")
        return False

def start_argocd():
    """Start ArgoCD using Docker"""
    print("🚀 Starting ArgoCD with Docker...")
    
    # Create ArgoCD container
    cmd = [
        'docker', 'run', '-d',
        '--name', 'argocd-server',
        '-p', '8080:8080',
        '-e', 'ARGOCD_SERVER_INSECURE=true',
        '-e', 'ARGOCD_SERVER_ROOT_PATH=/',
        'argoproj/argocd:latest',
        'argocd-server', '--insecure'
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print("✅ ArgoCD container started")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to start ArgoCD: {e}")
        return False

def wait_for_argocd():
    """Wait for ArgoCD to be ready"""
    print("⏳ Waiting for ArgoCD to be ready...")
    
    for i in range(30):  # Wait up to 30 seconds
        try:
            response = requests.get('http://localhost:8080/api/v1/version', timeout=5)
            if response.status_code == 200:
                print("✅ ArgoCD is ready!")
                return True
        except requests.exceptions.RequestException:
            pass
        
        time.sleep(1)
        print(f"   Attempt {i+1}/30...")
    
    print("❌ ArgoCD failed to start within 30 seconds")
    return False

def get_admin_password():
    """Get ArgoCD admin password"""
    print("🔑 Getting ArgoCD admin password...")
    
    try:
        # Get password from container logs
        result = subprocess.run([
            'docker', 'exec', 'argocd-server', 
            'argocd', 'admin', 'initial-password'
        ], capture_output=True, text=True, check=True)
        
        password = result.stdout.strip()
        print(f"✅ ArgoCD Admin Password: {password}")
        return password
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to get admin password: {e}")
        return None

def show_instructions(password):
    """Show setup instructions"""
    print("\n🎉 ArgoCD setup complete!")
    print(f"🌐 ArgoCD UI: http://localhost:8080")
    print(f"🔑 Admin Password: {password}")
    print(f"👤 Username: admin")
    
    print("\n📋 Next steps:")
    print("1. Open http://localhost:8080 in your browser")
    print("2. Login with admin / {password}")
    print("3. Your Dev Portal can now access ArgoCD via: https://auto-tool.up.railway.app/argocd")
    
    print("\n🔧 Configuration for Dev Portal:")
    print("Set these environment variables in your Dev Portal Railway project:")
    print(f"ARGOCD_SERVER_URL = http://localhost:8080")
    print(f"ARGOCD_ADMIN_PASSWORD = {password}")
    
    print("\n🌐 Public Access:")
    print("Your local ArgoCD is now accessible via:")
    print("https://auto-tool.up.railway.app/argocd")

def main():
    """Main setup function"""
    print("🎯 Setting up ArgoCD locally...")
    
    # Check prerequisites
    if not check_docker():
        return False
    
    # Start ArgoCD
    if not start_argocd():
        return False
    
    # Wait for ArgoCD to be ready
    if not wait_for_argocd():
        return False
    
    # Get admin password
    password = get_admin_password()
    if not password:
        return False
    
    # Show instructions
    show_instructions(password)
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
