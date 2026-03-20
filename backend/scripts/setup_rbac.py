"""Setup RBAC tables and seed data"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

DATABASE_URL = "postgresql+asyncpg://postgres:admin@localhost:5432/pms_db"

async def setup():
    engine = create_async_engine(DATABASE_URL)

    # Step 1: Schema migrations
    async with engine.begin() as conn:
        # Add missing columns to permissions table
        r = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='permissions'"
        ))
        cols = [row[0] for row in r.fetchall()]
        print("Permissions columns:", cols)
        if 'resource' not in cols:
            await conn.execute(text(
                "ALTER TABLE permissions ADD COLUMN resource VARCHAR NOT NULL DEFAULT 'general'"
            ))
            print("Added 'resource' column to permissions")
        if 'action' not in cols:
            await conn.execute(text(
                "ALTER TABLE permissions ADD COLUMN action VARCHAR NOT NULL DEFAULT 'read'"
            ))
            print("Added 'action' column to permissions")

    # Step 2: Create association tables
    async with engine.begin() as conn:
        r = await conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name IN "
            "('user_role_association','role_permission_association')"
        ))
        existing = [t[0] for t in r.fetchall()]
        print("Existing assoc tables:", existing)

        if 'user_role_association' not in existing:
            await conn.execute(text("""
                CREATE TABLE user_role_association (
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    role_id INTEGER REFERENCES roles(id) ON DELETE CASCADE,
                    PRIMARY KEY (user_id, role_id)
                )
            """))
            print("Created user_role_association")

        if 'role_permission_association' not in existing:
            await conn.execute(text("""
                CREATE TABLE role_permission_association (
                    role_id INTEGER REFERENCES roles(id) ON DELETE CASCADE,
                    permission_id INTEGER REFERENCES permissions(id) ON DELETE CASCADE,
                    PRIMARY KEY (role_id, permission_id)
                )
            """))
            print("Created role_permission_association")

    # Step 3: Seed roles
    async with engine.begin() as conn:
        r = await conn.execute(text("SELECT COUNT(*) FROM roles"))
        if r.scalar() == 0:
            await conn.execute(text("""
                INSERT INTO roles (name, description, is_system_role, is_active) VALUES
                ('Admin', 'Full system administrator with all permissions', true, true),
                ('Project Manager', 'Can manage projects, tasks, and team members', true, true),
                ('Resource Manager', 'Can manage resources and allocations', true, true),
                ('Team Member', 'Standard team member with basic access', true, true),
                ('Stakeholder', 'External stakeholder with view-only access', true, true)
            """))
            print("Seeded 5 default roles")
        else:
            print("Roles already exist")

    # Step 4: Seed permissions
    async with engine.begin() as conn:
        r = await conn.execute(text("SELECT COUNT(*) FROM permissions"))
        if r.scalar() == 0:
            await conn.execute(text("""
                INSERT INTO permissions (name, resource, action, description, category) VALUES
                ('projects.create', 'projects', 'create', 'Create new projects', 'general'),
                ('projects.read', 'projects', 'read', 'View projects', 'general'),
                ('projects.update', 'projects', 'update', 'Update projects', 'general'),
                ('projects.delete', 'projects', 'delete', 'Delete projects', 'admin'),
                ('tasks.create', 'tasks', 'create', 'Create tasks', 'general'),
                ('tasks.read', 'tasks', 'read', 'View tasks', 'general'),
                ('tasks.update', 'tasks', 'update', 'Update tasks', 'general'),
                ('tasks.delete', 'tasks', 'delete', 'Delete tasks', 'general'),
                ('users.create', 'users', 'create', 'Create users', 'admin'),
                ('users.read', 'users', 'read', 'View users', 'admin'),
                ('users.update', 'users', 'update', 'Update users', 'admin'),
                ('users.delete', 'users', 'delete', 'Delete users', 'admin'),
                ('resources.create', 'resources', 'create', 'Create resources', 'resource'),
                ('resources.read', 'resources', 'read', 'View resources', 'resource'),
                ('resources.update', 'resources', 'update', 'Update resources', 'resource'),
                ('resources.delete', 'resources', 'delete', 'Delete resources', 'resource'),
                ('reports.view', 'reports', 'read', 'View reports', 'general'),
                ('reports.export', 'reports', 'export', 'Export reports', 'general'),
                ('budget.manage', 'budget', 'manage', 'Manage budgets', 'general'),
                ('roles.manage', 'roles', 'manage', 'Manage roles and permissions', 'admin')
            """))
            print("Seeded 20 default permissions")
        else:
            print("Permissions already exist")

    # Step 5: Assign Admin role to admin user
    async with engine.begin() as conn:
        r = await conn.execute(text("SELECT COUNT(*) FROM user_role_association WHERE user_id=1"))
        if r.scalar() == 0:
            r2 = await conn.execute(text("SELECT id FROM roles WHERE name='Admin'"))
            admin_role_id = r2.scalar()
            if admin_role_id:
                await conn.execute(text(
                    "INSERT INTO user_role_association (user_id, role_id) VALUES (1, :rid)"
                ), {"rid": admin_role_id})
                print(f"Assigned Admin role to admin user")

    # Step 6: Assign all permissions to Admin role
    async with engine.begin() as conn:
        r = await conn.execute(text("SELECT id FROM roles WHERE name='Admin'"))
        admin_role_id = r.scalar()
        if admin_role_id:
            r2 = await conn.execute(text(
                "SELECT COUNT(*) FROM role_permission_association WHERE role_id=:rid"
            ), {"rid": admin_role_id})
            if r2.scalar() == 0:
                r3 = await conn.execute(text("SELECT id FROM permissions"))
                perm_ids = [row[0] for row in r3.fetchall()]
                for pid in perm_ids:
                    await conn.execute(text(
                        "INSERT INTO role_permission_association (role_id, permission_id) "
                        "VALUES (:rid, :pid)"
                    ), {"rid": admin_role_id, "pid": pid})
                print(f"Assigned {len(perm_ids)} permissions to Admin role")

    # Step 7: Assign roles to other users based on their role field
    async with engine.begin() as conn:
        r = await conn.execute(text("SELECT id, role FROM users WHERE id > 1"))
        users = r.fetchall()
        role_map = {
            'admin': 'Admin',
            'project_manager': 'Project Manager',
            'resource_manager': 'Resource Manager',
            'team_member': 'Team Member',
            'stakeholder': 'Stakeholder',
        }
        for user_id, user_role in users:
            r2 = await conn.execute(text(
                "SELECT COUNT(*) FROM user_role_association WHERE user_id=:uid"
            ), {"uid": user_id})
            if r2.scalar() == 0:
                role_name = role_map.get(user_role, 'Team Member')
                r3 = await conn.execute(text(
                    "SELECT id FROM roles WHERE name=:rn"
                ), {"rn": role_name})
                rid = r3.scalar()
                if rid:
                    await conn.execute(text(
                        "INSERT INTO user_role_association (user_id, role_id) VALUES (:uid, :rid)"
                    ), {"uid": user_id, "rid": rid})
                    print(f"Assigned '{role_name}' to user {user_id}")

    # Final summary
    async with engine.begin() as conn:
        r1 = await conn.execute(text("SELECT COUNT(*) FROM roles"))
        r2 = await conn.execute(text("SELECT COUNT(*) FROM permissions"))
        r3 = await conn.execute(text("SELECT COUNT(*) FROM user_role_association"))
        r4 = await conn.execute(text("SELECT COUNT(*) FROM role_permission_association"))
        print(f"\nSummary: {r1.scalar()} roles, {r2.scalar()} permissions, "
              f"{r3.scalar()} user-role assocs, {r4.scalar()} role-perm assocs")

    await engine.dispose()

asyncio.run(setup())
