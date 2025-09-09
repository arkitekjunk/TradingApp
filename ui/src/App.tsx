import { useState, useEffect } from 'react';
import type { HealthStatus } from './lib/api';
import { Chart } from './components/Chart';
import { Watchlist } from './components/Watchlist';

function App() {
  console.log('🔥 Trading App v2.0 - Chart Interface Loading...');
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [settings, setSettings] = useState({
    finnhub_api_key: '',
    lookback_days: 30,
    discord_webhook_url: ''
  });
  const [isRunning, setIsRunning] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [selectedSymbol, setSelectedSymbol] = useState<string>('AAPL');
  const [selectedTimeframe, setSelectedTimeframe] = useState<string>('5m');
  const [showDashboard, setShowDashboard] = useState(false);
  const [symbols, setSymbols] = useState<string[]>([]);

  // Fetch health status
  const fetchHealth = async () => {
    try {
      const response = await fetch('/healthz');
      const data = await response.json();
      setHealth(data);
      setIsRunning(data.worker?.running || false);
    } catch (error) {
      console.error('Failed to fetch health:', error);
    }
  };

  // Save settings
  const saveSettings = async () => {
    try {
      const response = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
      });
      
      if (response.ok) {
        alert('Settings saved successfully!');
        setShowSettings(false);
      } else {
        alert('Failed to save settings');
      }
    } catch (error) {
      alert('Error saving settings: ' + error);
    }
  };

  // Start worker
  const startWorker = async () => {
    try {
      const response = await fetch('/api/control/start', {
        method: 'POST'
      });
      const result = await response.json();
      
      if (result.status === 'success') {
        setIsRunning(true);
      } else {
        alert('Failed to start worker: ' + result.message);
      }
    } catch (error) {
      alert('Error starting worker: ' + error);
    }
  };

  // Stop worker
  const stopWorker = async () => {
    try {
      const response = await fetch('/api/control/stop', {
        method: 'POST'
      });
      const result = await response.json();
      
      if (result.status === 'success') {
        setIsRunning(false);
      }
    } catch (error) {
      alert('Error stopping worker: ' + error);
    }
  };

  // Load initial data
  useEffect(() => {
    const loadInitialData = async () => {
      try {
        // Load settings
        const settingsResponse = await fetch('/api/settings');
        const settingsData = await settingsResponse.json();
        if (settingsData.settings) {
          setSettings({
            finnhub_api_key: settingsData.settings.FINNHUB_API_KEY || '',
            lookback_days: parseInt(settingsData.settings.LOOKBACK_DAYS) || 30,
            discord_webhook_url: settingsData.settings.DISCORD_WEBHOOK_URL || ''
          });
        }

        // Load universe symbols
        const universeResponse = await fetch('/api/universe');
        const universeData = await universeResponse.json();
        if (universeData.symbols) {
          setSymbols(universeData.symbols);
        }
      } catch (error) {
        console.error('Failed to load initial data:', error);
      }
    };

    loadInitialData();
    fetchHealth();
    
    // Poll health every 5 seconds
    const interval = setInterval(fetchHealth, 5000);
    return () => clearInterval(interval);
  }, []);

  if (showDashboard) {
    return (
      <div className="min-h-screen bg-gray-900 text-white p-4">
        <div className="max-w-6xl mx-auto">
          {/* Header */}
          <div className="bg-gray-800 rounded-lg p-4 mb-4 flex justify-between items-center">
            <div className="flex items-center space-x-4">
              <h1 className="text-2xl font-bold">Trading App</h1>
              <div className="flex items-center space-x-2">
                <div className={`w-3 h-3 rounded-full ${
                  health?.worker?.ws_connected ? 'bg-green-500' : 'bg-red-500'
                }`}></div>
                <span>{health?.worker?.ws_connected ? 'Connected' : 'Disconnected'}</span>
              </div>
            </div>
            
            <div className="space-x-2">
              <button
                onClick={() => setShowDashboard(false)}
                className="bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded"
              >
                Charts
              </button>
              <button
                onClick={() => setShowSettings(!showSettings)}
                className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded"
              >
                Settings
              </button>
              
              {!isRunning ? (
                <button
                  onClick={startWorker}
                  className="bg-green-600 hover:bg-green-700 px-4 py-2 rounded"
                >
                  Start
                </button>
              ) : (
                <button
                  onClick={stopWorker}
                  className="bg-red-600 hover:bg-red-700 px-4 py-2 rounded"
                >
                  Stop
                </button>
              )}
            </div>
          </div>

        {/* Settings Panel */}
        {showSettings && (
          <div className="bg-gray-800 rounded-lg p-6 mb-4">
            <h2 className="text-xl font-bold mb-4">Settings</h2>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">
                  Finnhub API Key *
                </label>
                <input
                  type="password"
                  value={settings.finnhub_api_key}
                  onChange={(e) => setSettings({...settings, finnhub_api_key: e.target.value})}
                  className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2"
                  placeholder="Enter your Finnhub API key"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium mb-2">
                  Lookback Days
                </label>
                <input
                  type="number"
                  value={settings.lookback_days}
                  onChange={(e) => setSettings({...settings, lookback_days: parseInt(e.target.value) || 30})}
                  className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium mb-2">
                  Discord Webhook URL (Optional)
                </label>
                <input
                  type="url"
                  value={settings.discord_webhook_url}
                  onChange={(e) => setSettings({...settings, discord_webhook_url: e.target.value})}
                  className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2"
                  placeholder="https://discord.com/api/webhooks/..."
                />
              </div>
              
              <button
                onClick={saveSettings}
                className="bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded"
              >
                Save Settings
              </button>
            </div>
          </div>
        )}

        {/* Status Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* System Status */}
          <div className="bg-gray-800 rounded-lg p-4">
            <h3 className="text-lg font-semibold mb-3">System Status</h3>
            <div className="space-y-2 text-sm">
              <div>Worker: <span className={isRunning ? 'text-green-400' : 'text-red-400'}>
                {isRunning ? 'Running' : 'Stopped'}
              </span></div>
              <div>WebSocket: <span className={health?.worker?.ws_connected ? 'text-green-400' : 'text-red-400'}>
                {health?.worker?.ws_connected ? 'Connected' : 'Disconnected'}
              </span></div>
              {health?.last_ws_tick_ts && (
                <div>Last Tick: <span className="text-blue-400">
                  {(() => {
                    const lastTick = new Date(health.last_ws_tick_ts);
                    const now = new Date();
                    const ageSeconds = Math.floor((now.getTime() - lastTick.getTime()) / 1000);
                    if (ageSeconds < 60) return `${ageSeconds}s ago`;
                    if (ageSeconds < 3600) return `${Math.floor(ageSeconds / 60)}m ago`;
                    return `${Math.floor(ageSeconds / 3600)}h ago`;
                  })()} 
                </span></div>
              )}
              <div>Symbols: <span className="text-blue-400">
                {health?.worker?.symbols_count || 0}
              </span></div>
              <div>Messages: <span className="text-blue-400">
                {health?.worker?.stats?.ws_messages_received?.toLocaleString() || 0}
              </span></div>
              <div>Trades: <span className="text-blue-400">
                {health?.worker?.stats?.trades_processed?.toLocaleString() || 0}
              </span></div>
            </div>
          </div>

          {/* Backfill & Quota */}
          <div className="bg-gray-800 rounded-lg p-4">
            <h3 className="text-lg font-semibold mb-3">Backfill & Quota</h3>
            
            {/* Backfill Status */}
            <div className="mb-4">
              <div className="text-xs text-gray-400 mb-1">Backfill:</div>
              {health?.worker?.stats?.backfill_progress?.status === 'running' ? (
                <div>
                  <div className="w-full bg-gray-700 rounded-full h-2 mb-1">
                    <div 
                      className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                      style={{ 
                        width: `${Math.round(
                          (health.worker.stats.backfill_progress.current / 
                           health.worker.stats.backfill_progress.total) * 100
                        )}%` 
                      }}
                    ></div>
                  </div>
                  <div className="text-xs text-blue-400">
                    Running ({health.worker.stats.backfill_progress.current}/{health.worker.stats.backfill_progress.total})
                  </div>
                </div>
              ) : health?.worker?.stats?.backfill_progress?.status === 'completed' ? (
                <div className="text-xs text-green-400">✓ Completed</div>
              ) : (
                <div className="text-xs text-gray-400">Idle</div>
              )}
            </div>
            
            {/* API Quota */}
            <div>
              <div className="text-xs text-gray-400 mb-1">API Quota:</div>
              <div className="text-sm space-y-1">
                <div>Today: <span className="text-blue-400 font-mono">
                  {health?.rest_calls_today || 0} / 500
                </span></div>
                <div>Remaining: <span className={`font-mono ${
                  (health?.budget_remaining_today || 500) < 100 ? 'text-red-400' : 
                  (health?.budget_remaining_today || 500) < 200 ? 'text-yellow-400' : 'text-green-400'
                }`}>
                  {health?.budget_remaining_today || 500}
                </span></div>
                <div>This Minute: <span className="text-blue-400 font-mono">
                  {health?.rest_calls_minute || 0} / 60
                </span></div>
                {(health?.backfill_queue_size || 0) > 0 && (
                  <div>Queued: <span className="text-yellow-400 font-mono">
                    {health.backfill_queue_size} symbols
                  </span></div>
                )}
              </div>
            </div>
          </div>

          {/* Health Status */}
          <div className="bg-gray-800 rounded-lg p-4">
            <h3 className="text-lg font-semibold mb-3">Health Status</h3>
            <div className="space-y-2 text-sm">
              <div>Database: <span className={health?.database === 'healthy' ? 'text-green-400' : 'text-red-400'}>
                {health?.database === 'healthy' ? 'OK' : 'Error'}
              </span></div>
              <div>Storage: <span className={health?.storage?.includes('healthy') ? 'text-green-400' : 'text-red-400'}>
                {health?.storage?.includes('healthy') ? 'OK' : 'Error'}
              </span></div>
              <div>Universe: <span className="text-blue-400">
                {health?.universe?.symbols_count || 0} symbols
              </span></div>
              <div>Extended Hours: <span className={`${
                health?.include_extended_hours ? 'text-green-400' : 'text-gray-400'
              }`}>
                {health?.include_extended_hours ? 'Enabled' : 'Disabled'}
              </span></div>
              {health?.last_reconcile_date && (
                <div>Last Reconcile: <span className="text-blue-400">
                  {health.last_reconcile_date}
                </span></div>
              )}
            </div>
          </div>
        </div>

        {/* API Documentation Link */}
        <div className="mt-6 text-center">
          <a 
            href="/docs" 
            target="_blank"
            className="text-blue-400 hover:text-blue-300 underline"
          >
            View API Documentation
          </a>
        </div>
      </div>
    </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Simple Status Bar */}
      <div className="bg-gray-800 p-4 flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <h1 className="text-xl font-bold">🚀 TRADING CHARTS v2.0 - NEW INTERFACE! 🚀</h1>
          <div className="flex items-center space-x-2">
            <div className={`w-3 h-3 rounded-full ${
              health?.worker?.ws_connected ? 'bg-green-500' : 'bg-red-500'
            }`}></div>
            <span>{health?.worker?.ws_connected ? 'Connected' : 'Disconnected'}</span>
          </div>
          <div className="text-sm text-gray-300">
            Symbols: {symbols.length} | Worker: {isRunning ? 'Running' : 'Stopped'}
          </div>
        </div>
        
        <div className="space-x-2">
          <button
            onClick={() => setShowDashboard(true)}
            className="bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded text-sm"
          >
            Dashboard
          </button>
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded text-sm"
          >
            Settings
          </button>
          
          {!isRunning ? (
            <button
              onClick={startWorker}
              className="bg-green-600 hover:bg-green-700 px-4 py-2 rounded text-sm"
            >
              Start
            </button>
          ) : (
            <button
              onClick={stopWorker}
              className="bg-red-600 hover:bg-red-700 px-4 py-2 rounded text-sm"
            >
              Stop
            </button>
          )}
        </div>
      </div>

      {/* Settings Panel */}
      {showSettings && (
        <div className="bg-gray-800 p-6 mb-4 mx-4">
          <h2 className="text-xl font-bold mb-4">Settings</h2>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">
                Finnhub API Key *
              </label>
              <input
                type="password"
                value={settings.finnhub_api_key}
                onChange={(e) => setSettings({...settings, finnhub_api_key: e.target.value})}
                className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2"
                placeholder="Enter your Finnhub API key"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium mb-2">
                Lookback Days
              </label>
              <input
                type="number"
                value={settings.lookback_days}
                onChange={(e) => setSettings({...settings, lookback_days: parseInt(e.target.value) || 30})}
                className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium mb-2">
                Discord Webhook URL (Optional)
              </label>
              <input
                type="url"
                value={settings.discord_webhook_url}
                onChange={(e) => setSettings({...settings, discord_webhook_url: e.target.value})}
                className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2"
                placeholder="https://discord.com/api/webhooks/..."
              />
            </div>
            
            <button
              onClick={saveSettings}
              className="bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded"
            >
              Save Settings
            </button>
          </div>
        </div>
      )}

      {/* Main Trading Interface */}
      <div className="flex h-screen">
        {/* Left Sidebar - Watchlist */}
        <div className="w-80 p-4">
          <Watchlist 
            symbols={symbols}
            selectedSymbol={selectedSymbol}
            onSymbolSelect={setSelectedSymbol}
          />

          {/* Timeframe Selector */}
          <div className="bg-gray-800 rounded-lg p-4 mt-4">
            <h3 className="text-sm font-semibold mb-3">Timeframe</h3>
            <div className="grid grid-cols-3 gap-2">
              {['5m', '15m', '1h', '4h', '1d'].map((tf) => (
                <button
                  key={tf}
                  onClick={() => setSelectedTimeframe(tf)}
                  className={`px-3 py-2 text-sm rounded ${
                    selectedTimeframe === tf 
                      ? 'bg-blue-600 text-white' 
                      : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
                  }`}
                >
                  {tf.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Main Chart Area */}
        <div className="flex-1 p-4">
          <Chart 
            symbol={selectedSymbol}
            timeframe={selectedTimeframe}
          />
        </div>
      </div>
    </div>
  );
}

export default App;