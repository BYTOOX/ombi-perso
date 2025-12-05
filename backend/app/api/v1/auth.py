"""
Authentication endpoints and JWT handling.
Supports local JWT auth and Plex SSO.
"""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from ...config import get_settings
from ...models import get_db, User
from ...models.user import UserRole
from ...schemas.user import (
    UserCreate, UserResponse, UserUpdate,
    Token, PlexAuth
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

settings = get_settings()
ph = PasswordHasher()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# JWT settings
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    try:
        ph.verify(hashed_password, plain_password)
        return True
    except VerifyMismatchError:
        return False


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return ph.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Identifiants invalides",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte désactivé"
        )
    
    return user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """Ensure current user is admin."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Droits administrateur requis"
        )
    return user


# =========================================================================
# ENDPOINTS
# =========================================================================

@router.post("/register", response_model=Token)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user."""
    # Check if username exists
    result = await db.execute(
        select(User).where(User.username == user_data.username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nom d'utilisateur déjà pris"
        )
    
    # Check if email exists
    if user_data.email:
        result = await db.execute(
            select(User).where(User.email == user_data.email)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email déjà utilisé"
            )
    
    # Check if first user (make admin)
    result = await db.execute(select(User).limit(1))
    is_first_user = result.scalar_one_or_none() is None
    
    # Create user
    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        role=UserRole.ADMIN if is_first_user else UserRole.USER
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    # Create token
    access_token = create_access_token(
        data={"user_id": user.id, "username": user.username, "role": user.role.value}
    )
    
    return Token(
        access_token=access_token,
        user=UserResponse.model_validate(user)
    )


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """Login with username and password."""
    result = await db.execute(
        select(User).where(User.username == form_data.username)
    )
    user = result.scalar_one_or_none()
    
    if not user or not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants incorrects"
        )
    
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants incorrects"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte désactivé"
        )
    
    # Update last login
    user.last_login = datetime.utcnow()
    await db.commit()
    
    # Create token
    access_token = create_access_token(
        data={"user_id": user.id, "username": user.username, "role": user.role.value}
    )
    
    return Token(
        access_token=access_token,
        user=UserResponse.model_validate(user)
    )


@router.post("/plex", response_model=Token)
async def plex_auth(
    plex_data: PlexAuth,
    db: AsyncSession = Depends(get_db)
):
    """Authenticate via Plex SSO."""
    # Get Plex user info
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                "https://plex.tv/users/account.json",
                headers={"X-Plex-Token": plex_data.plex_token}
            )
            response.raise_for_status()
            plex_user = response.json().get("user", {})
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Erreur Plex: {str(e)}"
            )
    
    plex_id = str(plex_user.get("id"))
    plex_username = plex_user.get("username")
    plex_email = plex_user.get("email")
    plex_thumb = plex_user.get("thumb")
    
    if not plex_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Impossible de récupérer l'ID Plex"
        )
    
    # Check if user exists by Plex ID
    result = await db.execute(
        select(User).where(User.plex_id == plex_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        # Check if first user
        result = await db.execute(select(User).limit(1))
        is_first_user = result.scalar_one_or_none() is None
        
        # Create new user from Plex
        user = User(
            username=plex_username,
            email=plex_email,
            plex_id=plex_id,
            plex_username=plex_username,
            plex_thumb=plex_thumb,
            role=UserRole.ADMIN if is_first_user else UserRole.USER
        )
        db.add(user)
    else:
        # Update Plex info
        user.plex_username = plex_username
        user.plex_thumb = plex_thumb
        user.last_login = datetime.utcnow()
    
    await db.commit()
    await db.refresh(user)
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte désactivé"
        )
    
    # Create token
    access_token = create_access_token(
        data={"user_id": user.id, "username": user.username, "role": user.role.value}
    )
    
    return Token(
        access_token=access_token,
        user=UserResponse.model_validate(user)
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user info."""
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    update_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update current user info."""
    if update_data.email is not None:
        current_user.email = update_data.email
    
    await db.commit()
    await db.refresh(current_user)
    
    return UserResponse.model_validate(current_user)
