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
  marketCap?: string;
}

// Company name mapping
const COMPANY_NAMES: { [key: string]: string } = {
  'AAPL': 'Apple Inc.',
  'MSFT': 'Microsoft Corp.',
  'GOOGL': 'Alphabet Inc.',
  'AMZN': 'Amazon.com Inc.',
  'NVDA': 'NVIDIA Corp.',
  'TSLA': 'Tesla Inc.',
  'META': 'Meta Platforms',
  'BRK.B': 'Berkshire Hathaway',
  'UNH': 'UnitedHealth Group',
  'JNJ': 'Johnson & Johnson',
  'XOM': 'Exxon Mobil Corp.',
  'JPM': 'JPMorgan Chase',
  'V': 'Visa Inc.',
  'WMT': 'Walmart Inc.',
  'PG': 'Procter & Gamble',
  'HD': 'Home Depot Inc.',
  'CVX': 'Chevron Corp.',
  'MA': 'Mastercard Inc.',
  'BAC': 'Bank of America',
  'ABBV': 'AbbVie Inc.',
  'PFE': 'Pfizer Inc.',
  'AVGO': 'Broadcom Inc.',
  'KO': 'Coca-Cola Co.',
  'LLY': 'Eli Lilly & Co.',
  'COST': 'Costco Wholesale',
  'PEP': 'PepsiCo Inc.',
  'MRK': 'Merck & Co.',
  'TMO': 'Thermo Fisher',
  'DIS': 'Walt Disney Co.',
  'ABT': 'Abbott Labs',
  'NFLX': 'Netflix Inc.',
  'ADBE': 'Adobe Inc.',
  'CRM': 'Salesforce Inc.',
  'ORCL': 'Oracle Corp.',
  'ACN': 'Accenture PLC',
  'CSCO': 'Cisco Systems',
  'TXN': 'Texas Instruments',
  'QCOM': 'Qualcomm Inc.',
  'INTC': 'Intel Corp.',
  'AMD': 'Advanced Micro Devices',
  'IBM': 'IBM Corp.',
  'NOW': 'ServiceNow Inc.',
  'UBER': 'Uber Technologies',
  'PYPL': 'PayPal Holdings',
  'SHOP': 'Shopify Inc.',
  'SNOW': 'Snowflake Inc.',
  'ZM': 'Zoom Video',
  'DOCU': 'DocuSign Inc.',
  'OKTA': 'Okta Inc.',
  'TWLO': 'Twilio Inc.'
};


// Function to get company domain for logo fetching
const getCompanyDomain = (symbol: string): string => {
  const domainMap: { [key: string]: string } = {
    'AAPL': 'apple.com',
    'MSFT': 'microsoft.com',
    'GOOGL': 'google.com',
    'AMZN': 'amazon.com',
    'NVDA': 'nvidia.com',
    'TSLA': 'tesla.com',
    'META': 'meta.com',
    'BRK.B': 'berkshirehathaway.com',
    'UNH': 'unitedhealthgroup.com',
    'JNJ': 'jnj.com',
    'XOM': 'exxonmobil.com',
    'JPM': 'jpmorganchase.com',
    'V': 'visa.com',
    'WMT': 'walmart.com',
    'PG': 'pg.com',
    'HD': 'homedepot.com',
    'CVX': 'chevron.com',
    'MA': 'mastercard.com',
    'BAC': 'bankofamerica.com',
    'ABBV': 'abbvie.com',
    'PFE': 'pfizer.com',
    'AVGO': 'broadcom.com',
    'KO': 'coca-cola.com',
    'LLY': 'lilly.com',
    'COST': 'costco.com',
    'PEP': 'pepsico.com',
    'MRK': 'merck.com',
    'TMO': 'thermofisher.com',
    'DIS': 'disney.com',
    'ABT': 'abbott.com',
    'NFLX': 'netflix.com',
    'ADBE': 'adobe.com',
    'CRM': 'salesforce.com',
    'ORCL': 'oracle.com',
    'ACN': 'accenture.com',
    'CSCO': 'cisco.com',
    'TXN': 'ti.com',
    'QCOM': 'qualcomm.com',
    'INTC': 'intel.com',
    'AMD': 'amd.com',
    'IBM': 'ibm.com',
    'NOW': 'servicenow.com',
    'UBER': 'uber.com',
    'PYPL': 'paypal.com',
    'SHOP': 'shopify.com',
    'SNOW': 'snowflake.com',
    'ZM': 'zoom.us',
    'DOCU': 'docusign.com',
    'OKTA': 'okta.com',
    'TWLO': 'twilio.com'
  };
  
  return domainMap[symbol] || `${symbol.toLowerCase()}.com`;
};

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
                tf: '1d',
                limit: 5 // Get recent daily candles for meaningful volume
              });

              if (response.candles.length > 0) {
                // Use second-to-last candle if latest has very low volume (incomplete day)
                let latestCandle = response.candles[response.candles.length - 1];
                if (response.candles.length > 1 && latestCandle.volume < 10000) {
                  latestCandle = response.candles[response.candles.length - 2];
                }
                const firstCandle = response.candles[0];
                
                const price = latestCandle.close;
                const change = price - firstCandle.open;
                const changePercent = (change / firstCandle.open) * 100;
                
                // Fetch market cap
                let marketCap = '';
                try {
                  const marketCapResponse = await fetch(`/api/market-cap/${symbol}`);
                  if (marketCapResponse.ok) {
                    const marketCapData = await marketCapResponse.json();
                    marketCap = marketCapData.formatted;
                  }
                } catch (error) {
                  console.debug(`Market cap fetch failed for ${symbol}:`, error);
                }
                
                newData.set(symbol, {
                  symbol,
                  price,
                  change,
                  changePercent,
                  volume: latestCandle.volume,
                  rvol: latestCandle.rvol || 1,
                  marketCap
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
                    <div className="flex items-center space-x-3 flex-1 min-w-0">
                      <img 
                        src={`https://logo.clearbit.com/${getCompanyDomain(symbol)}`}
                        alt={symbol}
                        className="w-8 h-8 rounded-full bg-gray-700 flex-shrink-0"
                        onError={(e) => {
                          e.currentTarget.style.display = 'none';
                        }}
                      />
                      <div className="min-w-0">
                        <div className="flex items-center space-x-2">
                          <span className="font-mono font-semibold">{symbol}</span>
                          {data && data.marketCap && (
                            <span className="text-xs text-blue-400 font-medium">
                              {data.marketCap}
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-gray-400 truncate">
                          {COMPANY_NAMES[symbol] || symbol}
                        </div>
                      </div>
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
                      <span>Vol: {data.volume >= 1000000 ? (data.volume/1000000).toFixed(1) + 'M' : data.volume.toLocaleString()}</span>
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