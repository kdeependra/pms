import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def run():
    engine = create_async_engine('postgresql+asyncpg://postgres:admin@localhost:5432/pms_db')
    
    # Copy data from wrong tables to correct tables
    async with engine.begin() as conn:
        # Copy user_role_association -> user_roles
        r = await conn.execute(text("SELECT COUNT(*) FROM user_roles"))
        if r.scalar() == 0:
            await conn.execute(text(
                "INSERT INTO user_roles (user_id, role_id) "
                "SELECT user_id, role_id FROM user_role_association "
                "ON CONFLICT DO NOTHING"
            ))
            r2 = await conn.execute(text("SELECT COUNT(*) FROM user_roles"))
            print(f"Copied {r2.scalar()} rows to user_roles")
        else:
            print("user_roles already has data")

        # Copy role_permission_association -> role_permissions
        r3 = await conn.execute(text("SELECT COUNT(*) FROM role_permissions"))
        if r3.scalar() == 0:
            await conn.execute(text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT role_id, permission_id FROM role_permission_association "
                "ON CONFLICT DO NOTHING"
            ))
            r4 = await conn.execute(text("SELECT COUNT(*) FROM role_permissions"))
            print(f"Copied {r4.scalar()} rows to role_permissions")
        else:
            print("role_permissions already has data")

        # Verify
        r5 = await conn.execute(text(
            "SELECT u.username, r.name FROM user_roles ur "
            "JOIN users u ON u.id=ur.user_id "
            "JOIN roles r ON r.id=ur.role_id ORDER BY u.id"
        ))
        for row in r5.fetchall():
            print(f"  {row[0]} -> {row[1]}")

    await engine.dispose()

asyncio.run(run())
