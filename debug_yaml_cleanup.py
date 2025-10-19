#!/usr/bin/env python3
"""
Debug script to check and fix YAML file cleanup issues
"""
import os
import subprocess
import shutil
import tempfile
import json
import time

def check_service_status(service_name):
    """Check if service is properly synced and running"""
    print(f"🔍 Checking status for service: {service_name}")
    
    try:
        # 1. Check ArgoCD sync status
        argocd_result = subprocess.run(
            ['kubectl', 'get', 'application', service_name, '-n', 'argocd', '-o', 'jsonpath={.status.sync.status}'],
            capture_output=True, text=True, timeout=10
        )
        sync_status = argocd_result.stdout.strip() if argocd_result.returncode == 0 else 'Unknown'
        print(f"   ArgoCD Sync Status: {sync_status}")
        
        # 2. Check pods status
        pods_result = subprocess.run(
            ['kubectl', 'get', 'pods', '-l', f'app={service_name}', '-n', service_name, '-o', 'jsonpath={.items[*].status.phase}'],
            capture_output=True, text=True, timeout=10
        )
        pods_status = pods_result.stdout.strip() if pods_result.returncode == 0 else 'Unknown'
        print(f"   Pods Status: {pods_status}")
        
        # 3. Check deployment status
        deployment_result = subprocess.run(
            ['kubectl', 'get', 'deployment', service_name, '-n', service_name, '-o', 'jsonpath={.status.readyReplicas}'],
            capture_output=True, text=True, timeout=10
        )
        ready_replicas = deployment_result.stdout.strip() if deployment_result.returncode == 0 else 'Unknown'
        print(f"   Ready Replicas: {ready_replicas}")
        
        # 4. Check if service is healthy
        health_result = subprocess.run(
            ['kubectl', 'get', 'pods', '-l', f'app={service_name}', '-n', service_name, '-o', 'jsonpath={.items[0].status.conditions[?(@.type=="Ready")].status}'],
            capture_output=True, text=True, timeout=10
        )
        health_status = health_result.stdout.strip() if health_result.returncode == 0 else 'Unknown'
        print(f"   Health Status: {health_status}")
        
        # Determine if service is ready for cleanup
        is_synced = sync_status == 'Synced'
        has_running_pods = 'Running' in pods_status
        has_ready_replicas = ready_replicas.isdigit() and int(ready_replicas) > 0
        is_healthy = health_status == 'True'
        
        print(f"\n📊 Summary:")
        print(f"   - ArgoCD Synced: {'✅' if is_synced else '❌'}")
        print(f"   - Pods Running: {'✅' if has_running_pods else '❌'}")
        print(f"   - Deployment Ready: {'✅' if has_ready_replicas else '❌'}")
        print(f"   - Service Healthy: {'✅' if is_healthy else '❌'}")
        
        return is_synced and has_running_pods and has_ready_replicas and is_healthy
        
    except Exception as e:
        print(f"❌ Error checking service status: {e}")
        return False

def cleanup_yaml_files_manual(service_name, repo_b_url):
    """Manually cleanup YAML files from Repo B"""
    print(f"\n🧹 Manual cleanup for service: {service_name}")
    print(f"📁 Repository: {repo_b_url}")
    
    yaml_files_to_delete = [
        'deployment.yaml',
        'service.yaml', 
        'configmap.yaml',
        'hpa.yaml',
        'ingress.yaml',
        'ingress-gateway.yaml',
        'namespace.yaml',
        'secret.yaml',
        'argocd-application.yaml'
    ]
    
    try:
        # Create temp directory
        temp_dir = tempfile.gettempdir()
        clone_dir = os.path.join(temp_dir, f'cleanup_{service_name}_{int(time.time())}')
        
        print(f"📂 Temp directory: {clone_dir}")
        
        # Remove existing directory if it exists
        if os.path.exists(clone_dir):
            print("🗑️  Removing existing temp directory...")
            shutil.rmtree(clone_dir)
        
        # Clone repository
        print("📥 Cloning repository...")
        clone_proc = subprocess.run(['git', 'clone', repo_b_url, clone_dir], 
                                  capture_output=True, text=True, timeout=60)
        
        if clone_proc.returncode != 0:
            print(f"❌ Failed to clone repository: {clone_proc.stderr}")
            return False
        
        print("✅ Repository cloned successfully")
        
        # Check if service directory exists
        service_path = f"services/{service_name}/k8s"
        full_service_path = os.path.join(clone_dir, service_path)
        
        if not os.path.exists(full_service_path):
            print(f"⚠️  Service directory not found: {service_path}")
            return False
        
        print(f"📁 Service directory found: {service_path}")
        
        # List existing files
        existing_files = os.listdir(full_service_path)
        print(f"📄 Existing files: {existing_files}")
        
        # Delete YAML files
        deleted_files = []
        for yaml_file in yaml_files_to_delete:
            file_path = os.path.join(full_service_path, yaml_file)
            if os.path.exists(file_path):
                os.remove(file_path)
                deleted_files.append(yaml_file)
                print(f"🗑️  Deleted: {yaml_file}")
            else:
                print(f"⚠️  File not found: {yaml_file}")
        
        if not deleted_files:
            print("ℹ️  No YAML files found to delete")
            return True
        
        # Check if directory is empty
        remaining_files = os.listdir(full_service_path)
        print(f"📄 Remaining files: {remaining_files}")
        
        # Remove empty directories
        if not remaining_files:
            print("📁 Removing empty k8s directory...")
            os.rmdir(full_service_path)
            
            # Check if services directory is empty
            services_dir = os.path.join(clone_dir, 'services', service_name)
            if os.path.exists(services_dir) and not os.listdir(services_dir):
                print("📁 Removing empty service directory...")
                os.rmdir(services_dir)
        
        # Commit and push changes
        print("💾 Committing changes...")
        
        # Configure git
        subprocess.run(['git', 'config', 'user.email', 'dev-portal@local'], cwd=clone_dir, check=True)
        subprocess.run(['git', 'config', 'user.name', 'Dev Portal'], cwd=clone_dir, check=True)
        
        # Add changes
        subprocess.run(['git', 'add', '--all'], cwd=clone_dir, check=True)
        
        # Check if there are changes
        status_proc = subprocess.run(['git', 'status', '--porcelain'], cwd=clone_dir, capture_output=True, text=True, check=True)
        
        if status_proc.stdout.strip():
            # Commit changes
            commit_msg = f"Clean up YAML files for {service_name} after ArgoCD sync"
            commit_proc = subprocess.run(['git', 'commit', '-m', commit_msg], cwd=clone_dir, capture_output=True, text=True)
            
            if commit_proc.returncode == 0:
                print("✅ Changes committed successfully")
                
                # Push changes
                print("📤 Pushing changes...")
                push_proc = subprocess.run(['git', 'push', 'origin', 'main'], cwd=clone_dir, capture_output=True, text=True)
                
                if push_proc.returncode == 0:
                    print(f"✅ Successfully cleaned up {len(deleted_files)} YAML files")
                    print(f"📄 Deleted files: {deleted_files}")
                else:
                    print(f"❌ Failed to push changes: {push_proc.stderr}")
                    return False
            else:
                print(f"❌ Failed to commit changes: {commit_proc.stderr}")
                return False
        else:
            print("ℹ️  No changes to commit")
        
        # Cleanup temp directory
        shutil.rmtree(clone_dir)
        print("🧹 Cleaned up temp directory")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python debug_yaml_cleanup.py <service_name> [repo_b_url]")
        print("Example: python debug_yaml_cleanup.py demo-v109")
        sys.exit(1)
    
    service_name = sys.argv[1]
    repo_b_url = sys.argv[2] if len(sys.argv) > 2 else "https://github.com/ductri09072004/demo_fiss1_B"
    
    print(f"🔧 Debug YAML Cleanup for: {service_name}")
    print("=" * 60)
    
    # Check service status
    is_ready = check_service_status(service_name)
    
    if is_ready:
        print("\n✅ Service is ready for cleanup!")
        
        # Ask user confirmation
        response = input("\n🤔 Do you want to proceed with YAML cleanup? (y/N): ").strip().lower()
        
        if response in ['y', 'yes']:
            success = cleanup_yaml_files_manual(service_name, repo_b_url)
            
            if success:
                print("\n🎉 YAML cleanup completed successfully!")
            else:
                print("\n❌ YAML cleanup failed!")
        else:
            print("\n⏸️  Cleanup cancelled by user")
    else:
        print("\n⚠️  Service is not ready for cleanup yet")
        print("💡 Wait for ArgoCD to sync and pods to be running, then try again")

if __name__ == "__main__":
    main()
