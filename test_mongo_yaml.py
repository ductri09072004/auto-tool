#!/usr/bin/env python3
"""
Test script for MongoDB YAML template generation
"""
import requests
import json

def test_generate_yaml(service_name):
    """Test generating YAML templates from MongoDB"""
    
    base_url = "http://localhost:3050"
    
    print(f"Testing YAML generation for service: {service_name}")
    print("=" * 50)
    
    # 1. Generate YAML templates
    print("1. Generating YAML templates from MongoDB...")
    try:
        response = requests.post(f"{base_url}/api/services/{service_name}/generate-yaml")
        result = response.json()
        
        if result.get('success'):
            print(f"✅ YAML generation successful: {result.get('message')}")
        else:
            print(f"❌ YAML generation failed: {result.get('error')}")
            return False
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return False
    
    # 2. Get generated templates
    print("\n2. Retrieving generated YAML templates...")
    try:
        response = requests.get(f"{base_url}/api/services/{service_name}/yaml-templates")
        result = response.json()
        
        if result.get('success'):
            templates = result.get('templates', [])
            print(f"✅ Found {len(templates)} YAML templates:")
            
            for template in templates:
                template_type = template.get('template_type')
                created_at = template.get('created_at')
                print(f"   - {template_type} (created: {created_at})")
                
                # Show first few lines of YAML content
                yaml_content = template.get('yaml_content', '')
                lines = yaml_content.split('\n')[:5]
                print(f"     Preview: {' '.join(lines)}")
                print()
        else:
            print(f"❌ Failed to get templates: {result.get('error')}")
            return False
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return False
    
    # 3. Test deletion
    print("3. Testing YAML template deletion...")
    try:
        response = requests.delete(f"{base_url}/api/services/{service_name}/delete-yaml-templates")
        result = response.json()
        
        if result.get('success'):
            deleted_count = result.get('deleted_count', 0)
            print(f"✅ Deleted {deleted_count} YAML templates")
        else:
            print(f"❌ Deletion failed: {result.get('error')}")
    except Exception as e:
        print(f"❌ Request failed: {e}")
    
    return True

def test_service_creation_flow():
    """Test complete service creation flow with YAML generation"""
    
    print("Testing complete service creation flow...")
    print("=" * 50)
    
    # This would be a full test of creating a service and generating YAML
    # For now, just show the endpoints available
    
    endpoints = [
        "POST /api/services/{service_name}/generate-yaml",
        "GET /api/services/{service_name}/yaml-templates", 
        "DELETE /api/services/{service_name}/delete-yaml-templates"
    ]
    
    print("Available YAML template endpoints:")
    for endpoint in endpoints:
        print(f"  {endpoint}")
    
    print("\nExample usage:")
    print("  curl -X POST http://localhost:3050/api/services/demo-v108/generate-yaml")
    print("  curl -X GET http://localhost:3050/api/services/demo-v108/yaml-templates")
    print("  curl -X DELETE http://localhost:3050/api/services/demo-v108/delete-yaml-templates")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python test_mongo_yaml.py <service_name>")
        print("Example: python test_mongo_yaml.py demo-v108")
        sys.exit(1)
    
    service_name = sys.argv[1]
    
    print(f"🧪 Testing MongoDB YAML generation for: {service_name}")
    print("=" * 60)
    
    # Test YAML generation
    success = test_generate_yaml(service_name)
    
    if success:
        print("\n✅ All tests completed successfully!")
    else:
        print("\n❌ Some tests failed!")
    
    # Show complete flow
    print("\n" + "=" * 60)
    test_service_creation_flow()
