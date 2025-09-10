#!/usr/bin/env python3
"""
Simple backfill script for NASDAQ stocks using Yahoo Finance.
This bypasses the need for Finnhub API key and directly populates historical data.
"""

import asyncio
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from app.yahoo_provider import yahoo_provider
from app.data_access import storage
from app.universe import universe_manager

async def backfill_symbol(symbol: str, days: int = 30):
    """Backfill historical data for a single symbol."""
    print(f"Backfilling {symbol}...")
    
    # Calculate date range
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)
    
    try:
        # Get data from Yahoo Finance
        df = await yahoo_provider.get_historical_data(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            interval="5m"
        )
        
        if df is not None and not df.empty:
            # Store the data
            storage.write_candles(symbol, "5m", df)
            print(f"✅ {symbol}: Saved {len(df)} candles")
            return True
        else:
            print(f"❌ {symbol}: No data received")
            return False
            
    except Exception as e:
        print(f"❌ {symbol}: Error - {e}")
        return False

async def main():
    """Main backfill process."""
    print("🚀 Starting NASDAQ stocks backfill...")
    print("📊 Using Yahoo Finance (no API key required)")
    
    # Get current universe symbols
    symbols = await universe_manager.get_universe_symbols()
    print(f"📈 Found {len(symbols)} symbols to backfill")
    
    # Backfill each symbol
    success_count = 0
    total_count = len(symbols)
    
    for i, symbol in enumerate(symbols, 1):
        print(f"\n[{i}/{total_count}] Processing {symbol}")
        
        success = await backfill_symbol(symbol, days=60)  # 60 days of data
        if success:
            success_count += 1
            
        # Small delay to be nice to Yahoo Finance
        await asyncio.sleep(0.1)
    
    print(f"\n🎉 Backfill complete!")
    print(f"✅ Success: {success_count}/{total_count} symbols")
    print(f"❌ Failed: {total_count - success_count} symbols")
    print(f"\n💡 Refresh your browser to see the new data!")

if __name__ == "__main__":
    asyncio.run(main())