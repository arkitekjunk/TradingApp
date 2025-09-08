import { Activity, Database, HardDrive, Wifi } from 'lucide-react';
import { format } from 'date-fns';
import type { WorkerStatus, HealthStatus } from '../lib/api';

interface StatusBarProps {
  workerStatus: WorkerStatus | null;
  healthStatus: HealthStatus | null;
}

export function StatusBar({ workerStatus, healthStatus }: StatusBarProps) {
  if (!workerStatus || !healthStatus) {
    return (
      <div className="trading-card mx-4 mb-4 p-3">
        <div className="flex items-center justify-center text-gray-400">
          <Activity className="w-4 h-4 mr-2" />
          Loading status...
        </div>
      </div>
    );
  }

  const backfillProgress = workerStatus.stats.backfill_progress;
  const isBackfillActive = backfillProgress.status === 'running';
  const backfillPercent = backfillProgress.total > 0 
    ? Math.round((backfillProgress.current / backfillProgress.total) * 100) 
    : 0;

  return (
    <div className="trading-card mx-4 mb-4 p-3">
      <div className="flex items-center justify-between text-sm">
        {/* Left side - Connection status */}
        <div className="flex items-center space-x-6">
          <div className="flex items-center space-x-2">
            <Wifi className={`w-4 h-4 ${workerStatus.ws_connected ? 'text-green-500' : 'text-red-500'}`} />
            <span className="text-gray-300">
              WebSocket: {workerStatus.ws_connected ? 'Connected' : 'Disconnected'}
            </span>
          </div>

          <div className="flex items-center space-x-2">
            <Database className={`w-4 h-4 ${healthStatus.database === 'healthy' ? 'text-green-500' : 'text-red-500'}`} />
            <span className="text-gray-300">
              Database: {healthStatus.database === 'healthy' ? 'OK' : 'Error'}
            </span>
          </div>

          <div className="flex items-center space-x-2">
            <HardDrive className={`w-4 h-4 ${healthStatus.storage.includes('healthy') ? 'text-green-500' : 'text-red-500'}`} />
            <span className="text-gray-300">
              Storage: {healthStatus.storage.includes('healthy') ? 'OK' : 'Error'}
            </span>
          </div>
        </div>

        {/* Center - Backfill progress */}
        {isBackfillActive && (
          <div className="flex items-center space-x-3">
            <span className="text-gray-300">Backfill Progress:</span>
            <div className="w-32 h-2 bg-gray-700 rounded-full overflow-hidden">
              <div 
                className="h-full bg-blue-500 transition-all duration-300"
                style={{ width: `${backfillPercent}%` }}
              />
            </div>
            <span className="text-gray-300 font-mono">
              {backfillProgress.current}/{backfillProgress.total} ({backfillPercent}%)
            </span>
          </div>
        )}

        {/* Right side - Stats */}
        <div className="flex items-center space-x-6">
          <div className="text-gray-300">
            Symbols: <span className="font-mono">{workerStatus.symbols_count}</span>
          </div>
          
          <div className="text-gray-300">
            Messages: <span className="font-mono">{workerStatus.stats.ws_messages_received.toLocaleString()}</span>
          </div>

          <div className="text-gray-300">
            Trades: <span className="font-mono">{workerStatus.stats.trades_processed.toLocaleString()}</span>
          </div>

          {workerStatus.stats.last_trade_time && (
            <div className="text-gray-300">
              Last: <span className="font-mono">
                {format(new Date(workerStatus.stats.last_trade_time), 'HH:mm:ss')}
              </span>
            </div>
          )}

          <div className="text-gray-400">
            Updated: <span className="font-mono">
              {format(new Date(healthStatus.timestamp), 'HH:mm:ss')}
            </span>
          </div>
        </div>
      </div>

      {/* Backfill completed message */}
      {backfillProgress.status === 'completed' && (
        <div className="mt-2 text-xs text-green-400 text-center">
          ✓ Backfill completed successfully
        </div>
      )}

      {/* Backfill error message */}
      {backfillProgress.status === 'error' && (
        <div className="mt-2 text-xs text-red-400 text-center">
          ✗ Backfill failed - check logs
        </div>
      )}
    </div>
  );
}