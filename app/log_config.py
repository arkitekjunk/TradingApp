import sys
from pathlib import Path
from loguru import logger
from datetime import datetime

def setup_logging(log_level: str = "INFO", log_dir: str = "logs"):
    """Configure structured logging with rotation."""
    
    # Remove default handler
    logger.remove()
    
    # Create logs directory
    Path(log_dir).mkdir(exist_ok=True)
    
    # Console handler with colors
    logger.add(
        sys.stdout,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "<level>{message}</level>",
        colorize=True
    )
    
    # File handler with rotation
    logger.add(
        f"{log_dir}/trading_{{time:YYYY-MM-DD}}.log",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation="1 day",
        retention="30 days",
        compression="zip",
        serialize=False
    )
    
    # Error file handler
    logger.add(
        f"{log_dir}/errors_{{time:YYYY-MM-DD}}.log",
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}\n{exception}",
        rotation="1 day",
        retention="30 days",
        compression="zip",
    )
    
    logger.info(f"Logging initialized at level {log_level}")
    return logger

# Initialize logger
setup_logging()