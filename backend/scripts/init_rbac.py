"""
Initialize RBAC System with Default Roles and Permissions
Run this script once to set up the initial RBAC configuration
"""

import asyncio
import sys
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings
from app.models.models import Base, Permission, Role, User


# Create synchronous session for initialization
db_url = settings.DATABASE_URL
if "asyncpg" in db_url:
    sync_db_url = db_url.replace("+asyncpg", "")
elif "aiosqlite" in db_url:
    sync_db_url = db_url.replace("+aiosqlite", "")
else:
    sync_db_url = db_url

sync_engine = create_engine(sync_db_url, echo=False)
SyncSessionLocal = sessionmaker(bind=sync_engine)


def init_rbac():
    """Initialize the RBAC system with default roles and permissions"""
    
    db: Session = SyncSessionLocal()
    
    try:
        # Define all permissions
        permissions_data = [
            # Project Management
            {"name": "project:create", "category": "project", "description": "Create new projects"},
            {"name": "project:read", "category": "project", "description": "View projects"},
            {"name": "project:update", "category": "project", "description": "Update project details"},
            {"name": "project:delete", "category": "project", "description": "Delete projects"},
            {"name": "project:manage_team", "category": "project", "description": "Manage project team members"},
            
            # Task Management
            {"name": "task:create", "category": "task", "description": "Create new tasks"},
            {"name": "task:read", "category": "task", "description": "View tasks"},
            {"name": "task:update", "category": "task", "description": "Update tasks"},
            {"name": "task:delete", "category": "task", "description": "Delete tasks"},
            {"name": "task:assign", "category": "task", "description": "Assign tasks to users"},
            
            # Resource Management
            {"name": "resource:create", "category": "resource", "description": "Create resources"},
            {"name": "resource:read", "category": "resource", "description": "View resources"},
            {"name": "resource:update", "category": "resource", "description": "Update resources"},
            {"name": "resource:delete", "category": "resource", "description": "Delete resources"},
            {"name": "resource:allocate", "category": "resource", "description": "Allocate resources to projects"},
            
            # Risk Management
            {"name": "risk:create", "category": "risk", "description": "Create risks"},
            {"name": "risk:read", "category": "risk", "description": "View risks"},
            {"name": "risk:update", "category": "risk", "description": "Update risks"},
            {"name": "risk:delete", "category": "risk", "description": "Delete risks"},
            
            # Issue Management
            {"name": "issue:create", "category": "issue", "description": "Create issues"},
            {"name": "issue:read", "category": "issue", "description": "View issues"},
            {"name": "issue:update", "category": "issue", "description": "Update issues"},
            {"name": "issue:resolve", "category": "issue", "description": "Resolve issues"},
            
            # Budget Management
            {"name": "budget:view", "category": "budget", "description": "View budget information"},
            {"name": "budget:manage", "category": "budget", "description": "Manage budget allocations"},
            {"name": "budget:approve", "category": "budget", "description": "Approve budget expenses"},
            
            # Report & Analytics
            {"name": "report:view", "category": "report", "description": "View reports"},
            {"name": "report:create", "category": "report", "description": "Create custom reports"},
            {"name": "report:export", "category": "report", "description": "Export reports"},
            
            # User Management
            {"name": "user:create", "category": "user", "description": "Create new users"},
            {"name": "user:read", "category": "user", "description": "View user information"},
            {"name": "user:update", "category": "user", "description": "Update user information"},
            {"name": "user:delete", "category": "user", "description": "Delete users"},
            {"name": "user:manage_roles", "category": "user", "description": "Manage user roles"},
            
            # Role Management
            {"name": "role:create", "category": "role", "description": "Create roles"},
            {"name": "role:read", "category": "role", "description": "View roles"},
            {"name": "role:update", "category": "role", "description": "Update roles"},
            {"name": "role:delete", "category": "role", "description": "Delete roles"},
            {"name": "role:manage_permissions", "category": "role", "description": "Manage role permissions"},
            
            # Document Management
            {"name": "document:create", "category": "document", "description": "Create documents"},
            {"name": "document:read", "category": "document", "description": "View documents"},
            {"name": "document:update", "category": "document", "description": "Update documents"},
            {"name": "document:delete", "category": "document", "description": "Delete documents"},
            {"name": "document:approve", "category": "document", "description": "Approve documents"},
            
            # Workflow Management
            {"name": "workflow:create", "category": "workflow", "description": "Create workflows"},
            {"name": "workflow:read", "category": "workflow", "description": "View workflows"},
            {"name": "workflow:execute", "category": "workflow", "description": "Execute workflows"},
            {"name": "workflow:approve", "category": "workflow", "description": "Approve workflow steps"},
            
            # Dashboard & Analytics
            {"name": "dashboard:view", "category": "dashboard", "description": "View dashboards"},
            {"name": "dashboard:create", "category": "dashboard", "description": "Create custom dashboards"},
            
            # Admin Functions
            {"name": "admin:view_logs", "category": "admin", "description": "View system logs"},
            {"name": "admin:manage_system", "category": "admin", "description": "Manage system settings"},
        ]
        
        # Create permissions if they don't exist
        print("Creating permissions...")
        created_permissions = 0
        for perm_data in permissions_data:
            existing = db.query(Permission).filter(Permission.name == perm_data["name"]).first()
            if not existing:
                perm = Permission(**perm_data)
                db.add(perm)
                created_permissions += 1
        db.commit()
        print(f"✓ Created {created_permissions} new permissions")
        
        # Create roles and assign permissions
        print("\nCreating roles...")
        all_permissions = db.query(Permission).all()
        
        # Admin role - all permissions
        admin_role_data = {
            "name": "Admin",
            "description": "System administrator with full access",
            "is_system_role": True,
            "permissions": all_permissions
        }
        
        roles_to_create = [
            admin_role_data,
            {
                "name": "Project Manager",
                "description": "Project manager with project and team management access",
                "is_system_role": True,
                "permissions": [p for p in all_permissions if p.category in ["project", "task", "resource", "risk", "issue", "report", "document", "workflow"]]
            },
            {
                "name": "Team Member",
                "description": "Team member with task and project access",
                "is_system_role": True,
                "permissions": [p for p in all_permissions if p.name in [
                    "project:read", "task:read", "task:create", "task:update", 
                    "resource:read", "risk:read", "issue:read", "issue:create",
                    "report:view", "document:read", "dashboard:view"
                ]]
            },
            {
                "name": "Stakeholder",
                "description": "Stakeholder with read-only access",
                "is_system_role": True,
                "permissions": [p for p in all_permissions if p.name in [
                    "project:read", "task:read", "report:view", 
                    "document:read", "dashboard:view"
                ]]
            },
            {
                "name": "Budget Manager",
                "description": "Budget manager with budget and financial access",
                "is_system_role": False,
                "permissions": [p for p in all_permissions if p.category in ["budget", "project", "report"]]
            },
            {
                "name": "Resource Manager",
                "description": "Resource manager with resource allocation access",
                "is_system_role": False,
                "permissions": [p for p in all_permissions if p.category in ["resource", "project", "task"]]
            },
        ]
        
        created_roles = 0
        for role_data in roles_to_create:
            permissions_list = role_data.pop("permissions")
            existing = db.query(Role).filter(Role.name == role_data["name"]).first()
            if not existing:
                role = Role(**role_data)
                role.permissions = permissions_list
                db.add(role)
                created_roles += 1
        db.commit()
        print(f"✓ Created {created_roles} new roles")
        
        # Assign admin role to existing admin users
        print("\nAssigning Admin role to admin users...")
        admin_role = db.query(Role).filter(Role.name == "Admin").first()
        admin_users = db.query(User).filter(User.username == "admin").all()
        
        for user in admin_users:
            if admin_role not in user.assigned_roles:
                user.assigned_roles.append(admin_role)
                db.commit()
                print(f"✓ Assigned Admin role to user '{user.username}'")
        
        print("\n" + "="*50)
        print("✅ RBAC System initialized successfully!")
        print("="*50)
        print(f"\nSummary:")
        print(f"  - Total Permissions: {db.query(Permission).count()}")
        print(f"  - Total Roles: {db.query(Role).count()}")
        print(f"  - Active Permissions: {db.query(Permission).filter(Permission.is_active == True).count()}")
        print(f"  - Active Roles: {db.query(Role).filter(Role.is_active == True).count()}")
        print("\nYou can now restart the application and access RBAC management")
        print("from Admin > RBAC Dashboard")
        
    except Exception as e:
        print(f"❌ Error initializing RBAC: {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
        sys.exit(1)
    finally:
        db.close()
        sync_engine.dispose()
    
    try:
        # Define all permissions
        permissions_data = [
            # Project Management
            {"name": "project:create", "category": "project", "description": "Create new projects"},
            {"name": "project:read", "category": "project", "description": "View projects"},
            {"name": "project:update", "category": "project", "description": "Update project details"},
            {"name": "project:delete", "category": "project", "description": "Delete projects"},
            {"name": "project:manage_team", "category": "project", "description": "Manage project team members"},
            
            # Task Management
            {"name": "task:create", "category": "task", "description": "Create new tasks"},
            {"name": "task:read", "category": "task", "description": "View tasks"},
            {"name": "task:update", "category": "task", "description": "Update tasks"},
            {"name": "task:delete", "category": "task", "description": "Delete tasks"},
            {"name": "task:assign", "category": "task", "description": "Assign tasks to users"},
            
            # Resource Management
            {"name": "resource:create", "category": "resource", "description": "Create resources"},
            {"name": "resource:read", "category": "resource", "description": "View resources"},
            {"name": "resource:update", "category": "resource", "description": "Update resources"},
            {"name": "resource:delete", "category": "resource", "description": "Delete resources"},
            {"name": "resource:allocate", "category": "resource", "description": "Allocate resources to projects"},
            
            # Risk Management
            {"name": "risk:create", "category": "risk", "description": "Create risks"},
            {"name": "risk:read", "category": "risk", "description": "View risks"},
            {"name": "risk:update", "category": "risk", "description": "Update risks"},
            {"name": "risk:delete", "category": "risk", "description": "Delete risks"},
            
            # Issue Management
            {"name": "issue:create", "category": "issue", "description": "Create issues"},
            {"name": "issue:read", "category": "issue", "description": "View issues"},
            {"name": "issue:update", "category": "issue", "description": "Update issues"},
            {"name": "issue:resolve", "category": "issue", "description": "Resolve issues"},
            
            # Budget Management
            {"name": "budget:view", "category": "budget", "description": "View budget information"},
            {"name": "budget:manage", "category": "budget", "description": "Manage budget allocations"},
            {"name": "budget:approve", "category": "budget", "description": "Approve budget expenses"},
            
            # Report & Analytics
            {"name": "report:view", "category": "report", "description": "View reports"},
            {"name": "report:create", "category": "report", "description": "Create custom reports"},
            {"name": "report:export", "category": "report", "description": "Export reports"},
            
            # User Management
            {"name": "user:create", "category": "user", "description": "Create new users"},
            {"name": "user:read", "category": "user", "description": "View user information"},
            {"name": "user:update", "category": "user", "description": "Update user information"},
            {"name": "user:delete", "category": "user", "description": "Delete users"},
            {"name": "user:manage_roles", "category": "user", "description": "Manage user roles"},
            
            # Role Management
            {"name": "role:create", "category": "role", "description": "Create roles"},
            {"name": "role:read", "category": "role", "description": "View roles"},
            {"name": "role:update", "category": "role", "description": "Update roles"},
            {"name": "role:delete", "category": "role", "description": "Delete roles"},
            {"name": "role:manage_permissions", "category": "role", "description": "Manage role permissions"},
            
            # Document Management
            {"name": "document:create", "category": "document", "description": "Create documents"},
            {"name": "document:read", "category": "document", "description": "View documents"},
            {"name": "document:update", "category": "document", "description": "Update documents"},
            {"name": "document:delete", "category": "document", "description": "Delete documents"},
            {"name": "document:approve", "category": "document", "description": "Approve documents"},
            
            # Workflow Management
            {"name": "workflow:create", "category": "workflow", "description": "Create workflows"},
            {"name": "workflow:read", "category": "workflow", "description": "View workflows"},
            {"name": "workflow:execute", "category": "workflow", "description": "Execute workflows"},
            {"name": "workflow:approve", "category": "workflow", "description": "Approve workflow steps"},
            
            # Dashboard & Analytics
            {"name": "dashboard:view", "category": "dashboard", "description": "View dashboards"},
            {"name": "dashboard:create", "category": "dashboard", "description": "Create custom dashboards"},
            
            # Admin Functions
            {"name": "admin:view_logs", "category": "admin", "description": "View system logs"},
            {"name": "admin:manage_system", "category": "admin", "description": "Manage system settings"},
        ]
        
        # Create permissions if they don't exist
        print("Creating permissions...")
        created_permissions = 0
        for perm_data in permissions_data:
            existing = db.query(Permission).filter(Permission.name == perm_data["name"]).first()
            if not existing:
                perm = Permission(**perm_data)
                db.add(perm)
                created_permissions += 1
        db.commit()
        print(f"✓ Created {created_permissions} new permissions")
        
        # Define roles and their permissions
        roles_data = [
            {
                "name": "Admin",
                "description": "System administrator with full access",
                "is_system_role": True,
                "permissions": db.query(Permission).all()  # All permissions
            },
            {
                "name": "Project Manager",
                "description": "Project manager with project and team management access",
                "is_system_role": True,
                "permissions": [perm for perm in db.query(Permission).all() 
                               if perm.category in ["project", "task", "resource", "risk", "issue", "report", "document", "workflow"]]
            },
            {
                "name": "Team Member",
                "description": "Team member with task and project access",
                "is_system_role": True,
                "permissions": [perm for perm in db.query(Permission).all() 
                               if perm.name in ["project:read", "task:read", "task:create", "task:update", 
                                               "resource:read", "risk:read", "issue:read", "issue:create",
                                               "report:view", "document:read", "dashboard:view"]]
            },
            {
                "name": "Stakeholder",
                "description": "Stakeholder with read-only access",
                "is_system_role": True,
                "permissions": [perm for perm in db.query(Permission).all() 
                               if perm.name in ["project:read", "task:read", "report:view", 
                                               "document:read", "dashboard:view"]]
            },
            {
                "name": "Budget Manager",
                "description": "Budget manager with budget and financial access",
                "is_system_role": False,
                "permissions": [perm for perm in db.query(Permission).all() 
                               if perm.category in ["budget", "project", "report"]]
            },
            {
                "name": "Resource Manager",
                "description": "Resource manager with resource allocation access",
                "is_system_role": False,
                "permissions": [perm for perm in db.query(Permission).all() 
                               if perm.category in ["resource", "project", "task"]]
            },
        ]
        
        # Create roles if they don't exist
        print("\nCreating roles...")
        created_roles = 0
        for role_data in roles_data:
            permissions_list = role_data.pop("permissions")
            existing = db.query(Role).filter(Role.name == role_data["name"]).first()
            if not existing:
                role = Role(**role_data)
                role.permissions = permissions_list
                db.add(role)
                created_roles += 1
        db.commit()
        print(f"✓ Created {created_roles} new roles")
        
        # Assign admin role to existing admin users
        print("\nAssigning Admin role to admin users...")
        admin_role = db.query(Role).filter(Role.name == "Admin").first()
        admin_users = db.query(User).filter(User.username == "admin").all()
        
        for user in admin_users:
            if admin_role not in user.assigned_roles:
                user.assigned_roles.append(admin_role)
                db.commit()
                print(f"✓ Assigned Admin role to user '{user.username}'")
        
        print("\n" + "="*50)
        print("✅ RBAC System initialized successfully!")
        print("="*50)
        print(f"\nSummary:")
        print(f"  - Total Permissions: {db.query(Permission).count()}")
        print(f"  - Total Roles: {db.query(Role).count()}")
        print(f"  - Active Permissions: {db.query(Permission).filter(Permission.is_active == True).count()}")
        print(f"  - Active Roles: {db.query(Role).filter(Role.is_active == True).count()}")
        
    except Exception as e:
        print(f"❌ Error initializing RBAC: {str(e)}")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    init_rbac()
