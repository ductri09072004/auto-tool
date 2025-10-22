import requests

token = "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"
headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github+json'}

# Test user info
print("Testing token...")
response = requests.get('https://api.github.com/user', headers=headers)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    user = response.json()
    print(f"User: {user.get('login')}")
    print(f"Scopes: {response.headers.get('X-OAuth-Scopes', 'None')}")
else:
    print(f"Error: {response.text}")
