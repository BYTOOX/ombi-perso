"""
Transfer management endpoints for admin panel.
Includes WebSocket support for real-time updates.
"""
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from ...dependencies import get_async_db
from ...models.user import User
from ...models.transfer_history import TransferHistory, TransferStatus
from .auth import get_current_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/transfers", tags=["transfers"])

# WebSocket connections manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()


# =============================
# WebSocket Endpoint
# =============================

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time transfer updates.
    Broadcasts transfer status changes to all connected clients.
    """
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, wait for messages
            data = await websocket.receive_text()
            # Echo back for ping/pong keepalive
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# =============================
# REST Endpoints
# =============================

@router.get("")
async def get_transfers(
    status: Optional[str] = Query(None, description="Filter by status"),
    media_type: Optional[str] = Query(None, description="Filter by media type"),
    hours: int = Query(24, description="Get transfers from last N hours"),
    limit: int = Query(50, description="Max results"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_admin)
):
    """Get transfer history with optional filters."""
    query = select(TransferHistory)
    
    # Time filter
    since = datetime.utcnow() - timedelta(hours=hours)
    query = query.where(TransferHistory.created_at >= since)
    
    # Status filter
    if status:
        try:
            status_enum = TransferStatus(status)
            query = query.where(TransferHistory.status == status_enum)
        except ValueError:
            pass
    
    # Media type filter
    if media_type:
        query = query.where(TransferHistory.media_type == media_type)
    
    # Order and limit
    query = query.order_by(desc(TransferHistory.created_at)).limit(limit)
    
    result = await db.execute(query)
    transfers = result.scalars().all()
    
    return {
        "transfers": [t.to_dict() for t in transfers],
        "total": len(transfers)
    }


@router.get("/stats")
async def get_transfer_stats(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_admin)
):
    """Get transfer statistics."""
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)
    
    # Count by status (today)
    today_query = select(
        TransferHistory.status,
        func.count(TransferHistory.id)
    ).where(
        TransferHistory.created_at >= today_start
    ).group_by(TransferHistory.status)
    
    result = await db.execute(today_query)
    today_stats = {row[0].value: row[1] for row in result.all()}
    
    # Total bytes transferred this week
    bytes_query = select(
        func.sum(TransferHistory.file_size_bytes)
    ).where(
        and_(
            TransferHistory.created_at >= week_start,
            TransferHistory.status == TransferStatus.COMPLETED
        )
    )
    result = await db.execute(bytes_query)
    total_bytes = result.scalar() or 0
    
    # In progress count
    in_progress_query = select(func.count(TransferHistory.id)).where(
        TransferHistory.status == TransferStatus.IN_PROGRESS
    )
    result = await db.execute(in_progress_query)
    in_progress = result.scalar() or 0
    
    # Pending count
    pending_query = select(func.count(TransferHistory.id)).where(
        TransferHistory.status == TransferStatus.PENDING
    )
    result = await db.execute(pending_query)
    pending = result.scalar() or 0
    
    return {
        "in_progress": in_progress,
        "pending": pending,
        "today": {
            "completed": today_stats.get("completed", 0),
            "failed": today_stats.get("failed", 0),
            "total": sum(today_stats.values())
        },
        "week_bytes_transferred": total_bytes,
        "week_gb_transferred": round(total_bytes / (1024**3), 2) if total_bytes else 0
    }


@router.get("/active")
async def get_active_transfers(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_admin)
):
    """Get currently active (in_progress or pending) transfers."""
    query = select(TransferHistory).where(
        TransferHistory.status.in_([TransferStatus.PENDING, TransferStatus.IN_PROGRESS])
    ).order_by(TransferHistory.created_at)
    
    result = await db.execute(query)
    transfers = result.scalars().all()
    
    return {
        "active": [t.to_dict() for t in transfers],
        "count": len(transfers)
    }


@router.get("/logs")
async def get_friendly_logs(
    hours: int = Query(24, description="Get logs from last N hours"),
    limit: int = Query(20, description="Max logs to return"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_admin)
):
    """Get user-friendly activity logs."""
    since = datetime.utcnow() - timedelta(hours=hours)
    
    query = select(TransferHistory).where(
        TransferHistory.created_at >= since
    ).order_by(desc(TransferHistory.created_at)).limit(limit)
    
    result = await db.execute(query)
    transfers = result.scalars().all()
    
    logs = []
    for t in transfers:
        logs.append({
            "id": t.id,
            "message": t.to_friendly_log(),
            "status": t.status.value if t.status else None,
            "time": t.created_at.isoformat() if t.created_at else None,
            "can_retry": t.status == TransferStatus.FAILED
        })
    
    return {"logs": logs}


@router.post("/{transfer_id}/retry")
async def retry_transfer(
    transfer_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_admin)
):
    """Retry a failed transfer."""
    result = await db.execute(
        select(TransferHistory).where(TransferHistory.id == transfer_id)
    )
    transfer = result.scalar_one_or_none()
    
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfert non trouvé")
    
    if transfer.status != TransferStatus.FAILED:
        raise HTTPException(status_code=400, detail="Seuls les transferts échoués peuvent être relancés")
    
    # Reset status and increment retry count
    transfer.status = TransferStatus.PENDING
    transfer.progress = 0
    transfer.error_message = None
    transfer.retry_count += 1
    transfer.started_at = None
    transfer.completed_at = None
    
    await db.commit()
    
    # Broadcast update
    await manager.broadcast({
        "type": "transfer_update",
        "transfer": transfer.to_dict()
    })
    
    return {"success": True, "message": "Transfert remis en attente", "transfer": transfer.to_dict()}


@router.post("/force")
async def force_transfer(
    original_path: str,
    media_type: str,
    media_title: Optional[str] = None,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_admin)
):
    """Force a manual transfer."""
    import os
    
    if not os.path.exists(original_path):
        raise HTTPException(status_code=400, detail=f"Chemin non trouvé: {original_path}")
    
    # Create new transfer entry
    transfer = TransferHistory(
        original_filename=os.path.basename(original_path),
        original_path=original_path,
        media_title=media_title or os.path.basename(original_path),
        media_type=media_type,
        status=TransferStatus.PENDING,
        is_manual=True
    )
    
    db.add(transfer)
    await db.commit()
    await db.refresh(transfer)
    
    # Broadcast new transfer
    await manager.broadcast({
        "type": "transfer_new",
        "transfer": transfer.to_dict()
    })
    
    return {"success": True, "message": "Transfert manuel créé", "transfer": transfer.to_dict()}


@router.delete("/{transfer_id}")
async def cancel_transfer(
    transfer_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_admin)
):
    """Cancel a pending transfer."""
    result = await db.execute(
        select(TransferHistory).where(TransferHistory.id == transfer_id)
    )
    transfer = result.scalar_one_or_none()
    
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfert non trouvé")
    
    if transfer.status not in [TransferStatus.PENDING, TransferStatus.FAILED]:
        raise HTTPException(status_code=400, detail="Seuls les transferts en attente peuvent être annulés")
    
    transfer.status = TransferStatus.CANCELLED
    await db.commit()
    
    # Broadcast update
    await manager.broadcast({
        "type": "transfer_cancelled",
        "transfer_id": transfer_id
    })
    
    return {"success": True, "message": "Transfert annulé"}


# Helper function to update transfer and broadcast
async def update_transfer_progress(
    transfer_id: int,
    progress: float,
    status: Optional[TransferStatus] = None,
    error_message: Optional[str] = None
):
    """Update transfer progress and broadcast to WebSocket clients."""
    from ...models.database import SessionLocal
    
    async with SessionLocal() as db:
        result = await db.execute(
            select(TransferHistory).where(TransferHistory.id == transfer_id)
        )
        transfer = result.scalar_one_or_none()
        
        if transfer:
            transfer.progress = progress
            if status:
                transfer.status = status
                if status == TransferStatus.IN_PROGRESS and not transfer.started_at:
                    transfer.started_at = datetime.utcnow()
                elif status == TransferStatus.COMPLETED:
                    transfer.completed_at = datetime.utcnow()
            if error_message:
                transfer.error_message = error_message
            
            await db.commit()
            
            # Broadcast update
            await manager.broadcast({
                "type": "transfer_progress",
                "transfer": transfer.to_dict()
            })
