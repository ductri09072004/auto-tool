#!/usr/bin/env python3
"""
Test script for GitHub tokens in Auto Project Tool
Tests all three token types: GITHUB_TOKEN, GHCR_TOKEN, MANIFESTS_REPO_TOKEN
"""

import requests
import json
from config import GITHUB_TOKEN, GHCR_TOKEN, MANIFESTS_REPO_TOKEN, validate_tokens

def test_github_token(token, token_name):
    """Test GitHub token by making API call"""
    try:
        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # Test with user API
        response = requests.get('https://api.github.com/user', headers=headers)
        
        if response.status_code == 200:
            user_data = response.json()
            print(f"✅ {token_name}: Valid (User: {user_data.get('login', 'Unknown')})")
            return True
        else:
            print(f"❌ {token_name}: Invalid (Status: {response.status_code})")
            return False
            
    except Exception as e:
        print(f"❌ {token_name}: Error - {e}")
        return False

def test_ghcr_token(token, token_name):
    """Test GHCR token by checking package access"""
    try:
        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # Test with packages API
        response = requests.get('https://api.github.com/user/packages', headers=headers)
        
        if response.status_code == 200:
            print(f"✅ {token_name}: Valid (Can access packages)")
            return True
        elif response.status_code == 404:
            print(f"⚠️ {token_name}: Valid but no packages found")
            return True
        else:
            print(f"❌ {token_name}: Invalid (Status: {response.status_code})")
            return False
            
    except Exception as e:
        print(f"❌ {token_name}: Error - {e}")
        return False

def test_manifests_token(token, token_name):
    """Test manifests token by checking repository access"""
    try:
        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # Test with repositories API
        response = requests.get('https://api.github.com/user/repos', headers=headers)
        
        if response.status_code == 200:
            repos = response.json()
            print(f"✅ {token_name}: Valid (Access to {len(repos)} repositories)")
            return True
        else:
            print(f"❌ {token_name}: Invalid (Status: {response.status_code})")
            return False
            
    except Exception as e:
        print(f"❌ {token_name}: Error - {e}")
        return False

def main():
    """Main test function"""
    print("🔧 GitHub Tokens Test for Auto Project Tool")
    print("=" * 60)
    
    # Validate configuration
    print("\n📋 Configuration Validation:")
    validate_tokens()
    
    print("\n🧪 Token Testing:")
    print("-" * 30)
    
    # Test all tokens
    tokens_to_test = [
        (GITHUB_TOKEN, "GITHUB_TOKEN", test_github_token),
        (GHCR_TOKEN, "GHCR_TOKEN", test_ghcr_token),
        (MANIFESTS_REPO_TOKEN, "MANIFESTS_REPO_TOKEN", test_manifests_token)
    ]
    
    results = []
    for token, name, test_func in tokens_to_test:
        result = test_func(token, name)
        results.append((name, result))
    
    print("\n📊 Test Results Summary:")
    print("-" * 30)
    
    passed = 0
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{name}: {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 Overall: {passed}/{len(results)} tokens working")
    
    if passed == len(results):
        print("🎉 All tokens are working correctly!")
        print("✅ Auto Project Tool is ready to use")
    else:
        print("⚠️ Some tokens need attention")
        print("💡 Check token permissions and validity")
    
    print("\n📚 Token Usage Guide:")
    print("- GITHUB_TOKEN: General GitHub operations (create repos, push code)")
    print("- GHCR_TOKEN: Container registry operations (push/pull Docker images)")
    print("- MANIFESTS_REPO_TOKEN: Repository B operations (push K8s manifests)")

if __name__ == "__main__":
    main()
