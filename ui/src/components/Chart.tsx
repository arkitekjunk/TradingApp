import { useEffect, useRef, useState } from 'react';
import { BarChart3, RefreshCw, AlertCircle } from 'lucide-react';
import { TradingChart } from '../lib/charts';
import { api } from '../lib/api';

interface ChartProps {
  symbol: string;
  timeframe: string;
}

export function Chart({ symbol, timeframe }: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<TradingChart | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  // Initialize chart
  useEffect(() => {
    if (!containerRef.current) return;

    // Clean up existing chart
    if (chartRef.current) {
      chartRef.current.destroy();
    }

    // Create new chart
    chartRef.current = new TradingChart(containerRef.current);

    return () => {
      if (chartRef.current) {
        chartRef.current.destroy();
      }
    };
  }, []);

  // Handle resize
  useEffect(() => {
    const handleResize = () => {
      if (chartRef.current && containerRef.current) {
        const { clientWidth, clientHeight } = containerRef.current;
        chartRef.current.resize(clientWidth, clientHeight);
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Load data when symbol or timeframe changes
  useEffect(() => {
    if (symbol && chartRef.current) {
      loadChartData();
    }
  }, [symbol, timeframe]);

  // Auto-refresh data
  useEffect(() => {
    if (!symbol) return;

    const interval = setInterval(() => {
      loadChartData(true); // Silent refresh
    }, 15000); // Update every 15 seconds

    return () => clearInterval(interval);
  }, [symbol, timeframe]);

  const loadChartData = async (silent: boolean = false) => {
    if (!symbol || !chartRef.current) return;

    try {
      if (!silent) {
        setLoading(true);
        setError('');
      }

      // Calculate date range based on timeframe
      const now = new Date();
      const from = new Date();
      
      // Adjust lookback based on timeframe
      switch (timeframe) {
        case '5m':
          from.setDate(now.getDate() - 7); // 7 days for 5m
          break;
        case '15m':
          from.setDate(now.getDate() - 14); // 2 weeks for 15m
          break;
        case '1h':
          from.setMonth(now.getMonth() - 1); // 1 month for 1h
          break;
        case '4h':
          from.setMonth(now.getMonth() - 3); // 3 months for 4h
          break;
        case '1d':
          from.setFullYear(now.getFullYear() - 1); // 1 year for 1d
          break;
        default:
          from.setDate(now.getDate() - 7);
      }

      const response = await api.getCandles({
        symbol,
        tf: timeframe,
        from_time: from.toISOString(),
        to_time: now.toISOString(),
        limit: 1000
      });

      if (response.candles.length === 0) {
        setError(`No data available for ${symbol}`);
        return;
      }

      // Update chart with data
      chartRef.current.updateData(response.candles);
      setLastUpdate(new Date());

      // Load and add signal markers
      try {
        const signalsResponse = await api.getSignals({
          symbol,
          tf: timeframe,
          limit: 20
        });

        // Add signal markers to chart
        signalsResponse.signals.forEach(signal => {
          const signalTime = Math.floor(new Date(signal.ts).getTime() / 1000);
          chartRef.current?.addSignalMarker(
            signalTime,
            signal.details.price,
            `LONG @ $${signal.details.price.toFixed(2)}`
          );
        });
      } catch (signalError) {
        console.warn('Failed to load signals:', signalError);
      }

    } catch (err) {
      const errorMessage = `Failed to load chart data: ${err}`;
      setError(errorMessage);
      console.error(errorMessage);
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  };

  const handleRefresh = () => {
    loadChartData();
  };

  if (!symbol) {
    return (
      <div className="trading-card h-full flex items-center justify-center">
        <div className="text-center text-gray-400">
          <BarChart3 className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p>Select a symbol to view the chart</p>
        </div>
      </div>
    );
  }

  return (
    <div className="trading-card h-full flex flex-col">
      {/* Chart Header */}
      <div className="p-4 border-b border-gray-700 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <BarChart3 className="w-5 h-5 text-blue-500" />
          <span className="font-semibold">{symbol}</span>
          <span className="text-gray-400">•</span>
          <span className="text-sm text-gray-400">{timeframe.toUpperCase()}</span>
        </div>

        <div className="flex items-center space-x-3">
          {lastUpdate && (
            <span className="text-xs text-gray-400">
              Updated: {lastUpdate.toLocaleTimeString()}
            </span>
          )}
          
          <button
            onClick={handleRefresh}
            disabled={loading}
            className="trading-button p-2 hover:bg-gray-700"
            title="Refresh chart data"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Chart Content */}
      <div className="flex-1 relative">
        {loading && (
          <div className="absolute top-4 left-4 right-4 z-10">
            <div className="bg-blue-600/20 border border-blue-500/50 rounded-lg p-3 flex items-center">
              <RefreshCw className="w-4 h-4 animate-spin mr-2 text-blue-400" />
              <span className="text-blue-300 text-sm">Loading chart data...</span>
            </div>
          </div>
        )}

        {error && (
          <div className="absolute top-4 left-4 right-4 z-10">
            <div className="bg-red-600/20 border border-red-500/50 rounded-lg p-3 flex items-start space-x-2">
              <AlertCircle className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
              <div className="text-red-300 text-sm">{error}</div>
            </div>
          </div>
        )}

        <div
          ref={containerRef}
          className="w-full h-full"
          style={{ minHeight: '400px' }}
        />
      </div>

      {/* Chart Legend */}
      <div className="p-3 border-t border-gray-700">
        <div className="flex flex-wrap items-center gap-4 text-xs">
          <div className="flex items-center space-x-1">
            <div className="w-3 h-0.5 bg-blue-500"></div>
            <span className="text-gray-300">EMA 9</span>
          </div>
          <div className="flex items-center space-x-1">
            <div className="w-3 h-0.5 bg-orange-500"></div>
            <span className="text-gray-300">EMA 21</span>
          </div>
          <div className="flex items-center space-x-1">
            <div className="w-3 h-0.5 bg-purple-500" style={{ borderStyle: 'dashed', borderWidth: '1px 0' }}></div>
            <span className="text-gray-300">VWAP</span>
          </div>
          <div className="flex items-center space-x-1">
            <div className="w-3 h-0.5 bg-gray-400" style={{ borderStyle: 'dotted', borderWidth: '1px 0' }}></div>
            <span className="text-gray-300">Bollinger Bands</span>
          </div>
          <div className="flex items-center space-x-1">
            <div className="w-3 h-0.5 bg-teal-500"></div>
            <span className="text-gray-300">RSI (14)</span>
          </div>
        </div>
      </div>
    </div>
  );
}