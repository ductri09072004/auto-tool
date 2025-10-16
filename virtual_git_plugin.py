#!/usr/bin/env python3
"""
Virtual Git Plugin for ArgoCD
Calls Virtual Git Service API to get manifests
"""

import sys
import yaml
import requests
import os

def emit(obj):
    """Emit YAML object to stdout"""
    sys.stdout.write(yaml.safe_dump(obj, default_flow_style=False))
    sys.stdout.write("---\n")

def get_manifest_from_virtual_git(service_name):
    """Get manifest from Virtual Git Service"""
    virtual_git_url = os.getenv('VIRTUAL_GIT_URL', 'http://virtual-git-service.virtual-git.svc.cluster.local:8050')
    manifest_url = f"{virtual_git_url}/api/git/{service_name}/manifest.yaml"
    
    try:
        response = requests.get(manifest_url, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Error fetching manifest: {e}", file=sys.stderr)
        return None

def main():
    """Main function"""
    # Get service name from environment or use demo-v94 as default
    service_name = os.getenv('SERVICE_NAME', 'demo-v94')
    
    print(f"Virtual Git Plugin: Getting manifest for {service_name}", file=sys.stderr)
    
    # Get manifest from Virtual Git Service
    manifest_yaml = get_manifest_from_virtual_git(service_name)
    
    if not manifest_yaml:
        # Emit empty list if no manifest
        emit({'apiVersion': 'v1', 'kind': 'List', 'items': []})
        return
    
    # Parse and emit individual YAML documents
    try:
        documents = list(yaml.safe_load_all(manifest_yaml))
        for doc in documents:
            if doc:  # Skip empty documents
                emit(doc)
    except Exception as e:
        print(f"Error parsing YAML: {e}", file=sys.stderr)
        emit({'apiVersion': 'v1', 'kind': 'List', 'items': []})

if __name__ == '__main__':
    main()
