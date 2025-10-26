#!/usr/bin/env python3
"""
Start ArgoCD port-forward for ngrok connection
This script starts port-forward so ngrok can tunnel to ArgoCD on Kubernetes
"""

import subprocess
import sys
import time
import requests
import shutil

def check_kubectl():
    """Check if kubectl is available"""
    kubectl_path = shutil.which('kubectl')
    if kubectl_path:
        print(f"✅ kubectl is available at {kubectl_path}")
        return True
    else:
        print("❌ kubectl not found. Please install kubectl")
        return False

def check_argocd_namespace():
    """Check if ArgoCD namespace exists"""
    try:
        result = subprocess.run(
            ['kubectl', 'get', 'namespace', 'argocd'],
            capture_output=True,
            text=True,
            shell=True
        )
        if result.returncode == 0:
            print("✅ ArgoCD namespace exists")
            return True
        else:
            print("❌ ArgoCD namespace not found")
            return False
    except Exception as e:
        print(f"❌ Error checking namespace: {e}")
        return False

def start_port_forward():
    """Start kubectl port-forward for ArgoCD"""
    print("🚀 Starting port-forward for ArgoCD...")
    print("   Forwarding localhost:8080 -> argocd-server service:80")
    
    try:
        # Start port-forward in the background
        process = subprocess.Popen(
            ['kubectl', 'port-forward', 'svc/argocd-server', '-n', 'argocd', '8080:80'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=True
        )
        
        # Give it a moment to start
        time.sleep(2)
        
        # Check if process is still running
        if process.poll() is None:
            print("✅ Port-forward started successfully")
            print(f"   Process ID: {process.pid}")
            print()
            print("📋 Configuration:")
            print("   Local URL: http://localhost:8080")
            print("   ngrok URL: https://e509ac06fcdf.ngrok-free.app")
            print()
            print("⚠️  Important:")
            print("   - Keep this terminal window open")
            print("   - Port-forward will stop if you close this terminal")
            print("   - Press Ctrl+C to stop the port-forward")
            print()
            print("🔄 Port-forward is running... Press Ctrl+C to stop")
            
            try:
                # Wait for process to finish or be interrupted
                process.wait()
            except KeyboardInterrupt:
                print("\n🛑 Stopping port-forward...")
                process.terminate()
                process.wait()
                print("✅ Port-forward stopped")
                return True
        else:
            # Process died
            stdout, stderr = process.communicate()
            print("❌ Port-forward failed to start")
            print(f"Error: {stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Failed to start port-forward: {e}")
        return False

def test_connection():
    """Test if ArgoCD is accessible"""
    print("🔍 Testing ArgoCD connection...")
    
    try:
        response = requests.get('http://localhost:8080/api/version', timeout=5)
        if response.status_code == 200:
            version = response.json().get('Version', 'Unknown')
            print(f"✅ ArgoCD is accessible (Version: {version})")
            return True
        else:
            print(f"⚠️  ArgoCD responded with status {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot reach ArgoCD: {e}")
        print("   Make sure port-forward is running and ArgoCD is ready")
        return False

def main():
    """Main setup function"""
    print("🎯 Setting up ArgoCD port-forward for ngrok...\n")
    
    # Check prerequisites
    if not check_kubectl():
        sys.exit(1)
    
    if not check_argocd_namespace():
        print("\n💡 Tip: Make sure ArgoCD is installed in your Kubernetes cluster")
        sys.exit(1)
    
    # Start port-forward
    success = start_port_forward()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 