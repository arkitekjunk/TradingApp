import { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, Volume2 } from 'lucide-react';
import { api } from '../lib/api';

interface WatchlistProps {
  symbols: string[];
  selectedSymbol: string;
  onSymbolSelect: (symbol: string) => void;
}

interface SymbolData {
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
  volume: number;
  rvol: number;
}

export function Watchlist({ symbols, selectedSymbol, onSymbolSelect }: WatchlistProps) {
  const [symbolData, setSymbolData] = useState<Map<string, SymbolData>>(new Map());
  const [sortBy, setSortBy] = useState<'symbol' | 'change' | 'rvol'>('symbol');
  const [loading, setLoading] = useState(false);

  // Fetch data for all symbols
  useEffect(() => {
    const fetchSymbolData = async () => {
      if (symbols.length === 0) return;
      
      setLoading(true);
      const newData = new Map<string, SymbolData>();

      // Fetch recent candles for each symbol (limit to prevent overloading)
      const batchSize = 10;
      const symbolBatches = [];
      
      for (let i = 0; i < Math.min(symbols.length, 50); i += batchSize) {
        symbolBatches.push(symbols.slice(i, i + batchSize));
      }

      for (const batch of symbolBatches) {
        await Promise.all(
          batch.map(async (symbol) => {
            try {
              const response = await api.getCandles({
                symbol,
                tf: '5m',
                limit: 20 // Just get recent candles for price info
              });

              if (response.candles.length > 0) {
                const latestCandle = response.candles[response.candles.length - 1];
                const firstCandle = response.candles[0];
                
                const price = latestCandle.close;
                const change = price - firstCandle.open;
                const changePercent = (change / firstCandle.open) * 100;
                
                newData.set(symbol, {
                  symbol,
                  price,
                  change,
                  changePercent,
                  volume: latestCandle.volume,
                  rvol: latestCandle.rvol || 1
                });
              }
            } catch (error) {
              console.error(`Failed to fetch data for ${symbol}:`, error);
            }
          })
        );
      }

      setSymbolData(newData);
      setLoading(false);
    };

    fetchSymbolData();
    const interval = setInterval(fetchSymbolData, 30000); // Update every 30 seconds

    return () => clearInterval(interval);
  }, [symbols]);

  const sortedSymbols = symbols.sort((a, b) => {
    const aData = symbolData.get(a);
    const bData = symbolData.get(b);

    if (!aData && !bData) return a.localeCompare(b);
    if (!aData) return 1;
    if (!bData) return -1;

    switch (sortBy) {
      case 'change':
        return bData.changePercent - aData.changePercent;
      case 'rvol':
        return bData.rvol - aData.rvol;
      default:
        return a.localeCompare(b);
    }
  });

  return (
    <div className="trading-card p-4 h-96 flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Watchlist</h2>
        <div className="flex items-center space-x-2">
          <span className="text-xs text-gray-400">Sort by:</span>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as 'symbol' | 'change' | 'rvol')}
            className="trading-select text-xs"
          >
            <option value="symbol">Symbol</option>
            <option value="change">Change %</option>
            <option value="rvol">RVOL</option>
          </select>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading && symbols.length > 0 && (
          <div className="text-center text-gray-400 py-4">
            Loading symbol data...
          </div>
        )}

        {symbols.length === 0 ? (
          <div className="text-center text-gray-400 py-8">
            No symbols loaded. Check your configuration.
          </div>
        ) : (
          <div className="space-y-1">
            {sortedSymbols.map((symbol) => {
              const data = symbolData.get(symbol);
              const isSelected = symbol === selectedSymbol;
              
              return (
                <div
                  key={symbol}
                  onClick={() => onSymbolSelect(symbol)}
                  className={`p-3 rounded cursor-pointer transition-colors ${
                    isSelected 
                      ? 'bg-blue-600/20 border border-blue-500/50' 
                      : 'hover:bg-gray-700/50'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <span className="font-mono font-semibold">{symbol}</span>
                      {data && data.rvol > 2 && (
                        <Volume2 className="w-3 h-3 text-orange-500" />
                      )}
                    </div>
                    
                    {data && (
                      <div className="text-right">
                        <div className="text-sm font-mono">
                          ${data.price.toFixed(2)}
                        </div>
                        <div className={`text-xs flex items-center ${
                          data.change >= 0 ? 'text-green-400' : 'text-red-400'
                        }`}>
                          {data.change >= 0 ? (
                            <TrendingUp className="w-3 h-3 mr-1" />
                          ) : (
                            <TrendingDown className="w-3 h-3 mr-1" />
                          )}
                          {data.changePercent.toFixed(2)}%
                        </div>
                      </div>
                    )}
                  </div>
                  
                  {data && (
                    <div className="flex justify-between text-xs text-gray-400 mt-1">
                      <span>Vol: {data.volume.toLocaleString()}</span>
                      <span>RVOL: {data.rvol.toFixed(1)}x</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}