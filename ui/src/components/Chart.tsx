import { useEffect, useRef, useState } from 'react';
import { BarChart3, RefreshCw, AlertCircle, ZoomIn, ZoomOut, TrendingUp } from 'lucide-react';
import { TradingChart, LineChart } from '../lib/charts';
import { api } from '../lib/api';

interface ChartProps {
  symbol: string;
  timeframe: string;
}

type ChartType = 'candlestick' | 'line';

export function Chart({ symbol, timeframe }: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<TradingChart | LineChart | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [chartType, setChartType] = useState<ChartType>('candlestick');

  // Initialize chart
  useEffect(() => {
    if (!containerRef.current) return;

    const container = containerRef.current;
    let mounted = true;

    const initChart = async () => {
      try {
        console.log('Chart: Initializing chart type:', chartType);
        
        // Clean up existing chart first
        if (chartRef.current) {
          console.log('Chart: Destroying existing chart');
          try {
            chartRef.current.destroy();
          } catch (destroyError) {
            console.warn('Chart: Error destroying previous chart:', destroyError);
          }
          chartRef.current = null;
        }

        // Small delay to ensure cleanup is complete
        await new Promise(resolve => setTimeout(resolve, 10));
        
        if (!mounted || !container) return;

        if (chartType === 'candlestick') {
          console.log('Chart: Creating TradingChart');
          chartRef.current = new TradingChart(container);
        } else {
          console.log('Chart: Creating LineChart');
          chartRef.current = new LineChart(container);
        }
        
        if (!mounted || !chartRef.current) return;
        
        // Default interactions: wheel zoom and drag pan enabled
        chartRef.current.setInteractionOptions({ wheelZoom: true, dragPan: true });
        // Persist zoom per symbol+timeframe+chartType
        chartRef.current.setZoomPersistenceKey(`${symbol}:${timeframe}:${chartType}`);
        
        console.log('Chart: Chart initialization completed');
      } catch (error) {
        console.error('Chart: Failed to initialize chart:', error);
        if (mounted) {
          setError(`Failed to initialize chart: ${error}`);
        }
      }
    };

    initChart();

    return () => { 
      mounted = false;
      if (chartRef.current) {
        try {
          chartRef.current.destroy();
        } catch (error) {
          console.warn('Chart: Error destroying chart:', error);
        }
        chartRef.current = null;
      }
    };
  }, [chartType]);

  // Update persistence key and interaction when symbol/timeframe changes
  useEffect(() => {
    if (chartRef.current) {
      chartRef.current.setInteractionOptions({ wheelZoom: true, dragPan: true });
      chartRef.current.setZoomPersistenceKey(`${symbol}:${timeframe}:${chartType}`);
    }
  }, [symbol, timeframe, chartType]);

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
    const interval = setInterval(() => { loadChartData(true); }, 15000);
    return () => clearInterval(interval);
  }, [symbol, timeframe]);

  const loadChartData = async (silent: boolean = false) => {
    if (!symbol || !chartRef.current) return;

    try {
      if (!silent) { setLoading(true); setError(''); }

      const now = new Date();
      const from = new Date();
      switch (timeframe) {
        case '5m': case '15m': case '1h': case '4h': case '1d':
          from.setDate(now.getDate() - 60);
          break;
        default:
          from.setDate(now.getDate() - 60);
      }

      const response = await api.getCandles({ symbol, tf: timeframe, from_time: from.toISOString(), to_time: now.toISOString(), limit: 10000 });

      if (response.candles.length === 0) { setError(`No data available for ${symbol}`); return; }

      chartRef.current.updateData(response.candles);
      setLastUpdate(new Date());

      // Signals
      try {
        const signalsResponse = await api.getSignals({ symbol, tf: timeframe, limit: 50 });
        const markers = signalsResponse.signals.map(signal => ({
          time: Math.floor(new Date(signal.ts).getTime() / 1000),
          position: 'belowBar' as const,
          color: '#10b981',
          shape: 'arrowUp' as const,
          text: `LONG @ $${signal.details.price.toFixed(2)}`,
          size: 2 as const,
        }));
        chartRef.current?.setMarkers(markers as any);
      } catch (signalError) { console.warn('Failed to load signals:', signalError); }

    } catch (err) {
      const msg = `Failed to load chart data: ${err}`;
      setError(msg);
      console.error(msg);
    } finally {
      if (!silent) setLoading(false);
    }
  };

  const handleRefresh = () => { loadChartData(); };

  // Zoom functions
  const handleZoomIn = () => { chartRef.current?.zoomIn(); };
  const handleZoomOut = () => { chartRef.current?.zoomOut(); };
  const handleFitContent = () => { chartRef.current?.fitContent(); };
  const handleQuickZoom = (days: number) => { chartRef.current?.zoomToRange(days); };

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
          <span className="text-gray-400">•</span>
          <span className="text-xs text-gray-500">Volume: ON</span>
          <span className="text-gray-400">•</span>
          
          {/* Chart Type Tabs */}
          <div className="flex items-center space-x-1 bg-gray-800 rounded-lg p-1">
            <button
              onClick={() => setChartType('candlestick')}
              className={`text-xs px-2 py-1 rounded flex items-center space-x-1 transition-colors ${
                chartType === 'candlestick'
                  ? 'bg-blue-600 text-white'
                  : 'hover:bg-gray-700 text-gray-300'
              }`}
              title="Candlestick chart"
            >
              <BarChart3 className="w-3 h-3" />
              <span>Candles</span>
            </button>
            <button
              onClick={() => setChartType('line')}
              className={`text-xs px-2 py-1 rounded flex items-center space-x-1 transition-colors ${
                chartType === 'line'
                  ? 'bg-green-600 text-white'
                  : 'hover:bg-gray-700 text-gray-300'
              }`}
              title="Line chart"
            >
              <TrendingUp className="w-3 h-3" />
              <span>Line</span>
            </button>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          {/* Quick Zoom Buttons */}
          <div className="flex items-center space-x-1 bg-gray-800 rounded-lg p-1">
            <button onClick={() => handleQuickZoom(1)} className="text-xs px-2 py-1 rounded hover:bg-gray-700 text-gray-300" title="Zoom to 1 day">1D</button>
            <button onClick={() => handleQuickZoom(7)} className="text-xs px-2 py-1 rounded hover:bg-gray-700 text-gray-300" title="Zoom to 1 week">1W</button>
            <button onClick={() => handleQuickZoom(30)} className="text-xs px-2 py-1 rounded hover:bg-gray-700 text-gray-300" title="Zoom to 1 month">1M</button>
            <button onClick={handleFitContent} className="text-xs px-2 py-1 rounded hover:bg-gray-700 text-gray-300" title="Fit all data">ALL</button>
          </div>

          {/* Zoom In/Out */}
          <div className="flex items-center space-x-1">
            <button onClick={handleZoomOut} className="trading-button p-2 hover:bg-gray-700" title="Zoom out"><ZoomOut className="w-4 h-4" /></button>
            <button onClick={handleZoomIn} className="trading-button p-2 hover:bg-gray-700" title="Zoom in"><ZoomIn className="w-4 h-4" /></button>
          </div>

          {lastUpdate && <span className="text-xs text-gray-400">Updated: {lastUpdate.toLocaleTimeString()}</span>}
          
          <button onClick={handleRefresh} disabled={loading} className="trading-button p-2 hover:bg-gray-700" title="Refresh chart data">
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

        <div ref={containerRef} className="w-full h-full" style={{ minHeight: '400px' }} />
      </div>

      {/* Chart Legend */}
      <div className="p-3 border-t border-gray-700">
        <div className="flex flex-wrap items-center gap-4 text-xs">
          {chartType === 'line' && (
            <div className="flex items-center space-x-1">
              <div className="w-3 h-0.5 bg-green-500"></div>
              <span className="text-gray-300">Price Line</span>
            </div>
          )}
          <div className="flex items-center space-x-1"><div className="w-3 h-2 bg-green-500 opacity-50"></div><span className="text-gray-300">Volume</span></div>
          <div className="flex items-center space-x-1"><div className="w-3 h-0.5 bg-blue-500"></div><span className="text-gray-300">EMA 9</span></div>
          <div className="flex items-center space-x-1"><div className="w-3 h-0.5 bg-orange-500"></div><span className="text-gray-300">EMA 21</span></div>
          <div className="flex items-center space-x-1"><div className="w-3 h-0.5 bg-purple-500" style={{ borderStyle: 'dashed', borderWidth: '1px 0' }}></div><span className="text-gray-300">VWAP</span></div>
          <div className="flex items-center space-x-1"><div className="w-3 h-0.5 bg-gray-400" style={{ borderStyle: 'dotted', borderWidth: '1px 0' }}></div><span className="text-gray-300">Bollinger Bands</span></div>
          <div className="flex items-center space-x-1"><div className="w-3 h-0.5 bg-teal-500"></div><span className="text-gray-300">RSI (14)</span></div>
        </div>
      </div>
    </div>
  );
}