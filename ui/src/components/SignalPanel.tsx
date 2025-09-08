import { useState, useEffect } from 'react';
import { AlertTriangle, Clock, TrendingUp, RefreshCw } from 'lucide-react';
import { format } from 'date-fns';
import { api, type Signal } from '../lib/api';

interface SignalPanelProps {
  selectedSymbol: string;
}

export function SignalPanel({ selectedSymbol }: SignalPanelProps) {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<'all' | 'symbol'>('all');

  useEffect(() => {
    fetchSignals();
    const interval = setInterval(fetchSignals, 10000); // Update every 10 seconds
    return () => clearInterval(interval);
  }, [selectedSymbol, filter]);

  const fetchSignals = async () => {
    try {
      setLoading(true);
      const response = await api.getSignals({
        symbol: filter === 'symbol' ? selectedSymbol : undefined,
        limit: 50
      });
      setSignals(response.signals);
    } catch (error) {
      console.error('Failed to fetch signals:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleResendAlert = async (signalId: number) => {
    try {
      await api.resendSignalAlert(signalId);
      // Could show a toast notification here
    } catch (error) {
      console.error('Failed to resend alert:', error);
      alert(`Failed to resend alert: ${error}`);
    }
  };

  const formatConditions = (conditions: Record<string, boolean>) => {
    const conditionLabels: Record<string, string> = {
      ema_cross_above: 'EMA Cross',
      rsi_above_min: 'RSI > 50',
      price_above_vwap: 'Price > VWAP',
      rvol_above_min: 'RVOL ≥ 2.0'
    };

    return Object.entries(conditions)
      .filter(([_, met]) => met)
      .map(([key, _]) => conditionLabels[key] || key)
      .join(', ');
  };

  return (
    <div className="trading-card p-4 h-80 flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          <AlertTriangle className="w-5 h-5 text-orange-500" />
          <h2 className="text-lg font-semibold">Recent Signals</h2>
        </div>
        
        <div className="flex items-center space-x-2">
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value as 'all' | 'symbol')}
            className="trading-select text-xs"
          >
            <option value="all">All Symbols</option>
            <option value="symbol">{selectedSymbol || 'Selected'}</option>
          </select>
          
          <button
            onClick={fetchSignals}
            disabled={loading}
            className="p-1 hover:bg-gray-700 rounded transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {signals.length === 0 ? (
          <div className="text-center text-gray-400 py-8">
            {loading ? 'Loading signals...' : 'No signals yet'}
          </div>
        ) : (
          <div className="space-y-2">
            {signals.map((signal) => (
              <div
                key={signal.id}
                className="p-3 bg-gray-700/30 rounded-lg border border-gray-600/50"
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center space-x-2">
                    <TrendingUp className="w-4 h-4 text-green-400" />
                    <span className="font-mono font-semibold text-green-400">
                      {signal.symbol}
                    </span>
                    <span className="text-xs text-gray-400 bg-gray-600 px-2 py-1 rounded">
                      {signal.tf}
                    </span>
                  </div>
                  
                  <div className="flex items-center space-x-1">
                    <Clock className="w-3 h-3 text-gray-400" />
                    <span className="text-xs text-gray-400">
                      {format(new Date(signal.ts), 'HH:mm:ss')}
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 text-xs mb-2">
                  <div>
                    <span className="text-gray-400">Price:</span>
                    <span className="ml-1 font-mono">${signal.details.price.toFixed(2)}</span>
                  </div>
                  <div>
                    <span className="text-gray-400">RSI:</span>
                    <span className="ml-1 font-mono">{signal.details.rsi.toFixed(1)}</span>
                  </div>
                  <div>
                    <span className="text-gray-400">RVOL:</span>
                    <span className="ml-1 font-mono">{signal.details.rvol.toFixed(1)}x</span>
                  </div>
                  <div>
                    <span className="text-gray-400">Volume:</span>
                    <span className="ml-1 font-mono">{signal.details.volume.toLocaleString()}</span>
                  </div>
                </div>

                <div className="text-xs text-gray-400 mb-2">
                  <div className="font-medium mb-1">Conditions Met:</div>
                  <div className="text-green-400">
                    {formatConditions(signal.details.conditions)}
                  </div>
                </div>

                <div className="flex justify-between items-center">
                  <div className="text-xs text-gray-400">
                    {format(new Date(signal.ts), 'MMM dd, yyyy')}
                  </div>
                  
                  <button
                    onClick={() => handleResendAlert(signal.id)}
                    className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
                  >
                    Resend Alert
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}