import logging
import os
import shutil
import uuid
from datetime import datetime
from logging.handlers import RotatingFileHandler
from multiprocessing import current_process
from pathlib import Path
from typing import Optional

# Variable global para el ID de sesión
_SESSION_ID: Optional[str] = None
MAX_SESSIONS = 5


def clean_old_sessions(logs_base_dir: Path) -> None:
    """
    Keeps only the most recent MAX_SESSIONS session directories. 
    Deletes the oldest ones if the limit is exceeded.
    """
    try:
        # Get all session directories
        session_dirs = [
            d
            for d in logs_base_dir.iterdir()
            if d.is_dir() and d.name.startswith("video_session_")
        ]

        # Sort by creation date (oldest first)
        session_dirs.sort(key=lambda x: x.stat().st_ctime)

        # Delete old sessions if there are more than the limit
        while len(session_dirs) >= MAX_SESSIONS:
            oldest_dir = session_dirs.pop(0)
            try:
                shutil.rmtree(oldest_dir)
                logging.debug(f"Old session deleted: {oldest_dir}")
            except Exception as e:
                logging.error(f"Error deleting old session {oldest_dir}: {e}")

    except Exception as e:
        logging.error(f"Error during cleanup of old sessions: {e}")

def generate_session_id() -> str:
    """Generate a unique session ID for video processing."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Usar los primeros 8 caracteres del UUID para mantenerlo corto pero único
    short_uuid = str(uuid.uuid4())[:8]
    return f"video_session_{timestamp}_{short_uuid}"


def init_session(session_id: Optional[str] = None) -> str:
    """Initialize global session ID"""
    global _SESSION_ID
    if session_id is not None:
        _SESSION_ID = session_id
    elif _SESSION_ID is None:
        _SESSION_ID = generate_session_id()

        # Limpiar sesiones antiguas solo cuando se crea una nueva
        logs_base_dir = Path.home() / ".subauto" / "logs"
        if logs_base_dir.exists():
            clean_old_sessions(logs_base_dir)

    return _SESSION_ID


def get_log_directory() -> Path:
    """Gets the base directory for logs."""
    session_id = init_session()
    log_dir = Path.home() / ".subauto" / "logs" / session_id
    os.makedirs(str(log_dir), exist_ok=True)
    return log_dir


def get_log_file_path(process_name: Optional[str] = None) -> Path:
    """Generates the log file path based on the process name."""
    if process_name is None:
        process = current_process()
        process_name = process.name

    if process_name == "MainProcess":
        filename = "main.log"
    else:
        # Extraer solo el número del worker del nombre del proceso
        worker_num = process_name.split("-")[1] if "-" in process_name else "0"
        filename = f"worker_{worker_num}.log"

    log_path = get_log_directory() / filename
    return log_path


def create_logger(name: str, log_file_path: Path) -> logging.Logger:
    """Create and configure a logger instance."""
    
    # Set logger level
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Remove existing handlers if any
    if logger.handlers:
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(processName)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler
    try:
        file_handler = RotatingFileHandler(
            str(log_file_path),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
            delay=True,  # Only create file when first record is written
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Error creating file handler: {e}")

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


def init_worker_logging(session_id: Optional[str] = None) -> None:
    """Initialize logging for worker processes."""

    # Initialize session with the provided session_id
    init_session(session_id)
    process = current_process()
    log_file_path = get_log_file_path(process.name)
    logger = create_logger(f"worker.{process.name}", log_file_path)
    logger.debug(f"Initialized logging for worker {process.name}")
    


def get_process_logger() -> logging.Logger:
    """Get the logger for the current process."""
    process = current_process()
    logger_name = f"worker.{process.name}"

    # Create new logger if it doesn't exist
    if logger_name not in logging.Logger.manager.loggerDict:
        log_file_path = get_log_file_path(process.name)
        logger = create_logger(logger_name, log_file_path)
        logger.debug(f"Created new logger for {process.name}")
        return logger

    return logging.getLogger(logger_name)
