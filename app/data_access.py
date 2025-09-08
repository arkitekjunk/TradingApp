import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Text, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from loguru import logger

from app.config import settings

Base = declarative_base()

class Setting(Base):
    __tablename__ = "settings"
    
    key = Column(String, primary_key=True)
    value = Column(Text)

class Security(Base):
    __tablename__ = "securities"
    
    security_id = Column(String, primary_key=True)
    symbol = Column(String, unique=True, nullable=False)
    first_seen = Column(DateTime(timezone=True))
    last_seen = Column(DateTime(timezone=True))
    status = Column(String, default="active")

class Signal(Base):
    __tablename__ = "signals"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    tf = Column(String, nullable=False)
    ts = Column(DateTime(timezone=True), nullable=False)
    rule = Column(String, nullable=False)
    details = Column(JSON)


class Reconciliation(Base):
    __tablename__ = "reconciliations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    tf = Column(String, nullable=False)
    session_date = Column(String, nullable=False)  # YYYY-MM-DD
    bars_updated = Column(Integer, default=0)
    reconciled_at = Column(DateTime(timezone=True), nullable=False)
    

class BackfillQueue(Base):
    __tablename__ = "backfill_queue"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    priority = Column(Integer, default=0)  # Higher = more urgent
    scheduled_for = Column(DateTime(timezone=True), nullable=False)
    status = Column(String, default="pending")  # pending, processing, completed, failed
    created_at = Column(DateTime(timezone=True), nullable=False)
    attempts = Column(Integer, default=0)

class DatabaseManager:
    def __init__(self, db_url: str = None):
        self.db_url = db_url or settings.database_url
        self.engine = create_engine(self.db_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def get_session(self) -> Session:
        return self.SessionLocal()
    
    def get_setting(self, key: str, default: str = None) -> str:
        with self.get_session() as session:
            setting = session.query(Setting).filter(Setting.key == key).first()
            return setting.value if setting else default
    
    def set_setting(self, key: str, value: str):
        with self.get_session() as session:
            setting = session.query(Setting).filter(Setting.key == key).first()
            if setting:
                setting.value = value
            else:
                setting = Setting(key=key, value=value)
                session.add(setting)
            session.commit()
    
    def get_all_settings(self) -> Dict[str, str]:
        with self.get_session() as session:
            settings = session.query(Setting).all()
            return {s.key: s.value for s in settings}
    
    def update_security(self, symbol: str):
        with self.get_session() as session:
            security = session.query(Security).filter(Security.symbol == symbol).first()
            now = datetime.now(timezone.utc)
            
            if security:
                security.last_seen = now
            else:
                security = Security(
                    security_id=symbol,
                    symbol=symbol,
                    first_seen=now,
                    last_seen=now
                )
                session.add(security)
            
            session.commit()
    
    def add_signal(self, symbol: str, tf: str, ts: datetime, rule: str, details: Dict[str, Any]):
        with self.get_session() as session:
            signal = Signal(
                symbol=symbol,
                tf=tf,
                ts=ts,
                rule=rule,
                details=details
            )
            session.add(signal)
            session.commit()
    
    def get_signals(self, symbol: str = None, tf: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        with self.get_session() as session:
            query = session.query(Signal)
            
            if symbol:
                query = query.filter(Signal.symbol == symbol)
            if tf:
                query = query.filter(Signal.tf == tf)
            
            signals = query.order_by(Signal.ts.desc()).limit(limit).all()
            
            return [
                {
                    "id": s.id,
                    "symbol": s.symbol,
                    "tf": s.tf,
                    "ts": s.ts.isoformat(),
                    "rule": s.rule,
                    "details": s.details
                }
                for s in signals
            ]
    
    def add_reconciliation(self, symbol: str, tf: str, session_date: str, bars_updated: int):
        """Record a reconciliation event."""
        with self.get_session() as session:
            reconciliation = Reconciliation(
                symbol=symbol,
                tf=tf,
                session_date=session_date,
                bars_updated=bars_updated,
                reconciled_at=datetime.now(timezone.utc)
            )
            session.add(reconciliation)
            session.commit()
    
    def get_last_reconcile_date(self, symbol: str = None) -> Optional[str]:
        """Get the last reconciliation date (YYYY-MM-DD) for a symbol or globally."""
        with self.get_session() as session:
            query = session.query(Reconciliation)
            if symbol:
                query = query.filter(Reconciliation.symbol == symbol)
            
            last_reconcile = query.order_by(Reconciliation.reconciled_at.desc()).first()
            return last_reconcile.session_date if last_reconcile else None
    
    def add_to_backfill_queue(self, symbol: str, priority: int = 0, scheduled_for: datetime = None):
        """Add a symbol to the backfill queue."""
        if scheduled_for is None:
            scheduled_for = datetime.now(timezone.utc)
            
        with self.get_session() as session:
            # Check if already queued
            existing = session.query(BackfillQueue).filter(
                BackfillQueue.symbol == symbol,
                BackfillQueue.status == "pending"
            ).first()
            
            if not existing:
                queue_item = BackfillQueue(
                    symbol=symbol,
                    priority=priority,
                    scheduled_for=scheduled_for,
                    created_at=datetime.now(timezone.utc)
                )
                session.add(queue_item)
                session.commit()
    
    def get_backfill_queue_size(self) -> int:
        """Get the number of pending items in the backfill queue."""
        with self.get_session() as session:
            return session.query(BackfillQueue).filter(
                BackfillQueue.status == "pending"
            ).count()
    
    def get_next_backfill_symbols(self, limit: int = 10) -> List[str]:
        """Get the next symbols to backfill, respecting priority and schedule."""
        with self.get_session() as session:
            now = datetime.now(timezone.utc)
            items = session.query(BackfillQueue).filter(
                BackfillQueue.status == "pending",
                BackfillQueue.scheduled_for <= now
            ).order_by(
                BackfillQueue.priority.desc(),
                BackfillQueue.created_at.asc()
            ).limit(limit).all()
            
            return [item.symbol for item in items]
    
    def mark_backfill_processing(self, symbol: str):
        """Mark a symbol as currently being processed for backfill."""
        with self.get_session() as session:
            item = session.query(BackfillQueue).filter(
                BackfillQueue.symbol == symbol,
                BackfillQueue.status == "pending"
            ).first()
            
            if item:
                item.status = "processing"
                item.attempts += 1
                session.commit()
    
    def mark_backfill_completed(self, symbol: str):
        """Mark a symbol's backfill as completed."""
        with self.get_session() as session:
            item = session.query(BackfillQueue).filter(
                BackfillQueue.symbol == symbol,
                BackfillQueue.status == "processing"
            ).first()
            
            if item:
                item.status = "completed"
                session.commit()

class CandleStorage:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.candles_dir = self.data_dir / "candles"
        self.candles_dir.mkdir(exist_ok=True)
    
    def _get_parquet_path(self, symbol: str, tf: str) -> Path:
        symbol_dir = self.candles_dir / symbol
        symbol_dir.mkdir(exist_ok=True)
        return symbol_dir / f"{tf}.parquet"
    
    def write_candles(self, symbol: str, tf: str, candles: pd.DataFrame, 
                     reconcile_mode: bool = False) -> int:
        """Write candles to parquet file with enhanced deduplication and reconciliation.
        
        Returns:
            Number of bars that were actually updated/added.
        """
        parquet_path = self._get_parquet_path(symbol, tf)
        bars_changed = 0
        
        # Ensure proper schema
        if not candles.empty:
            candles = candles.copy()
            candles['ts'] = pd.to_datetime(candles['ts'], utc=True)
            candles = candles.set_index('ts').sort_index()
            
            # Read existing data if it exists
            if parquet_path.exists():
                try:
                    existing = pd.read_parquet(parquet_path)
                    existing.index = pd.to_datetime(existing.index, utc=True)
                    
                    if reconcile_mode:
                        # In reconcile mode, track what actually changed
                        original_size = len(existing)
                        
                        # Identify overlapping timestamps
                        overlap_mask = candles.index.isin(existing.index)
                        new_data = candles[~overlap_mask]
                        update_data = candles[overlap_mask]
                        
                        # Count actual changes in overlapping data
                        for ts in update_data.index:
                            if ts in existing.index:
                                old_row = existing.loc[ts]
                                new_row = update_data.loc[ts]
                                # Check if values actually changed (accounting for floating point precision)
                                if not old_row.equals(new_row):
                                    bars_changed += 1
                        
                        # Add new bars count
                        bars_changed += len(new_data)
                    
                    # Combine and deduplicate (keep='last' for reconcile mode, 'first' for normal)
                    combined = pd.concat([existing, candles])
                    keep_strategy = 'last' if reconcile_mode else 'first'
                    combined = combined[~combined.index.duplicated(keep=keep_strategy)]
                    combined = combined.sort_index()
                    
                    candles = combined
                    
                except Exception as e:
                    logger.warning(f"Error reading existing parquet for {symbol}/{tf}: {e}")
                    bars_changed = len(candles)  # Assume all are new if we can't read existing
            else:
                bars_changed = len(candles)
            
            # Write to parquet with metadata if reconciling
            metadata = {}
            if reconcile_mode:
                metadata['reconciled_at'] = datetime.now(timezone.utc).isoformat()
            
            # Create PyArrow table with metadata
            table = pa.Table.from_pandas(candles)
            if metadata:
                # Add metadata to the schema
                schema = table.schema
                schema = schema.with_metadata(metadata)
                table = table.cast(schema)
            
            pq.write_table(table, parquet_path, compression='snappy')
            logger.debug(f"Wrote {len(candles)} candles to {parquet_path} (changed: {bars_changed})")
            
        return bars_changed
    
    def read_candles(self, symbol: str, tf: str, 
                    start_time: datetime = None, 
                    end_time: datetime = None) -> pd.DataFrame:
        """Read candles from parquet file."""
        parquet_path = self._get_parquet_path(symbol, tf)
        
        if not parquet_path.exists():
            return pd.DataFrame(columns=['o', 'h', 'l', 'c', 'v'])
        
        try:
            df = pd.read_parquet(parquet_path)
            df.index = pd.to_datetime(df.index, utc=True)
            
            # Filter by time range if specified
            if start_time:
                df = df[df.index >= start_time]
            if end_time:
                df = df[df.index <= end_time]
            
            return df.sort_index()
            
        except Exception as e:
            logger.error(f"Error reading candles for {symbol}/{tf}: {e}")
            return pd.DataFrame(columns=['o', 'h', 'l', 'c', 'v'])
    
    def get_last_timestamp(self, symbol: str, tf: str) -> Optional[datetime]:
        """Get the timestamp of the last candle for a symbol/timeframe."""
        try:
            df = self.read_candles(symbol, tf)
            if df.empty:
                return None
            return df.index[-1].to_pydatetime()
        except Exception as e:
            logger.error(f"Error getting last timestamp for {symbol}/{tf}: {e}")
            return None
    
    def get_symbols_with_data(self) -> List[str]:
        """Get list of symbols that have data stored."""
        symbols = []
        for symbol_dir in self.candles_dir.iterdir():
            if symbol_dir.is_dir():
                symbols.append(symbol_dir.name)
        return symbols
    
    def reconcile_session_data(self, symbol: str, tf: str, official_candles: pd.DataFrame, 
                             session_date: str) -> int:
        """
        Reconcile live-built bars with official adjusted data for a trading session.
        
        Args:
            symbol: Symbol to reconcile
            tf: Timeframe (e.g., '5m')
            official_candles: Official adjusted candles from REST API
            session_date: Session date in YYYY-MM-DD format
            
        Returns:
            Number of bars that were updated
        """
        try:
            bars_updated = self.write_candles(symbol, tf, official_candles, reconcile_mode=True)
            
            # Record reconciliation in database
            db.add_reconciliation(symbol, tf, session_date, bars_updated)
            
            if bars_updated > 0:
                logger.info(f"Reconciled {bars_updated} bars for {symbol}/{tf} on {session_date}")
            
            return bars_updated
            
        except Exception as e:
            logger.error(f"Error reconciling session data for {symbol}/{tf} on {session_date}: {e}")
            return 0
    
    def get_session_data(self, symbol: str, tf: str, session_start: datetime, 
                        session_end: datetime) -> pd.DataFrame:
        """
        Get candle data for a specific trading session.
        
        Args:
            symbol: Symbol to query
            tf: Timeframe (e.g., '5m') 
            session_start: Session start datetime (UTC)
            session_end: Session end datetime (UTC)
            
        Returns:
            DataFrame with session candles
        """
        return self.read_candles(symbol, tf, session_start, session_end)

# Global instances
db = DatabaseManager()
storage = CandleStorage()

# Add pytz dependency check
try:
    import pytz
except ImportError:
    logger.warning("pytz not found. Market calendar features may not work correctly. Install with: pip install pytz")