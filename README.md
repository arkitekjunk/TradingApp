# Trading App

A production-ready real-time trading application that aggregates market data from Finnhub, processes technical indicators, and provides live charting with signal alerts. Built with enterprise-grade reliability, rate limiting, and comprehensive monitoring.

## Features

- **Real-time Data**: Live WebSocket streaming with gap-filling on reconnection and graceful shutdown
- **Hybrid Data Architecture**: Yahoo Finance for unlimited historical data + Finnhub for real-time streaming
- **Multi-Timeframe Charts**: Interactive TradingView-style charts with 5m, 15m, 1h, 4h, 1d timeframe support
- **Real-time Aggregation**: Dynamic timeframe conversion from 5-minute base data using pandas resample
- **Rate-Limited Streaming**: Quota-safe WebSocket streaming (50 symbols on free plan) with connection monitoring
- **Session-Aware VWAP**: Calendar-aware VWAP that resets at 9:30 AM ET with NYSE/NASDAQ holiday support
- **Storage Robustness**: Prevents data loss during symbol churn with proper deduplication and partial candle persistence
- **Health & Metrics**: Comprehensive health monitoring with quota tracking and real-time status indicators
- **Market Calendar**: Complete NYSE/NASDAQ holiday calendar (2024-2026) with early close detection
- **Dynamic Universe**: Automatically fetches top 50 symbols with fallback support
- **Professional UI**: React-based trading interface with real-time charts, watchlist, and timeframe switching
- **Alert System**: Discord and Telegram webhook notifications
- **Extended Hours**: Optional pre-market (4:00-9:30 AM ET) and after-hours (4:00-8:00 PM ET) inclusion
- **Production Ready**: Comprehensive error handling, logging, and browser cache management

## Tech Stack

### Backend
- **Python 3.11+** with FastAPI and uvicorn
- **Data Sources**: Yahoo Finance (yfinance) for historical data + Finnhub WebSocket for real-time
- **Data Processing**: pandas with resample for timeframe aggregation, pandas-ta for technical indicators
- **Storage**: Parquet files (pyarrow) + SQLite (SQLAlchemy) with robust deduplication
- **Rate Limiting**: WebSocket connection limits and streaming quota management
- **Market Calendar**: `pytz` timezone handling with comprehensive NYSE/NASDAQ holidays
- **Configuration**: python-dotenv, PyYAML with validation
- **Logging**: loguru with structured, rotating logs
- **Browser Compatibility**: Cache-busting headers for seamless frontend updates

### Frontend
- **React 18** with TypeScript and Vite
- **Styling**: TailwindCSS for responsive design
- **Charts**: Lightweight Charts (TradingView open-source) with multi-timeframe support
- **Icons**: Lucide React
- **Real-time Features**: Live WebSocket status, symbol watchlist, and dynamic timeframe switching
- **Browser Optimization**: Cache-busting for seamless updates and /charts endpoint for reliable access

### Infrastructure
- **Docker** with multi-stage builds
- **Docker Compose** for orchestration
- **Makefile** for development workflows

## Quick Start

### Local Development

1. **Clone and setup**:
   ```bash
   git clone <repository>
   cd trading-app
   make setup
   ```

2. **Configure environment**:
   ```bash
   # Edit .env file with your Finnhub API key
   vim .env
   ```
   
   Required:
   ```
   FINNHUB_API_KEY=your_api_key_here
   ```

3. **Start development**:
   ```bash
   make dev
   ```
   
   This starts:
   - Backend API at http://localhost:8000
   - Frontend dev server at http://localhost:3000
   - Charts interface at http://localhost:3000/charts (bypass cache)

### Docker Deployment

1. **Configure environment**:
   ```bash
   cp .env.sample .env
   # Edit .env with your configuration
   ```

2. **Deploy with Docker Compose**:
   ```bash
   make docker-run
   ```
   
   Access the app at http://localhost:8080

## Configuration

### Environment Variables (.env)

```bash
# Required
FINNHUB_API_KEY=your_finnhub_api_key_here

# Optional - Alert webhooks
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
TELEGRAM_BOT_TOKEN=1234567890:ABC...
TELEGRAM_CHAT_ID=-1001234567890

# Server (optional)
HOST=0.0.0.0
PORT=8000
DEBUG=false
DATABASE_URL=sqlite:///./trading.db

# Rate Limiting (optional - defaults shown)
DAILY_API_LIMIT=500      # Finnhub daily quota
MINUTE_API_LIMIT=60      # Finnhub per-minute limit
```

### Application Settings (settings.yaml)

```yaml
defaults:
  lookback_days: 30               # Historical data backfill period
  base_timeframe: "5m"            # Primary timeframe  
  universe_symbol: "^NDX"         # Index for constituents (NASDAQ-100)
  universe_cache_hours: 12        # How long to cache universe
  include_extended_hours: false   # Include pre/post market hours
  max_lookback_days: 365          # Maximum allowed lookback (safety limit)

indicators:
  ema_fast: 9                     # Fast EMA period
  ema_slow: 21                    # Slow EMA period
  rsi_period: 14                  # RSI calculation period
  bb_period: 20                   # Bollinger Bands period
  bb_std: 2.0                     # Bollinger Bands standard deviation

signals:
  long_trigger:
    ema_cross_above: true         # EMA9 > EMA21 crossover
    rsi_min: 50                  # RSI above 50
    price_above_vwap: true       # Price above session VWAP (resets at 9:30 AM ET)
    min_rvol: 2.0                # Relative volume >= 2.0x

reconciliation:
  enabled: true                   # Enable daily EOD reconciliation
  run_time: "17:30"              # Run at 5:30 PM ET (after market close)
  lookback_days: 1               # Days to reconcile (1 = previous session only)
```

## API Endpoints

### Core Endpoints

- `GET /` - Serve React application
- `GET /healthz` - Health check and comprehensive system status with quota tracking
- `GET /docs` - Interactive API documentation

### Settings Management

- `GET /api/settings` - Get current settings
- `POST /api/settings` - Update settings with validation

### Worker Control

- `POST /api/control/start` - Start data worker (backfill + streaming)
- `POST /api/control/stop` - Stop data worker with graceful shutdown

### Data Access

- `GET /api/universe` - Get current universe symbols
- `POST /api/universe/refresh` - Force refresh universe  
- `GET /api/candles?symbol=AAPL&tf=5m` - Get candle data (supports 5m, 15m, 1h, 4h, 1d)
- `GET /api/signals` - Get recent trading signals
- `GET /charts` - Serve charts interface with cache-busting headers

### Production Operations

- `POST /api/reconciliation/run` - Trigger manual EOD reconciliation
- `GET /api/reconciliation/status` - Get reconciliation history and status
- `POST /api/backfill/queue` - Add symbols to backfill queue when quota exhausted
- `GET /api/metrics/quota` - Get detailed API quota usage and rate limiting status

## Architecture

### Data Flow

1. **Universe Management**: Fetches top 50 symbols with fallback support when API quota exhausted
2. **Historical Data**: Yahoo Finance provides unlimited 60-day 5-minute historical data
3. **Real-time Streaming**: Finnhub WebSocket for live trade data (50 concurrent symbols on free plan)
4. **Timeframe Aggregation**: Dynamic conversion from 5m base data to 15m, 1h, 4h, 1d using pandas resample
5. **Session-Aware Processing**: VWAP and indicators reset at market session boundaries (9:30 AM ET)
6. **Signal Processing**: Technical indicators calculated with session awareness and market calendar integration
7. **Chart Interface**: Interactive TradingView-style charts with real-time timeframe switching
8. **Alert Dispatch**: Webhooks sent to configured Discord/Telegram channels
9. **Health Monitoring**: Real-time WebSocket status and connection monitoring

### Storage Schema

**Parquet Files** (`data/candles/{symbol}/{tf}.parquet`):
```
ts: timestamp (UTC, nanoseconds)
o: open price
h: high price  
l: low price
c: close price
v: volume
```

**SQLite Tables**:
```sql
-- Application settings
settings(key TEXT PRIMARY KEY, value TEXT)

-- Symbol tracking and universe management  
securities(security_id TEXT PRIMARY KEY, symbol TEXT, first_seen TIMESTAMP, last_seen TIMESTAMP, status TEXT)

-- Trading signals with rule details
signals(id INTEGER PRIMARY KEY, symbol TEXT, tf TEXT, ts TIMESTAMP, rule TEXT, details JSON)

-- Rate limiting and quota tracking
rate_limits(date TEXT PRIMARY KEY, daily_calls INTEGER, daily_limit INTEGER, minute_calls INTEGER, minute_limit INTEGER, last_reset TIMESTAMP)

-- Backfill queue for quota management
backfill_queue(id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, priority INTEGER, queued_at TIMESTAMP, status TEXT)

-- EOD reconciliation audit trail
reconciliations(id INTEGER PRIMARY KEY AUTOINCREMENT, session_date TEXT, symbol TEXT, bars_fetched INTEGER, bars_updated INTEGER, timestamp TIMESTAMP)
```

## Signal Logic

### Long Trigger Conditions

All conditions must be met simultaneously:

1. **EMA Crossover**: EMA(9) crosses above EMA(21)
2. **RSI Momentum**: RSI(14) > 50
3. **Price vs VWAP**: Current price ≥ session VWAP  
4. **Volume**: Relative volume ≥ 2.0x (current vs 20-day average)

### Session VWAP

- **Calendar-Aware Reset**: Resets precisely at 9:30 AM ET using comprehensive NYSE/NASDAQ holiday calendar
- **Extended Hours Support**: Optional inclusion of pre-market (4:00-9:30 AM ET) and after-hours (4:00-8:00 PM ET)
- **Calculation**: Cumulative (Price × Volume) / cumulative Volume within session boundaries
- **Market Calendar Integration**: Properly handles holidays, weekends, and early close days (Christmas Eve, etc.)
- **Timezone Handling**: All calculations in Eastern Time, converted to UTC for storage

## Monitoring & Operations

### Health Monitoring

```bash
# Check comprehensive application status with quota tracking
make status

# View real-time stats and performance metrics  
make monitor

# Follow logs with structured output
make logs

# Check API quota usage
curl http://localhost:8000/api/metrics/quota

# Monitor backfill queue status
curl http://localhost:8000/healthz | jq '.backfill_queue_size'
```

### Data Management

```bash
# Backup trading data
make backup-data

# Reset database (development only)
make db-reset

# Clean all data (CAUTION)
make clean-data
```

### Docker Operations

```bash
# View logs
make docker-logs

# Rebuild containers
make docker-rebuild

# Stop services
make docker-stop
```

## Development

### Project Structure

```
trading-app/
├── app/                        # Backend Python application
│   ├── main.py                # FastAPI application with comprehensive health endpoint
│   ├── worker.py              # WebSocket worker with gap-filling and graceful shutdown
│   ├── data_access.py         # Storage layer with deduplication and reconciliation support
│   ├── indicators.py          # Session-aware technical analysis & VWAP
│   ├── rate_limiter.py        # Token bucket rate limiting with persistent tracking
│   ├── market_calendar.py     # NYSE/NASDAQ holiday calendar and session management
│   ├── reconciliation.py      # EOD reconciliation service for adjusted data alignment
│   ├── universe.py            # Index constituent management
│   ├── alerts.py              # Discord/Telegram webhooks
│   ├── config.py              # Configuration management with validation
│   └── logging.py             # Structured logging setup
├── ui/                        # React frontend with real-time status monitoring
│   ├── src/
│   │   ├── components/        # React components with quota display
│   │   ├── lib/              # API client & chart utilities
│   │   └── App.tsx           # Main application with comprehensive health dashboard
│   └── package.json          # Node.js dependencies
├── tests/                     # Comprehensive test suite
│   ├── test_integration.py    # End-to-end workflow integration tests
│   ├── test_rate_limiter.py   # Rate limiting functionality tests
│   ├── test_market_calendar.py # Market calendar and session tests
│   └── ...                   # Unit tests for all modules
├── data/                      # Data storage directory
├── Dockerfile                 # Production container
├── docker-compose.yml         # Container orchestration
├── Makefile                  # Development commands
├── requirements.txt          # Python dependencies (includes pytz)
└── settings.yaml             # Application configuration
```

### Testing

```bash
# Run complete test suite (unit + integration)
make test

# Run with coverage report
pytest --cov=app tests/

# Test specific module
pytest tests/test_aggregate_5m.py -v

# Run integration tests only
pytest tests/test_integration.py -v

# Test rate limiting functionality  
pytest tests/test_rate_limiter.py -v

# Test market calendar functionality
pytest tests/test_market_calendar.py -v
```

### Code Quality

```bash
# Run linters
make lint

# Format code
make format
```

## Deployment

### Production Checklist

1. **Environment Setup**:
   ```bash
   make deploy-check
   ```

2. **Security**:
   - Set strong database passwords
   - Use HTTPS with reverse proxy
   - Restrict Docker network access
   - Set proper file permissions

3. **Monitoring**:
   - Set up log aggregation and structured logging
   - Monitor disk usage (Parquet files grow)
   - Configure health check alerts with quota thresholds
   - Monitor API rate limits and backfill queue size
   - Set up alerts for failed reconciliations or WebSocket disconnections

4. **Backup Strategy**:
   - Regular data backups
   - Database snapshots
   - Configuration versioning

### Resource Requirements

**Minimum**:
- CPU: 2 cores
- RAM: 4GB
- Storage: 50GB SSD
- Network: Stable internet for WebSocket

**Recommended**:
- CPU: 4+ cores
- RAM: 8GB+
- Storage: 200GB+ SSD
- Network: Low-latency connection

## Troubleshooting

### Common Issues

**WebSocket Disconnections**:
- Check internet connectivity and WebSocket gap-filling logs
- Verify Finnhub API key validity and quota limits
- Review rate limiting and reconnection attempts in logs

**Missing Data / Incomplete Backfill**:
- Check API quota usage: `curl http://localhost:8000/healthz | jq '.rest_calls_today'`
- Review backfill queue status for symbols waiting due to quota exhaustion
- Verify symbol exists in universe and market calendar is working correctly

**High Memory Usage**:
- Large universes increase memory usage (monitor with health endpoint)
- Consider reducing lookback days or universe size
- Monitor Parquet file sizes and implement data archiving

**Signal Not Firing**:
- Check VWAP session resets are working correctly (9:30 AM ET boundaries)
- Verify all signal conditions in logs with session-aware calculations
- Review RSI/RVOL thresholds and ensure sufficient historical data for indicators

**Quota Exhaustion**:
- Monitor daily and per-minute API limits in health dashboard
- Check backfill queue for delayed symbol processing
- Consider upgrading Finnhub plan or adjusting universe size

**Reconciliation Issues**:
- Review EOD reconciliation logs for API errors or data mismatches
- Check reconciliation audit trail in database
- Verify market calendar is correctly identifying trading sessions

### Log Analysis

```bash
# Error logs and troubleshooting
grep ERROR logs/trading_*.log

# WebSocket connection and gap-filling events
grep "WebSocket\|gap" logs/trading_*.log

# Rate limiting and quota events
grep "rate_limit\|quota" logs/trading_*.log

# Signal events and VWAP session resets
grep "signal\|vwap\|session" logs/trading_*.log

# Reconciliation events
grep "reconcil" logs/trading_*.log

# Market calendar and holiday events
grep "holiday\|market.*closed" logs/trading_*.log
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Run the test suite and linters
5. Submit a pull request

## License

This project is licensed under the MIT License. See LICENSE file for details.

## Disclaimer

This software is for educational and research purposes only. Do not use for actual trading without thorough testing and risk management. Past performance does not guarantee future results. Trading involves substantial risk of loss.