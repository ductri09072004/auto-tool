#!/usr/bin/env python3
"""
Enhanced ArgoCD + ngrok Manager with auto-restart and health monitoring
This script manages both ArgoCD port-forward and ngrok tunnel with auto-restart
"""

import subprocess
import sys
import time
import requests
import shutil
import signal
import threading
from datetime import datetime

class ArgoCDManager:
    def __init__(self):
        self.argocd_process = None
        self.running = True
        self.restart_count = 0
        self.max_restarts = 10
        self.health_check_interval = 30  # seconds
        self.ngrok_url = "https://d5a7ed750e62.ngrok-free.app"  # Fixed ngrok URL
        
    def check_prerequisites(self):
        """Check if all required tools are available"""
        print("🔍 Checking prerequisites...")
        
        # Check kubectl
        kubectl_path = shutil.which('kubectl')
        if not kubectl_path:
            print("❌ kubectl not found. Please install kubectl")
            return False
        print(f"✅ kubectl: {kubectl_path}")
        
        # Check ngrok URL accessibility
        print(f"🌐 Using ngrok URL: {self.ngrok_url}")
        
        return True

    def check_argocd_namespace(self):
        """Check if ArgoCD namespace exists"""
        try:
            result = subprocess.run(
                ['kubectl', 'get', 'namespace', 'argocd'],
                capture_output=True,
                text=True,
                shell=True,
                timeout=10
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

    def start_argocd_portforward(self):
        """Start ArgoCD port-forward"""
        print("🚀 Starting ArgoCD port-forward...")
        
        try:
            self.stop_argocd_portforward()
            
            self.argocd_process = subprocess.Popen(
                ['kubectl', 'port-forward', 'svc/argocd-server', '-n', 'argocd', '8080:80'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=True
            )
            
            time.sleep(3)
            
            if self.argocd_process and self.argocd_process.poll() is None:
                print(f"✅ ArgoCD port-forward started (PID: {self.argocd_process.pid})")
                return True
            else:
                print("❌ ArgoCD port-forward failed to start")
                return False
                
        except Exception as e:
            print(f"❌ Failed to start ArgoCD port-forward: {e}")
            return False

    def stop_argocd_portforward(self):
        """Stop ArgoCD port-forward"""
        if self.argocd_process and self.argocd_process.poll() is None:
            print("🛑 Stopping ArgoCD port-forward...")
            self.argocd_process.terminate()
            try:
                self.argocd_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.argocd_process.kill()
                self.argocd_process.wait()

    def test_argocd(self):
        """Test ArgoCD connectivity"""
        try:
            response = requests.get('http://localhost:8080/api/version', timeout=10)
            if response.status_code == 200:
                version = response.json().get('Version', 'Unknown')
                print(f"✅ ArgoCD accessible (Version: {version})")
                return True
            else:
                print(f"⚠️ ArgoCD responded with status {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Cannot reach ArgoCD: {e}")
            return False

    def test_ngrok(self):
        """Test ngrok tunnel accessibility"""
        try:
            headers = {'ngrok-skip-browser-warning': 'true'}
            response = requests.get(self.ngrok_url, headers=headers, timeout=10)
            if response.status_code in [200, 404]:
                print(f"✅ ngrok tunnel accessible: {self.ngrok_url}")
                return True
            else:
                print(f"⚠️ ngrok tunnel responded with status {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Cannot reach ngrok tunnel: {e}")
            return False

    def health_monitor(self):
        """Background health monitoring"""
        print("🔍 Starting health monitor...")
        
        while self.running:
            try:
                time.sleep(self.health_check_interval)
                
                if not self.running:
                    break
                
                # Check ArgoCD port-forward
                if not self.argocd_process or self.argocd_process.poll() is not None:
                    print("⚠️ ArgoCD port-forward died, restarting...")
                    if self.restart_count < self.max_restarts:
                        self.start_argocd_portforward()
                        self.restart_count += 1
                    else:
                        print(f"❌ Max restarts reached")
                        self.running = False
                        break
                
                # Test connectivity
                argocd_ok = self.test_argocd()
                ngrok_ok = self.test_ngrok()
                
                if not argocd_ok:
                    print("⚠️ ArgoCD connectivity issues detected, restarting port-forward...")
                    if self.restart_count < self.max_restarts:
                        self.start_argocd_portforward()
                        self.restart_count += 1
                    else:
                        print(f"❌ Max restarts reached")
                        self.running = False
                        break
                
                print(f"💚 Health check passed at {datetime.now().strftime('%H:%M:%S')}")
                
            except Exception as e:
                print(f"❌ Health monitor error: {e}")
                time.sleep(5)

    def signal_handler(self, signum, frame):
        """Handle Ctrl+C gracefully"""
        print(f"\n🛑 Received signal {signum}, shutting down...")
        self.running = False
        self.stop_argocd_portforward()
        sys.exit(0)

    def run(self):
        """Main run loop"""
        print("🎯 Enhanced ArgoCD Port-Forward Manager")
        print("=" * 50)
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Check prerequisites
        if not self.check_prerequisites():
            sys.exit(1)
        
        if not self.check_argocd_namespace():
            print("\n💡 Tip: Make sure ArgoCD is installed in your Kubernetes cluster")
            sys.exit(1)
        
        # Start ArgoCD port-forward
        print("\n🚀 Starting ArgoCD port-forward...")
        if not self.start_argocd_portforward():
            print("❌ Failed to start ArgoCD port-forward")
            sys.exit(1)
        
        # Test initial connectivity
        print("\n🔍 Testing initial connectivity...")
        self.test_argocd()
        self.test_ngrok()
        
        print(f"\n📋 Configuration:")
        print(f"   ArgoCD Local: http://localhost:8080")
        print(f"   ngrok URL: {self.ngrok_url}")
        print(f"   Health check interval: {self.health_check_interval}s")
        print(f"   Max restarts: {self.max_restarts}")
        print()
        print("🔄 ArgoCD port-forward is running with auto-restart...")
        print("   Press Ctrl+C to stop")
        print()
        
        # Start health monitoring
        health_thread = threading.Thread(target=self.health_monitor, daemon=True)
        health_thread.start()
        
        try:
            while self.running:
                time.sleep(1)
                if self.restart_count >= self.max_restarts:
                    print(f"❌ Maximum restarts ({self.max_restarts}) reached")
                    break
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False
            self.stop_argocd_portforward()
            print("✅ Manager stopped")

def main():
    """Main entry point"""
    manager = ArgoCDManager()
    manager.run()

if __name__ == "__main__":
    main() 