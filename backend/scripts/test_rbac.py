import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def fix_and_test():
    engine = create_async_engine('postgresql+asyncpg://postgres:admin@localhost:5432/pms_db')
    
    # Fix null is_active in permissions
    async with engine.begin() as conn:
        r = await conn.execute(text("UPDATE permissions SET is_active=true WHERE is_active IS NULL"))
        print(f"Fixed {r.rowcount} permissions with null is_active")
    
    await engine.dispose()
    
    # Test API
    import requests
    r = requests.post('http://localhost:8000/api/v1/auth/login', data={'username':'admin','password':'admin123'})
    token = r.json().get('access_token','')
    h = {'Authorization': f'Bearer {token}'}
    
    r2 = requests.get('http://localhost:8000/api/v1/rbac/roles', headers=h)
    print(f'Roles: {r2.status_code}')
    if r2.status_code == 200:
        for role in r2.json():
            print(f"  {role['name']} (perms={len(role.get('permissions',[]))})")
    else:
        print(r2.text[:500])
    
    r3 = requests.get('http://localhost:8000/api/v1/rbac/users', headers=h)
    print(f'Users: {r3.status_code}')
    if r3.status_code == 200:
        for u in r3.json():
            roles = [r['name'] for r in u.get('assigned_roles', [])]
            print(f"  {u['username']} -> {roles}")
    else:
        print(r3.text[:500])
    
    r4 = requests.get('http://localhost:8000/api/v1/rbac/dashboard/stats', headers=h)
    print(f'Stats: {r4.status_code} {r4.json() if r4.status_code==200 else r4.text[:200]}')

asyncio.run(fix_and_test())
