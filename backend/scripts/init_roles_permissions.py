"""
Initialize RBAC System with Roles and Permissions
This script creates system roles, permissions, and assigns all roles to admin user
"""

import sys
import os
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.models.models import Base, User, Role, Permission


# Database setup
DATABASE_URL = "sqlite:///./pms_dev.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_permissions(db: Session):
    """Initialize system permissions"""
    print("\n[*] Initializing Permissions...")
    
    permissions_data = [
        # Project Permissions
        {"name": "projects.create", "resource": "projects", "action": "create", "category": "general", "description": "Create new projects"},
        {"name": "projects.read", "resource": "projects", "action": "read", "category": "general", "description": "View projects"},
        {"name": "projects.update", "resource": "projects", "action": "update", "category": "general", "description": "Update projects"},
        {"name": "projects.delete", "resource": "projects", "action": "delete", "category": "general", "description": "Delete projects"},
        
        # Task Permissions
        {"name": "tasks.create", "resource": "tasks", "action": "create", "category": "general", "description": "Create new tasks"},
        {"name": "tasks.read", "resource": "tasks", "action": "read", "category": "general", "description": "View tasks"},
        {"name": "tasks.update", "resource": "tasks", "action": "update", "category": "general", "description": "Update tasks"},
        {"name": "tasks.delete", "resource": "tasks", "action": "delete", "category": "general", "description": "Delete tasks"},
        {"name": "tasks.assign", "resource": "tasks", "action": "assign", "category": "general", "description": "Assign tasks to users"},
        
        # User Permissions
        {"name": "users.create", "resource": "users", "action": "create", "category": "admin", "description": "Create new users"},
        {"name": "users.read", "resource": "users", "action": "read", "category": "general", "description": "View users"},
        {"name": "users.update", "resource": "users", "action": "update", "category": "admin", "description": "Update users"},
        {"name": "users.delete", "resource": "users", "action": "delete", "category": "admin", "description": "Delete users"},
        
        # Role Permissions
        {"name": "roles.create", "resource": "roles", "action": "create", "category": "admin", "description": "Create roles"},
        {"name": "roles.read", "resource": "roles", "action": "read", "category": "admin", "description": "View roles"},
        {"name": "roles.update", "resource": "roles", "action": "update", "category": "admin", "description": "Update roles"},
        {"name": "roles.delete", "resource": "roles", "action": "delete", "category": "admin", "description": "Delete roles"},
        {"name": "roles.assign", "resource": "roles", "action": "assign", "category": "admin", "description": "Assign roles to users"},
        
        # Resource Permissions
        {"name": "resources.create", "resource": "resources", "action": "create", "category": "resource", "description": "Create resources"},
        {"name": "resources.read", "resource": "resources", "action": "read", "category": "resource", "description": "View resources"},
        {"name": "resources.update", "resource": "resources", "action": "update", "category": "resource", "description": "Update resources"},
        {"name": "resources.allocate", "resource": "resources", "action": "allocate", "category": "resource", "description": "Allocate resources"},
        
        # Approval Permissions
        {"name": "approvals.approve", "resource": "approvals", "action": "approve", "category": "approval", "description": "Approve requests"},
        {"name": "approvals.reject", "resource": "approvals", "action": "reject", "category": "approval", "description": "Reject requests"},
        
        # System Permissions
        {"name": "system.configure", "resource": "system", "action": "configure", "category": "admin", "description": "Configure system settings"},
        {"name": "system.backup", "resource": "system", "action": "backup", "category": "admin", "description": "Backup system data"},
        {"name": "system.restore", "resource": "system", "action": "restore", "category": "admin", "description": "Restore system data"},
        
        # Report Permissions
        {"name": "reports.read", "resource": "reports", "action": "read", "category": "general", "description": "View reports"},
        {"name": "reports.export", "resource": "reports", "action": "export", "category": "general", "description": "Export reports"},
    ]
    
    created_count = 0
    for perm_data in permissions_data:
        existing = db.query(Permission).filter(Permission.name == perm_data["name"]).first()
        if not existing:
            permission = Permission(**perm_data)
            db.add(permission)
            created_count += 1
            print(f"  [+] Created permission: {perm_data['name']}")
    
    db.commit()
    print(f"[✓] Created {created_count} new permissions")
    return db.query(Permission).all()


def init_roles(db: Session, permissions):
    """Initialize system roles with appropriate permissions"""
    print("\n[*] Initializing Roles...")
    
    # Create a permission lookup
    perm_lookup = {p.name: p for p in permissions}
    
    roles_data = [
        {
            "name": "Admin",
            "description": "Full system access with all permissions",
            "is_system_role": True,
            "permissions": [p.name for p in permissions]  # All permissions
        },
        {
            "name": "Project Manager",
            "description": "Manage projects, tasks, and team resources",
            "is_system_role": True,
            "permissions": [
                "projects.create", "projects.read", "projects.update",
                "tasks.create", "tasks.read", "tasks.update", "tasks.assign",
                "users.read", "resources.read", "resources.allocate",
                "approvals.approve", "approvals.reject",
                "reports.read", "reports.export"
            ]
        },
        {
            "name": "Resource Manager",
            "description": "Manage resources and allocations",
            "is_system_role": True,
            "permissions": [
                "projects.read", "tasks.read",
                "resources.create", "resources.read", "resources.update", "resources.allocate",
                "users.read", "reports.read"
            ]
        },
        {
            "name": "Team Member",
            "description": "View projects and update assigned tasks",
            "is_system_role": True,
            "permissions": [
                "projects.read", "tasks.read", "tasks.update",
                "users.read", "resources.read", "reports.read"
            ]
        },
        {
            "name": "Stakeholder",
            "description": "View-only access to projects and reports",
            "is_system_role": True,
            "permissions": [
                "projects.read", "tasks.read", "reports.read"
            ]
        }
    ]
    
    created_count = 0
    roles = []
    for role_data in roles_data:
        existing = db.query(Role).filter(Role.name == role_data["name"]).first()
        if existing:
            role = existing
            print(f"  [~] Role already exists: {role_data['name']}")
        else:
            role = Role(
                name=role_data["name"],
                description=role_data["description"],
                is_system_role=role_data["is_system_role"]
            )
            db.add(role)
            created_count += 1
            print(f"  [+] Created role: {role_data['name']}")
        
        # Assign permissions to role
        role_permissions = [perm_lookup[pname] for pname in role_data["permissions"] if pname in perm_lookup]
        role.permissions = role_permissions
        roles.append(role)
    
    db.commit()
    print(f"[✓] Created {created_count} new roles")
    return roles


def assign_admin_all_roles(db: Session, roles):
    """Assign all roles to admin user"""
    print("\n[*] Assigning all roles to admin user...")
    
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        print("  [!] Admin user not found. Please create admin user first.")
        return
    
    # Assign all roles to admin
    admin.assigned_roles = roles
    db.commit()
    
    print(f"[✓] Assigned {len(roles)} roles to admin user")
    print(f"  Admin roles: {', '.join([r.name for r in admin.assigned_roles])}")


def main():
    """Main initialization function"""
    print("=" * 60)
    print("RBAC System Initialization")
    print("=" * 60)
    
    # Create tables
    print("\n[*] Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("[✓] Database tables created")
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Initialize permissions
        permissions = init_permissions(db)
        
        # Initialize roles with permissions
        roles = init_roles(db, permissions)
        
        # Assign all roles to admin
        assign_admin_all_roles(db, roles)
        
        print("\n" + "=" * 60)
        print("✓ RBAC System Initialization Complete!")
        print("=" * 60)
        print(f"\nTotal Permissions: {len(permissions)}")
        print(f"Total Roles: {len(roles)}")
        print("\nAdmin user has all roles and permissions.")
        
    except Exception as e:
        print(f"\n[✗] Error during initialization: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
