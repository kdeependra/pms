"""
Database migration to add RBAC tables
Run this script to add Role-Based Access Control tables to an existing database
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, ForeignKey, 
    Table as SQLTable, Text
)
from sqlalchemy.sql import func
from app.core.database import engine, Base
from app.models.models import Permission, Role, user_role_association, role_permission_association
import sys


def migrate_rbac():
    """Add RBAC tables to the database"""
    
    try:
        print("Creating RBAC tables...")
        
        # Create all tables defined in the models
        Base.metadata.create_all(bind=engine)
        
        print("✅ RBAC tables created successfully!")
        print("\nTables created:")
        print("  - permissions")
        print("  - roles")
        print("  - role_permissions (junction table)")
        print("  - user_roles (junction table)")
        
    except Exception as e:
        print(f"❌ Error creating RBAC tables: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    migrate_rbac()
