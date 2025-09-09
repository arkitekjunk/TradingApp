#!/bin/bash
# Production run script for trading app

echo "Starting Trading App in Production Mode"
echo "======================================="

# Check if required API key is set
if [ "$FINNHUB_API_KEY" = "your_finnhub_api_key_here" ] || [ -z "$FINNHUB_API_KEY" ]; then
    echo "⚠️  WARNING: Set your actual Finnhub API key in .env file"
    echo "   Required for real-time WebSocket streaming"
fi

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Start the application
echo "Starting server on http://localhost:8000"
echo "Real-time data: WebSocket trades → 5-minute candles"
echo "Historical data: Yahoo Finance (60 days × 50 symbols)"
echo ""

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload