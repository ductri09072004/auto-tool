"""
Service Management Database
Quản lý thông tin services trong database
"""
import sqlite3
import json
import os
from datetime import datetime

class ServiceManager:
    def __init__(self, db_path='services.db'):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Services table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                namespace TEXT NOT NULL,
                port INTEGER NOT NULL,
                description TEXT,
                repo_url TEXT,
                status TEXT DEFAULT 'active',
                health_status TEXT DEFAULT 'Unknown',
                sync_status TEXT DEFAULT 'Unknown',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            )
        ''')
        
        # Service events table (for audit trail)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS service_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_name TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_data TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (service_name) REFERENCES services (name)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_service(self, service_data):
        """Add a new service to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO services (name, namespace, port, description, repo_url, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                service_data['name'],
                service_data['namespace'],
                service_data['port'],
                service_data.get('description', ''),
                service_data.get('repo_url', ''),
                json.dumps(service_data.get('metadata', {}))
            ))
            
            # Log event
            cursor.execute('''
                INSERT INTO service_events (service_name, event_type, event_data)
                VALUES (?, ?, ?)
            ''', (
                service_data['name'],
                'created',
                json.dumps(service_data)
            ))
            
            conn.commit()
            return True
            
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def get_services(self, status=None):
        """Get all services or filter by status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if status:
            cursor.execute('SELECT * FROM services WHERE status = ? ORDER BY created_at DESC', (status,))
        else:
            cursor.execute('SELECT * FROM services ORDER BY created_at DESC')
        
        columns = [description[0] for description in cursor.description]
        services = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        return services
    
    def update_service_status(self, service_name, health_status=None, sync_status=None):
        """Update service status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        if health_status:
            updates.append('health_status = ?')
            params.append(health_status)
        
        if sync_status:
            updates.append('sync_status = ?')
            params.append(sync_status)
        
        if updates:
            updates.append('updated_at = CURRENT_TIMESTAMP')
            params.append(service_name)
            
            cursor.execute(f'''
                UPDATE services 
                SET {', '.join(updates)}
                WHERE name = ?
            ''', params)
            
            conn.commit()
        
        conn.close()
    
    def delete_service(self, service_name):
        """Delete service from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Log deletion event
        cursor.execute('''
            INSERT INTO service_events (service_name, event_type, event_data)
            VALUES (?, ?, ?)
        ''', (service_name, 'deleted', json.dumps({'timestamp': datetime.now().isoformat()})))
        
        # Delete service
        cursor.execute('DELETE FROM services WHERE name = ?', (service_name,))
        
        conn.commit()
        conn.close()
    
    def archive_service(self, service_name):
        """Archive a service"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE services 
            SET status = 'archived', updated_at = CURRENT_TIMESTAMP
            WHERE name = ?
        ''', (service_name,))
        
        # Log archive event
        cursor.execute('''
            INSERT INTO service_events (service_name, event_type, event_data)
            VALUES (?, ?, ?)
        ''', (service_name, 'archived', json.dumps({'timestamp': datetime.now().isoformat()})))
        
        conn.commit()
        conn.close()
    
    def get_service_events(self, service_name, limit=50):
        """Get service event history"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM service_events 
            WHERE service_name = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (service_name, limit))
        
        columns = [description[0] for description in cursor.description]
        events = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        return events
    
    def get_service_stats(self):
        """Get service statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Total services
        cursor.execute('SELECT COUNT(*) FROM services')
        total = cursor.fetchone()[0]
        
        # Active services
        cursor.execute('SELECT COUNT(*) FROM services WHERE status = "active"')
        active = cursor.fetchone()[0]
        
        # Healthy services
        cursor.execute('SELECT COUNT(*) FROM services WHERE health_status = "Healthy"')
        healthy = cursor.fetchone()[0]
        
        # Degraded services
        cursor.execute('SELECT COUNT(*) FROM services WHERE health_status = "Degraded"')
        degraded = cursor.fetchone()[0]
        
        # Archived services
        cursor.execute('SELECT COUNT(*) FROM services WHERE status = "archived"')
        archived = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total': total,
            'active': active,
            'healthy': healthy,
            'degraded': degraded,
            'archived': archived
        }
    
    def cleanup_old_services(self, days=30):
        """Cleanup old archived services"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Delete archived services older than specified days
        cursor.execute('''
            DELETE FROM services 
            WHERE status = 'archived' 
            AND updated_at < datetime('now', '-{} days')
        '''.format(days))
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        return deleted_count
