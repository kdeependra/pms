from fastapi import APIRouter, Depends
from typing import List
from app.core.security import get_current_user
from app.schemas.schemas import UserResponse

router = APIRouter()

@router.get("/", response_model=List[UserResponse])
async def get_users(current_user: dict = Depends(get_current_user)):
    """Get all users"""
    return []
