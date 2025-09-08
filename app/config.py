import os
import yaml
from typing import Dict, Any
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    finnhub_api_key: str = Field(..., env="FINNHUB_API_KEY")
    discord_webhook_url: str = Field("", env="DISCORD_WEBHOOK_URL")
    telegram_bot_token: str = Field("", env="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field("", env="TELEGRAM_CHAT_ID")
    host: str = Field("0.0.0.0", env="HOST")
    port: int = Field(8000, env="PORT")
    debug: bool = Field(False, env="DEBUG")
    database_url: str = Field("sqlite:///./trading.db", env="DATABASE_URL")
    
    # New settings for enhanced functionality
    include_extended_hours: bool = Field(False, env="INCLUDE_EXTENDED_HOURS")
    max_lookback_days: int = Field(60, env="MAX_LOOKBACK_DAYS")
    enable_backlog_scheduling: bool = Field(True, env="ENABLE_BACKLOG_SCHEDULING")
    
    class Config:
        env_file = ".env"

def load_yaml_config(config_path: str = "settings.yaml") -> Dict[str, Any]:
    """Load configuration from YAML file."""
    config_file = Path(config_path)
    if not config_file.exists():
        return {}
    
    with open(config_file, 'r') as f:
        return yaml.safe_load(f) or {}

def get_config_value(key_path: str, default: Any = None) -> Any:
    """Get configuration value using dot notation (e.g., 'defaults.lookback_days')."""
    config = load_yaml_config()
    
    keys = key_path.split('.')
    current = config
    
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    
    return current

def validate_settings(settings_obj: Settings) -> None:
    """Validate critical settings and raise errors for invalid configurations."""
    if not settings_obj.finnhub_api_key or settings_obj.finnhub_api_key == "your_api_key_here":
        raise ValueError("FINNHUB_API_KEY is required and must be set to a valid API key")
    
    # Validate lookback days to prevent quota exhaustion
    if not hasattr(settings_obj, 'max_lookback_days'):
        settings_obj.max_lookback_days = 60
        
    # Extended hours validation
    if not hasattr(settings_obj, 'include_extended_hours'):
        settings_obj.include_extended_hours = False

settings = Settings()
validate_settings(settings)