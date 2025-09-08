import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import httpx
from loguru import logger

from app.config import settings

class AlertManager:
    """Handles sending alerts to Discord and Telegram."""
    
    def __init__(self):
        self.discord_webhook_url = settings.discord_webhook_url
        self.telegram_bot_token = settings.telegram_bot_token
        self.telegram_chat_id = settings.telegram_chat_id
        
        self.http_timeout = 10.0
    
    async def send_signal_alert(self, signal: Dict[str, Any]):
        """Send alert for a trading signal to configured channels."""
        if not any([self.discord_webhook_url, 
                   self.telegram_bot_token and self.telegram_chat_id]):
            logger.debug("No alert channels configured, skipping alert")
            return
        
        try:
            # Create alert message
            message = self._format_signal_message(signal)
            
            # Send to configured channels
            tasks = []
            
            if self.discord_webhook_url:
                tasks.append(self._send_discord_alert(message, signal))
            
            if self.telegram_bot_token and self.telegram_chat_id:
                tasks.append(self._send_telegram_alert(message))
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                logger.info(f"Alert sent for {signal['symbol']} signal")
            
        except Exception as e:
            logger.error(f"Error sending signal alert: {e}")
    
    def _format_signal_message(self, signal: Dict[str, Any]) -> str:
        """Format signal data into a readable message."""
        try:
            symbol = signal['symbol']
            details = signal['details']
            timestamp = signal['timestamp']
            
            # Basic message
            message = f"🚀 **Long Signal: {symbol}**\n\n"
            message += f"⏰ Time: {timestamp}\n"
            message += f"💰 Price: ${details['price']:.2f}\n"
            message += f"📊 RSI: {details['rsi']:.1f}\n"
            message += f"📈 EMA9: ${details['ema_9']:.2f}\n"
            message += f"📉 EMA21: ${details['ema_21']:.2f}\n"
            message += f"🎯 VWAP: ${details['vwap']:.2f}\n"
            message += f"📦 RVOL: {details['rvol']:.2f}x\n"
            message += f"💹 Volume: {details['volume']:,}\n"
            
            return message
            
        except Exception as e:
            logger.error(f"Error formatting signal message: {e}")
            return f"Trading signal for {signal.get('symbol', 'Unknown')}"
    
    async def _send_discord_alert(self, message: str, signal: Dict[str, Any]):
        """Send alert to Discord via webhook."""
        try:
            # Create Discord embed
            embed = {
                "title": f"🚀 Long Signal: {signal['symbol']}",
                "description": message,
                "color": 0x00ff00,  # Green color
                "timestamp": signal['timestamp'],
                "fields": []
            }
            
            details = signal['details']
            
            # Add fields for key metrics
            embed["fields"].extend([
                {"name": "Price", "value": f"${details['price']:.2f}", "inline": True},
                {"name": "RSI", "value": f"{details['rsi']:.1f}", "inline": True},
                {"name": "RVOL", "value": f"{details['rvol']:.2f}x", "inline": True},
                {"name": "EMA 9/21", "value": f"${details['ema_9']:.2f} / ${details['ema_21']:.2f}", "inline": True},
                {"name": "VWAP", "value": f"${details['vwap']:.2f}", "inline": True},
                {"name": "Volume", "value": f"{details['volume']:,}", "inline": True},
            ])
            
            payload = {
                "username": "Trading Bot",
                "embeds": [embed]
            }
            
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                response = await client.post(
                    self.discord_webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                
            logger.debug(f"Discord alert sent for {signal['symbol']}")
            
        except Exception as e:
            logger.error(f"Error sending Discord alert: {e}")
    
    async def _send_telegram_alert(self, message: str):
        """Send alert to Telegram via bot API."""
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }
            
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                
            logger.debug("Telegram alert sent")
            
        except Exception as e:
            logger.error(f"Error sending Telegram alert: {e}")
    
    async def send_status_alert(self, status: str, message: str):
        """Send a status update alert (e.g., worker started/stopped)."""
        try:
            if not any([self.discord_webhook_url, 
                       self.telegram_bot_token and self.telegram_chat_id]):
                return
            
            alert_message = f"📊 **Trading System Status**\n\n"
            alert_message += f"Status: {status}\n"
            alert_message += f"Message: {message}\n"
            alert_message += f"Time: {datetime.now(timezone.utc).isoformat()}"
            
            # Send to configured channels
            tasks = []
            
            if self.discord_webhook_url:
                tasks.append(self._send_discord_status(status, alert_message))
            
            if self.telegram_bot_token and self.telegram_chat_id:
                tasks.append(self._send_telegram_alert(alert_message))
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                
        except Exception as e:
            logger.error(f"Error sending status alert: {e}")
    
    async def _send_discord_status(self, status: str, message: str):
        """Send status alert to Discord."""
        try:
            color = 0x00ff00 if status == "started" else 0xff9900 if status == "stopped" else 0xff0000
            
            embed = {
                "title": "📊 Trading System Status",
                "description": message,
                "color": color,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            payload = {
                "username": "Trading Bot",
                "embeds": [embed]
            }
            
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                response = await client.post(
                    self.discord_webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                
        except Exception as e:
            logger.error(f"Error sending Discord status alert: {e}")
    
    def update_settings(self, discord_webhook: str = None, 
                       telegram_bot_token: str = None, 
                       telegram_chat_id: str = None):
        """Update alert settings."""
        if discord_webhook is not None:
            self.discord_webhook_url = discord_webhook
        
        if telegram_bot_token is not None:
            self.telegram_bot_token = telegram_bot_token
            
        if telegram_chat_id is not None:
            self.telegram_chat_id = telegram_chat_id
    
    def get_configured_channels(self) -> Dict[str, bool]:
        """Get which alert channels are configured."""
        return {
            'discord': bool(self.discord_webhook_url),
            'telegram': bool(self.telegram_bot_token and self.telegram_chat_id)
        }

# Global alert manager instance
alert_manager = AlertManager()