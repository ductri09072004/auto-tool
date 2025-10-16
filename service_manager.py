"""
Service Management Database (MongoDB)
Quản lý thông tin services trong MongoDB
"""
import json
import os
from datetime import datetime
from pymongo import MongoClient, ASCENDING, DESCENDING
from mongo_operations import MongoOperations


class ServiceManager:
    def __init__(self, mongo_uri=None, mongo_db=None):
        self.mongo_uri = mongo_uri or os.environ.get('MONGO_URI', 'mongodb+srv://BlueDuck2:Fcsunny0907@tpexpress.zjf26.mongodb.net/?retryWrites=true&w=majority&appName=TPExpress')
        self.mongo_db_name = mongo_db or os.environ.get('MONGO_DB', 'AutoToolDevOPS')
        self.client = MongoClient(self.mongo_uri)
        self.db = self.client[self.mongo_db_name]
        self.mongo_ops = MongoOperations(mongo_uri, mongo_db)
        self._ensure_indexes()

    def _ensure_indexes(self):
        try:
            self.db.services.create_index([('name', ASCENDING)], unique=True)
            self.db.service_events.create_index([('service_name', ASCENDING), ('timestamp', DESCENDING)])
        except Exception:
            pass

    # === High-level services ===
    def add_service(self, service_data):
        """Add or upsert a service document."""
        try:
            doc = dict(service_data)
            doc['updated_at'] = doc.get('updated_at') or datetime.utcnow().isoformat()
            doc['created_at'] = doc.get('created_at') or datetime.utcnow().isoformat()
            # Normalize metadata to dict
            if isinstance(doc.get('metadata'), str):
                try:
                    doc['metadata'] = json.loads(doc['metadata'])
                except Exception:
                    doc['metadata'] = {}
            self.db.services.update_one({'name': doc['name']}, {'$set': doc}, upsert=True)
            # Log event
            self.db.service_events.insert_one({
                'service_name': doc['name'],
                'event_type': 'created',
                'event_data': doc,
                'timestamp': datetime.utcnow().isoformat()
            })
            return True
        except Exception:
            return False

    def parse_yaml_files(self, service_name, k8s_path):
        """Parse YAML files from k8s folder and extract data for MongoDB collections."""
        return self.mongo_ops.parse_yaml_files(service_name, k8s_path)

    def add_service_from_yaml(self, service_name, k8s_path, repo_url=''):
        """Add service to all collections by parsing YAML files from k8s folder."""
        return self.mongo_ops.add_service_from_yaml(service_name, k8s_path, repo_url)

    def add_service_complete(self, service_data):
        """Add service to all collections (services, deployments, k8s_services, configmaps, hpas, ingresses, namespaces, secrets, argocd_applications, manifest_versions)."""
        return self.mongo_ops.add_service_complete(service_data)

    def delete_service_from_all_collections(self, service_name):
        """Delete service from all collections."""
        return self.mongo_ops.delete_service_from_all_collections(service_name)

    def get_collection_stats(self):
        """Get statistics for all collections."""
        return self.mongo_ops.get_collection_stats()

    def get_services(self, status=None):
        """Get all services or filter by status."""
        query = {}
        if status:
            query['status'] = status
        services = list(self.db.services.find(query, {'_id': 0}))
        return services

    def update_service_status(self, service_name, health_status=None, sync_status=None):
        """Update service status fields."""
        updates = {}
        if health_status:
            updates['health_status'] = health_status
        if sync_status:
            updates['sync_status'] = sync_status
        if updates:
            updates['updated_at'] = datetime.utcnow().isoformat()
            self.db.services.update_one({'name': service_name}, {'$set': updates})

    def delete_service(self, service_name):
        """Delete a service document and log event."""
        try:
            self.db.service_events.insert_one({
                'service_name': service_name,
                'event_type': 'deleted',
                'event_data': {'timestamp': datetime.utcnow().isoformat()},
                'timestamp': datetime.utcnow().isoformat()
            })
            self.db.services.delete_one({'name': service_name})
        except Exception:
            pass

    def archive_service(self, service_name):
        """Archive a service (status=archived)."""
        self.db.services.update_one(
            {'name': service_name},
            {'$set': {'status': 'archived', 'updated_at': datetime.utcnow().isoformat()}}
        )
        self.db.service_events.insert_one({
            'service_name': service_name,
            'event_type': 'archived',
            'event_data': {'timestamp': datetime.utcnow().isoformat()},
            'timestamp': datetime.utcnow().isoformat()
        })

    def get_service_events(self, service_name, limit=50):
        """Get service event history."""
        docs = list(self.db.service_events.find({'service_name': service_name}, {'_id': 0})
                    .sort('timestamp', DESCENDING)
                    .limit(int(limit)))
        return docs

    def get_service_stats(self):
        """Get service statistics."""
        total = self.db.services.count_documents({})
        active = self.db.services.count_documents({'status': 'active'})
        healthy = self.db.services.count_documents({'health_status': 'Healthy'})
        degraded = self.db.services.count_documents({'health_status': 'Degraded'})
        archived = self.db.services.count_documents({'status': 'archived'})
        return {
            'total': total,
            'active': active,
            'healthy': healthy,
            'degraded': degraded,
            'archived': archived
        }

    def cleanup_old_services(self, days=30):
        """No-op for Mongo; implement TTL via indexes if needed."""
        return 0

    # === Raw collection getters for API (/api/db/<collection>) ===
    def get_deployments(self):
        return list(self.db.deployments.find({}, {'_id': 0}))

    def get_k8s_services(self):
        return list(self.db.k8s_services.find({}, {'_id': 0}))

    def get_configmaps(self):
        return list(self.db.configmaps.find({}, {'_id': 0}))

    def get_hpas(self):
        return list(self.db.hpas.find({}, {'_id': 0}))

    def get_ingresses(self):
        return list(self.db.ingresses.find({}, {'_id': 0}))

    def get_namespaces(self):
        return list(self.db.namespaces.find({}, {'_id': 0}))

    def get_secrets(self):
        return list(self.db.secrets.find({}, {'_id': 0}))

    def get_argocd_applications(self):
        return list(self.db.argocd_applications.find({}, {'_id': 0}))

    def get_manifest_versions(self):
        return list(self.db.manifest_versions.find({}, {'_id': 0}))
