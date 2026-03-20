"""
RBAC (Role-Based Access Control) Management Endpoints
Allows admins to manage roles, permissions, and user role assignments
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import List
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import User, Role, Permission, user_role_association, role_permission_association
from app.schemas.schemas import (
    RoleResponse, RoleCreate, RoleUpdate, RoleDetailResponse,
    PermissionResponse, PermissionCreate, PermissionUpdate,
    UserRoleAssignment, UserRoleRemoval, UserWithRoles,
    AdminRoleManagementResponse
)
from datetime import datetime

router = APIRouter()


def _check_admin(current_user: User):
    if not any(role.name.lower() == "admin" for role in current_user.assigned_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can perform this action"
        )


# ==================== Permission Endpoints ====================

@router.get("/permissions", response_model=List[PermissionResponse])
async def get_all_permissions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100
):
    _check_admin(current_user)
    result = await db.execute(select(Permission).offset(skip).limit(limit))
    return result.scalars().all()


@router.post("/permissions", response_model=PermissionResponse)
async def create_permission(
    permission: PermissionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    _check_admin(current_user)
    result = await db.execute(select(Permission).where(Permission.name == permission.name))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Permission already exists")
    db_permission = Permission(
        name=permission.name,
        description=permission.description,
        category=permission.category
    )
    db.add(db_permission)
    await db.commit()
    await db.refresh(db_permission)
    return db_permission


@router.get("/permissions/{permission_id}", response_model=PermissionResponse)
async def get_permission(
    permission_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    _check_admin(current_user)
    result = await db.execute(select(Permission).where(Permission.id == permission_id))
    permission = result.scalar_one_or_none()
    if not permission:
        raise HTTPException(status_code=404, detail="Permission not found")
    return permission


@router.put("/permissions/{permission_id}", response_model=PermissionResponse)
async def update_permission(
    permission_id: int,
    permission_update: PermissionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    _check_admin(current_user)
    result = await db.execute(select(Permission).where(Permission.id == permission_id))
    permission = result.scalar_one_or_none()
    if not permission:
        raise HTTPException(status_code=404, detail="Permission not found")
    if permission_update.description is not None:
        permission.description = permission_update.description
    if permission_update.category is not None:
        permission.category = permission_update.category
    if permission_update.is_active is not None:
        permission.is_active = permission_update.is_active
    permission.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(permission)
    return permission


# ==================== Role Endpoints ====================

@router.get("/roles", response_model=List[RoleResponse])
async def get_all_roles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100,
    is_active: bool = None
):
    _check_admin(current_user)
    query = select(Role).options(selectinload(Role.permissions)).offset(skip).limit(limit)
    if is_active is not None:
        query = query.where(Role.is_active == is_active)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/roles", response_model=RoleResponse)
async def create_role(
    role: RoleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    _check_admin(current_user)
    result = await db.execute(select(Role).where(Role.name == role.name))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Role already exists")
    db_role = Role(
        name=role.name,
        description=role.description,
        created_by=current_user.id
    )
    db.add(db_role)
    await db.commit()
    await db.refresh(db_role)
    return db_role


@router.get("/roles/{role_id}", response_model=RoleDetailResponse)
async def get_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    _check_admin(current_user)
    result = await db.execute(
        select(Role).options(selectinload(Role.permissions)).where(Role.id == role_id)
    )
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


@router.put("/roles/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: int,
    role_update: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    _check_admin(current_user)
    result = await db.execute(
        select(Role).options(selectinload(Role.permissions)).where(Role.id == role_id)
    )
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.is_system_role:
        raise HTTPException(status_code=400, detail="Cannot modify system roles")
    if role_update.description is not None:
        role.description = role_update.description
    if role_update.is_active is not None:
        role.is_active = role_update.is_active
    role.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(role)
    return role


@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    _check_admin(current_user)
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.is_system_role:
        raise HTTPException(status_code=400, detail="Cannot delete system roles")
    await db.delete(role)
    await db.commit()
    return {"message": "Role deleted successfully", "status": "success"}


# ==================== Role-Permission Association Endpoints ====================

@router.post("/roles/{role_id}/permissions")
async def assign_permissions_to_role(
    role_id: int,
    permissions_update: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    _check_admin(current_user)
    result = await db.execute(
        select(Role).options(selectinload(Role.permissions)).where(Role.id == role_id)
    )
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    permission_ids = permissions_update.get("permissions", [])
    perm_result = await db.execute(select(Permission).where(Permission.id.in_(permission_ids)))
    permissions = perm_result.scalars().all()
    if len(permissions) != len(permission_ids):
        raise HTTPException(status_code=400, detail="One or more permissions not found")
    role.permissions = list(permissions)
    await db.commit()
    return {
        "message": "Permissions assigned successfully",
        "status": "success",
        "role_id": role_id,
        "permission_count": len(permissions)
    }


@router.get("/roles/{role_id}/permissions", response_model=List[PermissionResponse])
async def get_role_permissions(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    _check_admin(current_user)
    result = await db.execute(
        select(Role).options(selectinload(Role.permissions)).where(Role.id == role_id)
    )
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return role.permissions


# ==================== User-Role Assignment Endpoints ====================

@router.post("/users/{user_id}/roles")
async def assign_role_to_user(
    user_id: int,
    role_assignment: UserRoleAssignment,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    _check_admin(current_user)
    result = await db.execute(
        select(User).options(selectinload(User.assigned_roles)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    role_result = await db.execute(select(Role).where(Role.id == role_assignment.role_id))
    role = role_result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if any(r.id == role.id for r in user.assigned_roles):
        raise HTTPException(status_code=400, detail="User already has this role")
    user.assigned_roles.append(role)
    await db.commit()
    return {
        "message": f"Role '{role.name}' assigned to user successfully",
        "status": "success",
        "user_id": user_id,
        "role_id": role.id
    }


@router.delete("/users/{user_id}/roles/{role_id}")
async def remove_role_from_user(
    user_id: int,
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    _check_admin(current_user)
    result = await db.execute(
        select(User).options(selectinload(User.assigned_roles)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    role_to_remove = None
    for r in user.assigned_roles:
        if r.id == role_id:
            role_to_remove = r
            break
    if not role_to_remove:
        raise HTTPException(status_code=400, detail="User does not have this role")
    user.assigned_roles.remove(role_to_remove)
    await db.commit()
    return {
        "message": f"Role '{role_to_remove.name}' removed from user successfully",
        "status": "success",
        "user_id": user_id,
        "role_id": role_id
    }


@router.get("/users/{user_id}/roles", response_model=List[RoleResponse])
async def get_user_roles(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    _check_admin(current_user)
    result = await db.execute(
        select(User)
        .options(selectinload(User.assigned_roles).selectinload(Role.permissions))
        .where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user.assigned_roles


@router.get("/users/{user_id}/permissions", response_model=List[PermissionResponse])
async def get_user_permissions(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    _check_admin(current_user)
    result = await db.execute(
        select(User)
        .options(selectinload(User.assigned_roles).selectinload(Role.permissions))
        .where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    all_permissions = {}
    for role in user.assigned_roles:
        for perm in role.permissions:
            all_permissions[perm.id] = perm
    return list(all_permissions.values())


@router.get("/users", response_model=List[UserWithRoles])
async def get_all_users_with_roles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100
):
    _check_admin(current_user)
    result = await db.execute(
        select(User)
        .options(selectinload(User.assigned_roles).selectinload(Role.permissions))
        .offset(skip).limit(limit)
    )
    return result.scalars().all()


@router.get("/dashboard/stats")
async def get_rbac_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    _check_admin(current_user)
    total_users = (await db.execute(select(func.count(User.id)))).scalar()
    total_roles = (await db.execute(select(func.count(Role.id)))).scalar()
    total_permissions = (await db.execute(select(func.count(Permission.id)))).scalar()
    active_roles = (await db.execute(
        select(func.count(Role.id)).where(Role.is_active == True)
    )).scalar()
    active_permissions = (await db.execute(
        select(func.count(Permission.id)).where(Permission.is_active == True)
    )).scalar()
    return {
        "total_users": total_users,
        "total_roles": total_roles,
        "total_permissions": total_permissions,
        "active_roles": active_roles,
        "active_permissions": active_permissions,
        "timestamp": datetime.utcnow()
    }
