"""
Schemas for system settings management.
"""
from typing import Dict, Optional
from pydantic import BaseModel, Field


class PathInfo(BaseModel):
    """Path validation information."""
    path: str
    exists: bool
    writable: bool
    is_directory: bool = True


class PathSettingsResponse(BaseModel):
    """Response for path settings GET endpoint."""
    download_path: PathInfo
    library_paths: Dict[str, PathInfo]


class PathSettingsUpdate(BaseModel):
    """Request body for updating path settings."""
    download_path: str = Field(..., description="Path for temporary downloads")
    library_paths: Dict[str, str] = Field(
        ..., 
        description="Mapping of media type to library path"
    )


class DirectoryItem(BaseModel):
    """A directory item in file browser."""
    name: str
    path: str
    is_directory: bool = True
    is_parent: bool = False
    writable: bool = True


class DirectoryBrowseResponse(BaseModel):
    """Response for directory browse endpoint."""
    current_path: str
    items: list[DirectoryItem]
    error: Optional[str] = None
