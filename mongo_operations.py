"""
MongoDB Operations for Service Management
Tách riêng các operations liên quan đến MongoDB
"""
import json
import os
import yaml
from datetime import datetime
from pymongo import MongoClient, ASCENDING, DESCENDING


class MongoOperations:
    def __init__(self, mongo_uri=None, mongo_db=None):
        self.mongo_uri = mongo_uri or os.environ.get('MONGO_URI', 'mongodb+srv://BlueDuck2:Fcsunny0907@tpexpress.zjf26.mongodb.net/?retryWrites=true&w=majority&appName=TPExpress')
        self.mongo_db_name = mongo_db or os.environ.get('MONGO_DB', 'AutoToolDevOPS')
        self.client = MongoClient(self.mongo_uri)
        self.db = self.client[self.mongo_db_name]
        self._ensure_indexes()

    def _ensure_indexes(self):
        try:
            self.db.services.create_index([('name', ASCENDING)], unique=True)
            self.db.service_events.create_index([('service_name', ASCENDING), ('timestamp', DESCENDING)])
        except Exception:
            pass

    def _substitute_placeholders(self, content, service_name, parsed_data):
        """Substitute placeholders in YAML content."""
        return content.replace('{SERVICE_NAME}', service_name) \
                     .replace('{NAMESPACE}', parsed_data['namespace']) \
                     .replace('{PORT}', str(parsed_data['port'])) \
                     .replace('{REPLICAS}', str(parsed_data['replicas'])) \
                     .replace('{MIN_REPLICAS}', str(parsed_data['min_replicas'])) \
                     .replace('{MAX_REPLICAS}', str(parsed_data['max_replicas'])) \
                     .replace('{CPU_REQUEST}', parsed_data['cpu_request']) \
                     .replace('{CPU_LIMIT}', parsed_data['cpu_limit']) \
                     .replace('{MEMORY_REQUEST}', parsed_data['memory_request']) \
                     .replace('{MEMORY_LIMIT}', parsed_data['memory_limit'])

    def parse_yaml_files(self, service_name, k8s_path, service_data=None):
        """Parse YAML files from k8s folder and extract data for MongoDB collections."""
        try:
            # Default values
            parsed_data = {
                'service_name': service_name,
                'namespace': service_name,
                'port': 5001,
                'target_port': 5001,
                'replicas': 3,
                'cpu_request': '100m',
                'cpu_limit': '200m',
                'memory_request': '128Mi',
                'memory_limit': '256Mi',
                'min_replicas': 2,
                'max_replicas': 10,
                'image': f"{service_name}:latest",
                'type': 'ClusterIP',
                'host': f"{service_name}.local",
                'path': '/',
                'data': {},
                'labels': {},
                'repo_url': '',
                'target_revision': 'HEAD',
                'destination_server': 'https://kubernetes.default.svc',
                'destination_namespace': service_name,
                'sync_policy': {
                    'automated': {
                        'prune': True,
                        'self_heal': True
                    }
                }
            }
            
            # Override with service_data if provided
            if service_data:
                parsed_data.update({
                    'namespace': service_data.get('namespace', service_name),
                    'port': service_data.get('port', 5001),
                    'target_port': service_data.get('port', 5001),
                    'replicas': service_data.get('replicas', 3),
                    'min_replicas': service_data.get('min_replicas', 2),
                    'max_replicas': service_data.get('max_replicas', 10),
                    'cpu_request': service_data.get('cpu_request', '100m'),
                    'cpu_limit': service_data.get('cpu_limit', '200m'),
                    'memory_request': service_data.get('memory_request', '128Mi'),
                    'memory_limit': service_data.get('memory_limit', '256Mi'),
                    'image': f"ghcr.io/ductri09072004/{service_name}:latest",
                    'data': {
                        'FLASK_ENV': 'production',
                        'PYTHONUNBUFFERED': '1',
                        'PORT': str(service_data.get('port', 5001))
                    },
                    'repo_url': service_data.get('repo_url', '')
                })
            
            # Parse deployment.yaml
            deployment_file = os.path.join(k8s_path, 'deployment.yaml')
            if os.path.exists(deployment_file):
                with open(deployment_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    content = self._substitute_placeholders(content, service_name, parsed_data)
                    deployment_data = yaml.safe_load(content)
                    if deployment_data:
                        spec = deployment_data.get('spec', {})
                        parsed_data['replicas'] = spec.get('replicas', 3)
                        
                        # Extract container info
                        template = spec.get('template', {})
                        containers = template.get('spec', {}).get('containers', [])
                        if containers:
                            container = containers[0]
                            parsed_data['image'] = container.get('image', f"{service_name}:latest")
                            
                            # Extract port
                            ports = container.get('ports', [])
                            if ports:
                                parsed_data['target_port'] = ports[0].get('containerPort', 5001)
                            
                            # Extract resources
                            resources = container.get('resources', {})
                            requests = resources.get('requests', {})
                            limits = resources.get('limits', {})
                            parsed_data['cpu_request'] = requests.get('cpu', '100m')
                            parsed_data['cpu_limit'] = limits.get('cpu', '200m')
                            parsed_data['memory_request'] = requests.get('memory', '128Mi')
                            parsed_data['memory_limit'] = limits.get('memory', '256Mi')
            
            # Parse service.yaml
            service_file = os.path.join(k8s_path, 'service.yaml')
            if os.path.exists(service_file):
                with open(service_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    content = self._substitute_placeholders(content, service_name, parsed_data)
                    service_data = yaml.safe_load(content)
                    if service_data:
                        spec = service_data.get('spec', {})
                        parsed_data['type'] = spec.get('type', 'ClusterIP')
                        
                        # Extract port
                        ports = spec.get('ports', [])
                        if ports:
                            parsed_data['port'] = ports[0].get('port', 5001)
                            parsed_data['target_port'] = ports[0].get('targetPort', 5001)
            
            # Parse configmap.yaml
            configmap_file = os.path.join(k8s_path, 'configmap.yaml')
            if os.path.exists(configmap_file):
                with open(configmap_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    content = self._substitute_placeholders(content, service_name, parsed_data)
                    configmap_data = yaml.safe_load(content)
                    if configmap_data:
                        parsed_data['data'] = configmap_data.get('data', {})
                        # Extract PORT from configmap
                        if 'PORT' in parsed_data['data']:
                            parsed_data['port'] = int(parsed_data['data']['PORT'])
                            parsed_data['target_port'] = int(parsed_data['data']['PORT'])
            
            # Parse hpa.yaml
            hpa_file = os.path.join(k8s_path, 'hpa.yaml')
            if os.path.exists(hpa_file):
                with open(hpa_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    content = self._substitute_placeholders(content, service_name, parsed_data)
                    hpa_data = yaml.safe_load(content)
                    if hpa_data:
                        spec = hpa_data.get('spec', {})
                        parsed_data['min_replicas'] = spec.get('minReplicas', 2)
                        parsed_data['max_replicas'] = spec.get('maxReplicas', 10)
            
            # Parse ingress.yaml
            ingress_file = os.path.join(k8s_path, 'ingress.yaml')
            if os.path.exists(ingress_file):
                with open(ingress_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    content = self._substitute_placeholders(content, service_name, parsed_data)
                    ingress_data = yaml.safe_load(content)
                    if ingress_data:
                        spec = ingress_data.get('spec', {})
                        rules = spec.get('rules', [])
                        if rules:
                            rule = rules[0]
                            parsed_data['host'] = rule.get('host', f"{service_name}.local")
                            http = rule.get('http', {})
                            paths = http.get('paths', [])
                            if paths:
                                parsed_data['path'] = paths[0].get('path', '/')
            
            # Parse namespace.yaml
            namespace_file = os.path.join(k8s_path, 'namespace.yaml')
            if os.path.exists(namespace_file):
                with open(namespace_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    content = self._substitute_placeholders(content, service_name, parsed_data)
                    namespace_data = yaml.safe_load(content)
                    if namespace_data:
                        parsed_data['namespace'] = namespace_data.get('metadata', {}).get('name', service_name)
                        parsed_data['labels'] = namespace_data.get('metadata', {}).get('labels', {})
            
            # Parse argocd-application.yaml
            argocd_file = os.path.join(k8s_path, 'argocd-application.yaml')
            if os.path.exists(argocd_file):
                with open(argocd_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    content = self._substitute_placeholders(content, service_name, parsed_data)
                    argocd_data = yaml.safe_load(content)
                    if argocd_data:
                        spec = argocd_data.get('spec', {})
                        source = spec.get('source', {})
                        destination = spec.get('destination', {})
                        parsed_data['repo_url'] = source.get('repoURL', '')
                        parsed_data['target_revision'] = source.get('targetRevision', 'HEAD')
                        parsed_data['destination_server'] = destination.get('server', 'https://kubernetes.default.svc')
                        parsed_data['destination_namespace'] = destination.get('namespace', service_name)
                        parsed_data['sync_policy'] = spec.get('syncPolicy', parsed_data['sync_policy'])
            
            return parsed_data
            
        except Exception as e:
            print(f"Error parsing YAML files for {service_name}: {e}")
            return None

    def add_service_from_yaml(self, service_name, k8s_path, repo_url=''):
        """Add service to all collections by parsing YAML files from k8s folder."""
        try:
            # Parse YAML files
            parsed_data = self.parse_yaml_files(service_name, k8s_path)
            if not parsed_data:
                return False
            
            # Add repo_url if provided
            if repo_url:
                parsed_data['repo_url'] = repo_url
            
            timestamp = datetime.utcnow().isoformat()
            
            # 1. Add to services collection
            service_doc = {
                'name': service_name,
                'namespace': parsed_data['namespace'],
                'port': parsed_data['port'],
                'description': f'Demo service {service_name}',
                'repo_url': parsed_data['repo_url'],
                'replicas': parsed_data['replicas'],
                'min_replicas': parsed_data['min_replicas'],
                'max_replicas': parsed_data['max_replicas'],
                'cpu_request': parsed_data['cpu_request'],
                'cpu_limit': parsed_data['cpu_limit'],
                'memory_request': parsed_data['memory_request'],
                'memory_limit': parsed_data['memory_limit'],
                'metadata': {
                    'created_by': 'yaml_parser',
                    'source': 'k8s_files',
                    'k8s_path': k8s_path
                },
                'created_at': timestamp,
                'updated_at': timestamp
            }
            self.db.services.update_one({'name': service_name}, {'$set': service_doc}, upsert=True)
            
            # 2. Add to service_events collection
            self.db.service_events.insert_one({
                'service_name': service_name,
                'event_type': 'created_from_yaml',
                'event_data': service_doc,
                'timestamp': timestamp
            })
            
            # 3. Add to deployments collection
            deployment_doc = {
                'service_name': service_name,
                'name': service_name,
                'namespace': parsed_data['namespace'],
                'replicas': parsed_data['replicas'],
                'image': parsed_data['image'],
                'port': parsed_data['target_port'],
                'cpu_request': parsed_data['cpu_request'],
                'cpu_limit': parsed_data['cpu_limit'],
                'memory_request': parsed_data['memory_request'],
                'memory_limit': parsed_data['memory_limit'],
                'created_at': timestamp,
                'updated_at': timestamp
            }
            self.db.deployments.update_one({'name': service_name}, {'$set': deployment_doc}, upsert=True)
            
            # 4. Add to k8s_services collection
            k8s_service_doc = {
                'service_name': service_name,
                'name': f"{service_name}-service",
                'namespace': parsed_data['namespace'],
                'port': parsed_data['port'],
                'target_port': parsed_data['target_port'],
                'type': parsed_data['type'],
                'created_at': timestamp,
                'updated_at': timestamp
            }
            self.db.k8s_services.update_one({'name': f"{service_name}-service"}, {'$set': k8s_service_doc}, upsert=True)
            
            # 5. Add to configmaps collection
            configmap_doc = {
                'service_name': service_name,
                'name': f"{service_name}-config",
                'namespace': parsed_data['namespace'],
                'data': parsed_data['data'],
                'created_at': timestamp,
                'updated_at': timestamp
            }
            self.db.configmaps.update_one({'name': f"{service_name}-config"}, {'$set': configmap_doc}, upsert=True)
            
            # 6. Add to hpas collection
            hpa_doc = {
                'service_name': service_name,
                'name': f"{service_name}-hpa",
                'namespace': parsed_data['namespace'],
                'min_replicas': parsed_data['min_replicas'],
                'max_replicas': parsed_data['max_replicas'],
                'target_cpu_utilization': 70,
                'created_at': timestamp,
                'updated_at': timestamp
            }
            self.db.hpas.update_one({'name': f"{service_name}-hpa"}, {'$set': hpa_doc}, upsert=True)
            
            # 7. Add to ingresses collection
            ingress_doc = {
                'service_name': service_name,
                'name': f"{service_name}-ingress",
                'namespace': parsed_data['namespace'],
                'host': parsed_data['host'],
                'path': parsed_data['path'],
                'service_name': f"{service_name}-service",
                'service_port': parsed_data['port'],
                'created_at': timestamp,
                'updated_at': timestamp
            }
            self.db.ingresses.update_one({'name': f"{service_name}-ingress"}, {'$set': ingress_doc}, upsert=True)
            
            # 8. Add to namespaces collection
            namespace_doc = {
                'service_name': service_name,
                'name': parsed_data['namespace'],
                'labels': parsed_data['labels'],
                'created_at': timestamp,
                'updated_at': timestamp
            }
            self.db.namespaces.update_one({'name': parsed_data['namespace']}, {'$set': namespace_doc}, upsert=True)
            
            # 9. Add to secrets collection
            secret_doc = {
                'service_name': service_name,
                'name': f"{service_name}-secret",
                'namespace': parsed_data['namespace'],
                'type': 'Opaque',
                'data': {},
                'created_at': timestamp,
                'updated_at': timestamp
            }
            self.db.secrets.update_one({'name': f"{service_name}-secret"}, {'$set': secret_doc}, upsert=True)
            
            # 10. Add to argocd_applications collection
            argocd_app_doc = {
                'service_name': service_name,
                'name': service_name,
                'namespace': 'argocd',
                'project': 'default',
                'repo_url': parsed_data['repo_url'],
                'target_revision': parsed_data['target_revision'],
                'path': f"services/{service_name}/k8s",
                'destination_server': parsed_data['destination_server'],
                'destination_namespace': parsed_data['destination_namespace'],
                'sync_policy': parsed_data['sync_policy'],
                'created_at': timestamp,
                'updated_at': timestamp
            }
            self.db.argocd_applications.update_one({'name': service_name}, {'$set': argocd_app_doc}, upsert=True)
            
            # 11. Add to manifest_versions collection
            manifest_version_doc = {
                'service_name': service_name,
                'version': 1,
                'manifest_type': 'deployment',
                'content': json.dumps(deployment_doc),
                'created_at': timestamp,
                'updated_at': timestamp
            }
            self.db.manifest_versions.insert_one(manifest_version_doc)
            
            return True
        except Exception as e:
            print(f"Error adding service from YAML: {e}")
            return False

    def add_service_complete(self, service_data):
        """Add service to single services collection with all information."""
        try:
            service_name = service_data.get('name') or service_data.get('service_name')
            if not service_name:
                print(f"ERROR: No service name in data: {service_data}")
                return False
            
            print(f"DEBUG: add_service_complete called for {service_name}")
            
            timestamp = datetime.utcnow().isoformat()
            
            # Create complete service document with all information
            service_doc = {
                'name': service_name,
                'namespace': service_data.get('namespace', service_name),
                'port': service_data.get('port', 5001),
                'description': service_data.get('description', f'Demo service {service_name}'),
                'repo_url': service_data.get('repo_url', ''),
                'replicas': service_data.get('replicas', 3),
                'min_replicas': service_data.get('min_replicas', 2),
                'max_replicas': service_data.get('max_replicas', 10),
                'cpu_request': service_data.get('cpu_request', '100m'),
                'cpu_limit': service_data.get('cpu_limit', '200m'),
                'memory_request': service_data.get('memory_request', '128Mi'),
                'memory_limit': service_data.get('memory_limit', '256Mi'),
                
                # Deployment info
                'deployment': {
                    'name': service_name,
                    'image': f"ghcr.io/ductri09072004/{service_name}:latest",
                    'target_port': service_data.get('port', 5001)
                },
                
                # K8s Service info
                'k8s_service': {
                    'name': f"{service_name}-service",
                    'type': 'ClusterIP',
                    'target_port': service_data.get('port', 5001)
                },
                
                # ConfigMap info
                'configmap': {
                    'name': f"{service_name}-config",
                    'data': {
                        'FLASK_ENV': 'production',
                        'PYTHONUNBUFFERED': '1',
                        'PORT': str(service_data.get('port', 5001))
                    }
                },
                
                # HPA info
                'hpa': {
                    'name': f"{service_name}-hpa",
                    'target_cpu_utilization': 70
                },
                
                # Ingress info
                'ingress': {
                    'name': f"{service_name}-ingress",
                    'host': f"{service_name}.local",
                    'path': '/'
                },
                
                # Namespace info
                'namespace_info': {
                    'labels': {
                        'app': service_name,
                        'managed-by': 'dev-portal'
                    }
                },
                
                # Secret info
                'secret': {
                    'name': f"{service_name}-secret",
                    'type': 'Opaque',
                    'data': {}
                },
                
                # ArgoCD Application info
                'argocd_application': {
                    'name': service_name,
                    'namespace': 'argocd',
                    'project': 'default',
                    'target_revision': 'HEAD',
                    'path': f"services/{service_name}/k8s",
                    'destination_server': 'https://kubernetes.default.svc',
                    'destination_namespace': service_data.get('namespace', service_name),
                    'sync_policy': {
                        'automated': {
                            'prune': True,
                            'self_heal': True
                        }
                    }
                },
                
                # Metadata
                'metadata': service_data.get('metadata', {
                    'created_by': 'portal',
                    'template': 'repo_a_template'
                }),
                'created_at': timestamp,
                'updated_at': timestamp
            }
            
            # Insert/Update in services collection
            self.db.services.update_one({'name': service_name}, {'$set': service_doc}, upsert=True)
            
            # Add to service_events collection for logging
            self.db.service_events.insert_one({
                'service_name': service_name,
                'event_type': 'created',
                'event_data': service_doc,
                'timestamp': timestamp
            })
            
            # Add to manifest_versions collection
            self.db.manifest_versions.insert_one({
                'service_name': service_name,
                'version': 1,
                'manifest_type': 'deployment',
                'content': json.dumps(service_doc['deployment']),
                'created_at': timestamp,
                'updated_at': timestamp
            })
            
            print(f"DEBUG: Successfully added {service_name} to services collection")
            return True
        except Exception as e:
            print(f"ERROR: Failed to add service to services collection: {e}")
            import traceback
            traceback.print_exc()
            return False

    def delete_service_from_all_collections(self, service_name):
        """Delete service from all collections."""
        try:
            # Delete from all collections
            collections_to_clean = [
                'services', 'service_events', 'deployments', 'k8s_services', 
                'configmaps', 'hpas', 'ingresses', 'namespaces', 'secrets', 
                'argocd_applications', 'manifest_versions'
            ]
            
            for collection_name in collections_to_clean:
                collection = getattr(self.db, collection_name)
                if collection_name == 'services':
                    collection.delete_one({'name': service_name})
                elif collection_name == 'service_events':
                    collection.delete_many({'service_name': service_name})
                elif collection_name == 'manifest_versions':
                    collection.delete_many({'service_name': service_name})
                else:
                    # For other collections, delete by service_name field
                    collection.delete_many({'service_name': service_name})
            
            return True
        except Exception as e:
            print(f"Error deleting service from all collections: {e}")
            return False

    def get_collection_stats(self):
        """Get statistics for all collections."""
        try:
            stats = {}
            collections = [
                'services', 'service_events', 'deployments', 'k8s_services', 
                'configmaps', 'hpas', 'ingresses', 'namespaces', 'secrets', 
                'argocd_applications', 'manifest_versions'
            ]
            
            for collection_name in collections:
                collection = getattr(self.db, collection_name)
                stats[collection_name] = collection.count_documents({})
            
            return stats
        except Exception as e:
            print(f"Error getting collection stats: {e}")
            return {}
