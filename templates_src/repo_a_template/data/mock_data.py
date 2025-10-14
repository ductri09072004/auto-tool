"""
Mock data cho Demo FISS API
Chứa các dữ liệu giả để test API endpoints
"""

import datetime

def get_system_info():
    """Trả về thông tin hệ thống giả"""
    return {
        "system_info": {
            "name": "Demo FISS API v46",
            "version": "1.0.0",
            "environment": "development"
        },
        "server_status": "running",
        "uptime": "2 hours 15 minutes",
        "last_updated": datetime.datetime.now().isoformat()
    }

def get_user_profile():
    """Trả về thông tin người dùng giả"""
    return {
        "user_profile": {
            "id": 12345,
            "username": "demo_user",
            "email": "demo@example.com",
            "role": "admin"
        },
        "permissions": ["read", "write", "delete"],
        "last_login": "2024-01-15T10:30:00Z",
        "active_sessions": 3
    }

def get_products_data():
    """Trả về dữ liệu sản phẩm giả"""
    return {
        "products": [
            {
                "id": 1,
                "name": "Laptop Gaming",
                "price": 25000000,
                "category": "Electronics",
                "in_stock": True,
                "rating": 4.5
            },
            {
                "id": 2,
                "name": "Smartphone",
                "price": 12000000,
                "category": "Electronics",
                "in_stock": True,
                "rating": 4.2
            },
            {
                "id": 3,
                "name": "Headphones",
                "price": 2500000,
                "category": "Accessories",
                "in_stock": False,
                "rating": 4.8
            }
        ],
        "total_products": 3,
        "page": 1,
        "per_page": 10
    }

def get_orders_data():
    """Trả về dữ liệu đơn hàng giả"""
    return {
        "orders": [
            {
                "order_id": "ORD-001",
                "customer_name": "Nguyễn Văn A",
                "total_amount": 37500000,
                "status": "completed",
                "order_date": "2024-01-15T09:30:00Z"
            },
            {
                "order_id": "ORD-002",
                "customer_name": "Trần Thị B",
                "total_amount": 12000000,
                "status": "pending",
                "order_date": "2024-01-15T14:20:00Z"
            }
        ],
        "total_orders": 2,
        "total_revenue": 49500000
    }
