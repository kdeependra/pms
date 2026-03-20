from datetime import datetime, timedelta
from typing import Optional, List, Callable
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.config import settings
from app.core.database import get_db

# Password hashing - Using argon2 for better Python 3.14+ compatibility
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str):
    """Decode JWT token"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Get current authenticated user from database"""
    from app.models.models import User, Role

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    
    user_id: str = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.assigned_roles)
            .selectinload(Role.permissions)
        )
        .where(User.id == int(user_id))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    
    return user


# --------------- RBAC Helpers ---------------

def require_role(*allowed_roles: str) -> Callable:
    """
    Dependency that checks if the current user has at least one of the allowed roles.
    Usage:  current_user: User = Depends(require_role("Admin", "Project Manager"))
    """
    async def _check(current_user=Depends(get_current_user)):
        user_roles = {r.name for r in current_user.assigned_roles}
        if not user_roles.intersection(allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(allowed_roles)}"
            )
        return current_user
    return _check


def require_permission(*needed: str) -> Callable:
    """
    Dependency that checks if the current user has ALL of the listed permissions
    (through any of their assigned roles).
    Usage:  current_user: User = Depends(require_permission("projects.create"))
    """
    async def _check(current_user=Depends(get_current_user)):
        user_perms: set[str] = set()
        for role in current_user.assigned_roles:
            for perm in role.permissions:
                user_perms.add(perm.name)
        missing = set(needed) - user_perms
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permissions: {', '.join(missing)}"
            )
        return current_user
    return _check
