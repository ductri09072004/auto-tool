#!/usr/bin/env python3
"""
Virtual Git Service - Trung gian giữa ArgoCD và MongoDB
Expose các endpoint giống Git repository nhưng render từ MongoDB
"""

from flask import Flask, jsonify, Response
import yaml
import json
import os
from pymongo import MongoClient
from datetime import datetime

app = Flask(__name__)

# MongoDB connection
MONGO_URI = os.getenv('MONGO_URI', 'mongodb+srv://BlueDuck2:Fcsunny0907@tpexpress.zjf26.mongodb.net/?retryWrites=true&w=majority&appName=TPExpress')
MONGO_DB = os.getenv('MONGO_DB', 'AutoToolDevOPS')
client = MongoClient(MONGO_URI)
db = client[MONGO_DB]

def get_service_data(service_name):
    """Lấy data service từ MongoDB"""
    service = db.services.find_one({'name': service_name})
    return service

def render_namespace(service_data):
    """Render Namespace YAML"""
    return {
        'apiVersion': 'v1',
        'kind': 'Namespace',
        'metadata': {
            'name': service_data.get('namespace', service_data['name']),
            'labels': service_data.get('namespace_info', {}).get('labels', {})
        }
    }

def render_configmap(service_data):
    """Render ConfigMap YAML"""
    configmap_data = service_data.get('configmap', {})
    return {
        'apiVersion': 'v1',
        'kind': 'ConfigMap',
        'metadata': {
            'name': configmap_data.get('name', f"{service_data['name']}-config"),
            'namespace': service_data.get('namespace', service_data['name'])
        },
        'data': configmap_data.get('data', {})
    }

def render_secret(service_data):
    """Render Secret YAML"""
    secret_data = service_data.get('secret', {})
    return {
        'apiVersion': 'v1',
        'kind': 'Secret',
        'metadata': {
            'name': secret_data.get('name', f"{service_data['name']}-secret"),
            'namespace': service_data.get('namespace', service_data['name'])
        },
        'type': secret_data.get('type', 'Opaque'),
        'data': secret_data.get('data', {})
    }

def render_deployment(service_data):
    """Render Deployment YAML"""
    deployment_data = service_data.get('deployment', {})
    return {
        'apiVersion': 'apps/v1',
        'kind': 'Deployment',
        'metadata': {
            'name': deployment_data.get('name', service_data['name']),
            'namespace': service_data.get('namespace', service_data['name']),
            'labels': {'app': service_data['name']}
        },
        'spec': {
            'replicas': service_data.get('replicas', 3),
            'selector': {'matchLabels': {'app': service_data['name']}},
            'template': {
                'metadata': {'labels': {'app': service_data['name']}},
                'spec': {
                    'containers': [{
                        'name': service_data['name'],
                        'image': deployment_data.get('image', f"ghcr.io/ductri09072004/{service_data['name']}:latest"),
                        'ports': [{'containerPort': deployment_data.get('target_port', service_data.get('port', 5001))}],
                        'resources': {
                            'requests': {
                                'cpu': service_data.get('cpu_request', '100m'),
                                'memory': service_data.get('memory_request', '128Mi')
                            },
                            'limits': {
                                'cpu': service_data.get('cpu_limit', '200m'),
                                'memory': service_data.get('memory_limit', '256Mi')
                            }
                        },
                        'envFrom': [{'configMapRef': {'name': service_data.get('configmap', {}).get('name', f"{service_data['name']}-config")}}]
                    }]
                }
            }
        }
    }

def render_service(service_data):
    """Render Service YAML"""
    k8s_service_data = service_data.get('k8s_service', {})
    return {
        'apiVersion': 'v1',
        'kind': 'Service',
        'metadata': {
            'name': k8s_service_data.get('name', f"{service_data['name']}-service"),
            'namespace': service_data.get('namespace', service_data['name']),
            'labels': {'app': service_data['name']}
        },
        'spec': {
            'type': k8s_service_data.get('type', 'ClusterIP'),
            'selector': {'app': service_data['name']},
            'ports': [{
                'port': service_data.get('port', 5001),
                'targetPort': k8s_service_data.get('target_port', service_data.get('port', 5001)),
                'protocol': 'TCP'
            }]
        }
    }

def render_hpa(service_data):
    """Render HPA YAML"""
    hpa_data = service_data.get('hpa', {})
    deployment_data = service_data.get('deployment', {})
    return {
        'apiVersion': 'autoscaling/v2',
        'kind': 'HorizontalPodAutoscaler',
        'metadata': {
            'name': hpa_data.get('name', f"{service_data['name']}-hpa"),
            'namespace': service_data.get('namespace', service_data['name'])
        },
        'spec': {
            'scaleTargetRef': {
                'apiVersion': 'apps/v1',
                'kind': 'Deployment',
                'name': deployment_data.get('name', service_data['name'])
            },
            'minReplicas': service_data.get('min_replicas', 2),
            'maxReplicas': service_data.get('max_replicas', 10),
            'metrics': [{
                'type': 'Resource',
                'resource': {
                    'name': 'cpu',
                    'target': {
                        'type': 'Utilization',
                        'averageUtilization': hpa_data.get('target_cpu_utilization', 70)
                    }
                }
            }]
        }
    }

def render_ingress(service_data):
    """Render Ingress YAML"""
    ingress_data = service_data.get('ingress', {})
    k8s_service_data = service_data.get('k8s_service', {})
    return {
        'apiVersion': 'networking.k8s.io/v1',
        'kind': 'Ingress',
        'metadata': {
            'name': ingress_data.get('name', f"{service_data['name']}-ingress"),
            'namespace': service_data.get('namespace', service_data['name'])
        },
        'spec': {
            'rules': [{
                'host': ingress_data.get('host', f"{service_data['name']}.local"),
                'http': {
                    'paths': [{
                        'path': ingress_data.get('path', '/'),
                        'pathType': 'Prefix',
                        'backend': {
                            'service': {
                                'name': k8s_service_data.get('name', f"{service_data['name']}-service"),
                                'port': {'number': service_data.get('port', 5001)}
                            }
                        }
                    }]
                }
            }]
        }
    }

@app.route('/api/git/<service_name>/manifest.yaml')
def get_service_manifest(service_name):
    """Trả về tất cả manifests của service"""
    try:
        service_data = get_service_data(service_name)
        if not service_data:
            return jsonify({'error': f'Service {service_name} not found'}), 404
        
        # Render tất cả manifests
        manifests = []
        manifests.append(render_namespace(service_data))
        manifests.append(render_configmap(service_data))
        manifests.append(render_secret(service_data))
        manifests.append(render_deployment(service_data))
        manifests.append(render_service(service_data))
        manifests.append(render_hpa(service_data))
        manifests.append(render_ingress(service_data))
        
        # Tạo YAML output
        yaml_output = ""
        for manifest in manifests:
            yaml_output += "---\n"
            yaml_output += yaml.dump(manifest, default_flow_style=False)
        
        return Response(yaml_output, mimetype='text/yaml')
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/git/<service_name>/deployment.yaml')
def get_deployment(service_name):
    """Trả về Deployment YAML"""
    try:
        service_data = get_service_data(service_name)
        if not service_data:
            return jsonify({'error': f'Service {service_name} not found'}), 404
        
        deployment = render_deployment(service_data)
        yaml_output = yaml.dump(deployment, default_flow_style=False)
        return Response(yaml_output, mimetype='text/yaml')
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/git/<service_name>/service.yaml')
def get_service(service_name):
    """Trả về Service YAML"""
    try:
        service_data = get_service_data(service_name)
        if not service_data:
            return jsonify({'error': f'Service {service_name} not found'}), 404
        
        service = render_service(service_data)
        yaml_output = yaml.dump(service, default_flow_style=False)
        return Response(yaml_output, mimetype='text/yaml')
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/git/<service_name>/configmap.yaml')
def get_configmap(service_name):
    """Trả về ConfigMap YAML"""
    try:
        service_data = get_service_data(service_name)
        if not service_data:
            return jsonify({'error': f'Service {service_name} not found'}), 404
        
        configmap = render_configmap(service_data)
        yaml_output = yaml.dump(configmap, default_flow_style=False)
        return Response(yaml_output, mimetype='text/yaml')
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/git/<service_name>/hpa.yaml')
def get_hpa(service_name):
    """Trả về HPA YAML"""
    try:
        service_data = get_service_data(service_name)
        if not service_data:
            return jsonify({'error': f'Service {service_name} not found'}), 404
        
        hpa = render_hpa(service_data)
        yaml_output = yaml.dump(hpa, default_flow_style=False)
        return Response(yaml_output, mimetype='text/yaml')
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/git/<service_name>/ingress.yaml')
def get_ingress(service_name):
    """Trả về Ingress YAML"""
    try:
        service_data = get_service_data(service_name)
        if not service_data:
            return jsonify({'error': f'Service {service_name} not found'}), 404
        
        ingress = render_ingress(service_data)
        yaml_output = yaml.dump(ingress, default_flow_style=False)
        return Response(yaml_output, mimetype='text/yaml')
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/git/<service_name>/namespace.yaml')
def get_namespace(service_name):
    """Trả về Namespace YAML"""
    try:
        service_data = get_service_data(service_name)
        if not service_data:
            return jsonify({'error': f'Service {service_name} not found'}), 404
        
        namespace = render_namespace(service_data)
        yaml_output = yaml.dump(namespace, default_flow_style=False)
        return Response(yaml_output, mimetype='text/yaml')
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/git/<service_name>/secret.yaml')
def get_secret(service_name):
    """Trả về Secret YAML"""
    try:
        service_data = get_service_data(service_name)
        if not service_data:
            return jsonify({'error': f'Service {service_name} not found'}), 404
        
        secret = render_secret(service_data)
        yaml_output = yaml.dump(secret, default_flow_style=False)
        return Response(yaml_output, mimetype='text/yaml')
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})

@app.route('/')
def index():
    """Root endpoint - list available services"""
    try:
        services = list(db.services.find({}, {'name': 1, 'namespace': 1, 'created_at': 1}))
        service_list = []
        for service in services:
            service_list.append({
                'name': service['name'],
                'namespace': service.get('namespace', service['name']),
                'created_at': service.get('created_at'),
                'manifest_url': f'/api/git/{service["name"]}/manifest.yaml'
            })
        
        return jsonify({
            'message': 'Virtual Git Service - ArgoCD to MongoDB Bridge',
            'services': service_list,
            'endpoints': {
                'manifest': '/api/git/{service_name}/manifest.yaml',
                'deployment': '/api/git/{service_name}/deployment.yaml',
                'service': '/api/git/{service_name}/service.yaml',
                'configmap': '/api/git/{service_name}/configmap.yaml',
                'hpa': '/api/git/{service_name}/hpa.yaml',
                'ingress': '/api/git/{service_name}/ingress.yaml',
                'namespace': '/api/git/{service_name}/namespace.yaml',
                'secret': '/api/git/{service_name}/secret.yaml'
            }
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
