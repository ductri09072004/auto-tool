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
import socket
from datetime import datetime

# Try to import psutil, fallback to subprocess if not available
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

class ArgoCDManager:
    def __init__(self):
        self.argocd_process = None
        self.running = True
        self.restart_count = 0
        self.max_restarts = 10
        self.health_check_interval = 30  # seconds
        self.ngrok_url = "https://nonobligatory-aisha-twee.ngrok-free.dev"  # Fixed ngrok URL
        
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

    def check_argocd_service(self):
        """Check if ArgoCD server service exists and is ready"""
        try:
            result = subprocess.run(
                ['kubectl', 'get', 'svc', 'argocd-server', '-n', 'argocd'],
                capture_output=True,
                text=True,
                shell=True,
                timeout=10
            )
            if result.returncode == 0:
                print("✅ ArgoCD server service exists")
                return True
            else:
                print("❌ ArgoCD server service not found")
                print(f"   Error: {result.stderr}")
                return False
        except Exception as e:
            print(f"❌ Error checking ArgoCD service: {e}")
            return False

    def start_argocd_portforward(self):
        """Start ArgoCD port-forward"""
        print("🚀 Starting ArgoCD port-forward...")
        
        try:
            # Check if port 8080 is available
            if not self.check_port_available(8080):
                print("⚠️ Port 8080 is already in use, cleaning up...")
                self.kill_all_port_forwards()
                time.sleep(2)
                if not self.check_port_available(8080):
                    print("❌ Port 8080 is still in use after cleanup")
                    print("💡 Please manually kill the process using port 8080")
                    return False
            
            # Stop existing port-forward
            self.stop_argocd_portforward()
            
            # Check ArgoCD service exists
            if not self.check_argocd_service():
                print("❌ Cannot start port-forward: ArgoCD service not available")
                return False
            
            # Start port-forward
            self.argocd_process = subprocess.Popen(
                ['kubectl', 'port-forward', 'svc/argocd-server', '-n', 'argocd', '8080:80'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=True
            )
            
            # Wait a bit for process to start
            time.sleep(3)
            
            # Check if process is still running
            if self.argocd_process and self.argocd_process.poll() is None:
                print(f"✅ ArgoCD port-forward started (PID: {self.argocd_process.pid})")
                return True
            else:
                # Process died immediately, read error from stderr
                error_output = ""
                if self.argocd_process:
                    try:
                        _, stderr_data = self.argocd_process.communicate(timeout=1)
                        error_output = stderr_data if stderr_data else ""
                    except:
                        pass
                
                print("❌ ArgoCD port-forward failed to start")
                if error_output:
                    print(f"   Error details: {error_output[:200]}")
                else:
                    print("   (No error details available)")
                return False
                
        except Exception as e:
            print(f"❌ Failed to start ArgoCD port-forward: {e}")
            return False

    def kill_all_port_forwards(self):
        """Kill all existing kubectl port-forward processes"""
        try:
            if HAS_PSUTIL:
                # psutil is available, use it for better process management
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        cmdline = proc.info.get('cmdline', [])
                        if cmdline and 'kubectl' in ' '.join(cmdline).lower() and 'port-forward' in ' '.join(cmdline).lower():
                            if 'argocd-server' in ' '.join(cmdline) or '8080:80' in ' '.join(cmdline):
                                print(f"🧹 Killing existing port-forward process (PID: {proc.info['pid']})")
                                proc.terminate()
                                try:
                                    proc.wait(timeout=3)
                                except psutil.TimeoutExpired:
                                    proc.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            else:
                # Fallback: Use Windows taskkill or Linux pkill
                if sys.platform == 'win32':
                    # Windows: Find and kill kubectl port-forward processes
                    try:
                        # Find PIDs of processes listening on port 8080
                        result = subprocess.run(
                            ['netstat', '-ano'],
                            capture_output=True,
                            text=True,
                            shell=True,
                            timeout=5
                        )
                        if result.returncode == 0:
                            lines = result.stdout.split('\n')
                            for line in lines:
                                if ':8080' in line and 'LISTENING' in line:
                                    parts = line.split()
                                    if len(parts) > 4:
                                        pid = parts[-1]
                                        # Verify it's kubectl
                                        try:
                                            task_result = subprocess.run(
                                                ['tasklist', '/FI', f'PID eq {pid}'],
                                                capture_output=True,
                                                text=True,
                                                shell=True,
                                                timeout=3
                                            )
                                            if 'kubectl' in task_result.stdout:
                                                print(f"🧹 Killing kubectl process (PID: {pid})")
                                                subprocess.run(['taskkill', '/F', '/PID', pid], shell=True, timeout=5)
                                        except:
                                            pass
                    except Exception as e:
                        print(f"⚠️ Error killing processes: {e}")
                else:
                    # Linux/Mac: Use pkill
                    try:
                        subprocess.run(['pkill', '-f', 'kubectl.*port-forward.*argocd-server'], timeout=5)
                        print("🧹 Killed existing kubectl port-forward processes")
                    except:
                        pass
            
            time.sleep(1)  # Wait for processes to die
        except Exception as e:
            print(f"⚠️ Error killing port-forward processes: {e}")

    def check_port_available(self, port):
        """Check if port is available"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(('127.0.0.1', port))
            sock.close()
            return True
        except OSError:
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
        
        # Also kill any orphaned port-forward processes
        self.kill_all_port_forwards()

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
        
        # Check ArgoCD service
        if not self.check_argocd_service():
            print("\n💡 Tip: Make sure ArgoCD server service is running")
            print("   Run: kubectl get svc -n argocd")
            sys.exit(1)
        
        # Start ArgoCD port-forward
        print("\n🚀 Starting ArgoCD port-forward...")
        if not self.start_argocd_portforward():
            print("\n❌ Failed to start ArgoCD port-forward")
            print("💡 Troubleshooting tips:")
            print("   1. Check if port 8080 is available: netstat -ano | findstr :8080")
            print("   2. Verify ArgoCD service: kubectl get svc argocd-server -n argocd")
            print("   3. Check kubectl can connect: kubectl cluster-info")
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