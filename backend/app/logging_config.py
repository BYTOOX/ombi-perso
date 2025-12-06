"""
Centralized logging configuration with file handlers and module separation.

Logs are written to:
- /app/data/logs/all.log - All logs
- /app/data/logs/api.log - API endpoints logs  
- /app/data/logs/pipeline.log - Request pipeline logs
- /app/data/logs/services.log - Services logs (torrent, plex, etc)
"""
import logging
import json
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Dict, List, Optional
from collections import deque

# Log storage directory
LOG_DIR = Path("/app/data/logs")

# In-memory log buffer for quick access (last N entries per module)
LOG_BUFFER_SIZE = 500

# Module mapping for categorization
LOG_MODULES = {
    "api": ["app.api", "app.main", "uvicorn"],
    "pipeline": ["app.services.pipeline"],
    "ai": ["app.services.ai_agent"],  # Dedicated AI logs for prompt debugging
    "services": [
        "app.services.torrent_scraper",
        "app.services.downloader",
        "app.services.plex_manager",
        "app.services.file_renamer",
        "app.services.notifications",
        "app.services.media_search"
    ],
    "database": ["app.models", "sqlalchemy"]
}


class JsonFormatter(logging.Formatter):
    """Format log records as JSON for easy parsing."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": self._get_module_category(record.name),
            "message": record.getMessage(),
            "filename": record.filename,
            "lineno": record.lineno
        }
        
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_entry, ensure_ascii=False)
    
    def _get_module_category(self, logger_name: str) -> str:
        """Map logger name to module category."""
        for module, prefixes in LOG_MODULES.items():
            for prefix in prefixes:
                if logger_name.startswith(prefix):
                    return module
        return "other"


class InMemoryLogHandler(logging.Handler):
    """Handler that keeps logs in memory for quick access via API."""
    
    _buffers: Dict[str, deque] = {}
    _all_buffer: deque = deque(maxlen=LOG_BUFFER_SIZE * 2)
    
    def __init__(self):
        super().__init__()
        # Initialize buffers for each module
        for module in list(LOG_MODULES.keys()) + ["other"]:
            if module not in InMemoryLogHandler._buffers:
                InMemoryLogHandler._buffers[module] = deque(maxlen=LOG_BUFFER_SIZE)
    
    def emit(self, record: logging.LogRecord):
        try:
            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "module": self._get_module_category(record.name),
                "message": record.getMessage(),
                "filename": record.filename,
                "lineno": record.lineno
            }
            
            if record.exc_info:
                log_entry["exception"] = self.format(record)
            
            # Add to module-specific buffer
            module = log_entry["module"]
            if module in InMemoryLogHandler._buffers:
                InMemoryLogHandler._buffers[module].append(log_entry)
            
            # Add to all buffer
            InMemoryLogHandler._all_buffer.append(log_entry)
            
        except Exception:
            self.handleError(record)
    
    def _get_module_category(self, logger_name: str) -> str:
        """Map logger name to module category."""
        for module, prefixes in LOG_MODULES.items():
            for prefix in prefixes:
                if logger_name.startswith(prefix):
                    return module
        return "other"
    
    @classmethod
    def get_logs(
        cls,
        module: str = "all",
        level: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict:
        """Get logs from memory buffer with filtering."""
        
        # Select buffer
        if module == "all":
            logs = list(cls._all_buffer)
        elif module in cls._buffers:
            logs = list(cls._buffers[module])
        else:
            logs = []
        
        # Reverse to get newest first
        logs = logs[::-1]
        
        # Filter by level
        if level:
            logs = [entry for entry in logs if entry["level"] == level.upper()]
        
        # Filter by search
        if search:
            search_lower = search.lower()
            logs = [entry for entry in logs if search_lower in entry["message"].lower()]
        
        total = len(logs)
        
        # Apply pagination
        logs = logs[offset:offset + limit]
        
        return {
            "logs": logs,
            "total": total,
            "offset": offset,
            "limit": limit,
            "module": module
        }
    
    @classmethod
    def get_stats(cls) -> Dict:
        """Get log statistics per module."""
        stats = {}
        for module, buffer in cls._buffers.items():
            logs = list(buffer)
            stats[module] = {
                "total": len(logs),
                "errors": sum(1 for entry in logs if entry["level"] == "ERROR"),
                "warnings": sum(1 for entry in logs if entry["level"] == "WARNING")
            }
        stats["all"] = {
            "total": len(cls._all_buffer),
            "errors": sum(1 for entry in cls._all_buffer if entry["level"] == "ERROR"),
            "warnings": sum(1 for entry in cls._all_buffer if entry["level"] == "WARNING")
        }
        return stats


def setup_logging(log_level: str = "INFO"):
    """
    Configure logging with:
    - Console output (colored)
    - File output (JSON format, rotating)
    - In-memory buffer for API access
    """
    # Create log directory
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler (human-readable)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)
    
    # File handler for all logs (JSON, rotating)
    all_file_handler = RotatingFileHandler(
        LOG_DIR / "all.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=7,
        encoding="utf-8"
    )
    all_file_handler.setLevel(log_level)
    all_file_handler.setFormatter(JsonFormatter())
    root_logger.addHandler(all_file_handler)
    
    # In-memory handler for API access
    memory_handler = InMemoryLogHandler()
    memory_handler.setLevel(log_level)
    root_logger.addHandler(memory_handler)
    
    # Reduce noise from external libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    
    logging.info("Logging system initialized")


def get_available_modules() -> List[str]:
    """Get list of available log modules."""
    return ["all"] + list(LOG_MODULES.keys()) + ["other"]
