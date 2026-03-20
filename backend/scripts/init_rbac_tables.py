"""
Initialize RBAC tables using synchronous database connection
This ensures tables are created properly regardless of async configuration
"""

import asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models.models import Base, Permission, Role
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_tables():
    """Create RBAC tables using synchronous engine"""
    
    try:
        print("Initializing RBAC tables...")
        
        # Convert async database URL to sync for table creation
        db_url = settings.DATABASE_URL
        
        if "asyncpg" in db_url:
            # Convert postgresql+asyncpg to postgresql
            sync_db_url = db_url.replace("+asyncpg", "")
        elif "aiosqlite" in db_url:
            # Convert sqlite+aiosqlite to sqlite
            sync_db_url = db_url.replace("+aiosqlite", "")
        else:
            sync_db_url = db_url
        
        print(f"Using database: {sync_db_url.split('@')[-1] if '@' in sync_db_url else sync_db_url}")
        
        # Create synchronous engine
        sync_engine = create_engine(sync_db_url, echo=False)
        
        # Create all tables from Base metadata
        Base.metadata.create_all(bind=sync_engine)
        
        # Test connection and get table count
        with sync_engine.connect() as conn:
            # Check if tables exist
            if "postgresql" in sync_db_url:
                result = conn.execute(text("""
                    SELECT table_name FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name IN ('permissions', 'roles', 'role_permissions', 'user_roles')
                """))
            else:  # SQLite
                result = conn.execute(text("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' 
                    AND name IN ('permissions', 'roles', 'role_permissions', 'user_roles')
                """))
            
            tables = [row[0] for row in result]
        
        print("\n" + "="*60)
        print("✅ RBAC TABLES CREATED SUCCESSFULLY!")
        print("="*60)
        print(f"\nTables created: {len(tables)}")
        print(f"  {tables}")
        print("\nNext steps:")
        print("  1. Run: python scripts/init_rbac.py")
        print("  2. This will create default roles and permissions")
        print("  3. Restart the application")
        print("\nNOTE: Keep the application running with 'npm start' from frontend")
        print("="*60)
        
        sync_engine.dispose()
        return True
        
    except Exception as e:
        print(f"❌ Error creating RBAC tables: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    create_tables()
