"""
Transfer History model for tracking file movements.
"""
from enum import Enum
from sqlalchemy import Column, Integer, String, DateTime, Enum as SQLEnum, Float, Text, Boolean
from sqlalchemy.sql import func

from .database import Base


class TransferStatus(str, Enum):
    """Status of a file transfer."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TransferHistory(Base):
    """
    Model for tracking file transfer history.
    Stores information about each file movement operation.
    """
    __tablename__ = "transfer_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Transfer identification
    request_id = Column(Integer, nullable=True, index=True)  # Link to original request
    
    # File info
    original_filename = Column(String(500), nullable=False)
    original_path = Column(String(1000), nullable=False)
    destination_path = Column(String(1000), nullable=True)
    
    # Media info
    media_title = Column(String(255), nullable=True)
    media_type = Column(String(50), nullable=False)  # movie, series, anime
    year = Column(Integer, nullable=True)
    season = Column(Integer, nullable=True)
    episode = Column(Integer, nullable=True)
    
    # Transfer details
    status = Column(SQLEnum(TransferStatus), default=TransferStatus.PENDING, index=True)
    progress = Column(Float, default=0.0)  # 0-100
    file_size_bytes = Column(Integer, nullable=True)
    
    # Timing
    created_at = Column(DateTime, server_default=func.now(), index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Error handling
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    
    # Flags
    is_manual = Column(Boolean, default=False)  # Manually triggered transfer
    
    def to_dict(self):
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "request_id": self.request_id,
            "original_filename": self.original_filename,
            "original_path": self.original_path,
            "destination_path": self.destination_path,
            "media_title": self.media_title,
            "media_type": self.media_type,
            "year": self.year,
            "season": self.season,
            "episode": self.episode,
            "status": self.status.value if self.status else None,
            "progress": self.progress,
            "file_size_bytes": self.file_size_bytes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "is_manual": self.is_manual
        }
    
    def to_friendly_log(self) -> str:
        """Generate user-friendly log message."""
        emoji = {
            TransferStatus.PENDING: "⏳",
            TransferStatus.IN_PROGRESS: "📦",
            TransferStatus.COMPLETED: "✅",
            TransferStatus.FAILED: "❌",
            TransferStatus.CANCELLED: "🚫"
        }.get(self.status, "❓")
        
        title = self.media_title or self.original_filename
        
        if self.status == TransferStatus.COMPLETED:
            return f'{emoji} "{title}" déplacé vers {self.media_type} avec succès'
        elif self.status == TransferStatus.FAILED:
            error = self.error_message[:50] if self.error_message else "erreur inconnue"
            return f'{emoji} "{title}" a échoué - {error}'
        elif self.status == TransferStatus.IN_PROGRESS:
            return f'{emoji} "{title}" en cours de transfert ({self.progress:.0f}%)'
        elif self.status == TransferStatus.PENDING:
            return f'{emoji} "{title}" en attente de transfert'
        elif self.status == TransferStatus.CANCELLED:
            return f'{emoji} "{title}" transfert annulé'
        
        return f'{emoji} "{title}" - statut: {self.status}'
