export interface Settings {
  finnhub_api_key?: string;
  lookback_days?: number;
  base_timeframe?: string;
  universe_symbol?: string;
  discord_webhook_url?: string;
  telegram_bot_token?: string;
  telegram_chat_id?: string;
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ema_9?: number;
  ema_21?: number;
  rsi?: number;
  bb_upper?: number;
  bb_middle?: number;
  bb_lower?: number;
  vwap?: number;
  atr?: number;
  rvol?: number;
}

export interface Signal {
  id: number;
  symbol: string;
  tf: string;
  ts: string;
  rule: string;
  details: {
    price: number;
    ema_9: number;
    ema_21: number;
    rsi: number;
    vwap: number;
    rvol: number;
    volume: number;
    conditions: Record<string, boolean>;
  };
}

export interface WorkerStatus {
  running: boolean;
  ws_connected: boolean;
  symbols_count: number;
  stats: {
    ws_messages_received: number;
    trades_processed: number;
    last_trade_time?: string;
    symbols_subscribed: number;
    backfill_progress: {
      current: number;
      total: number;
      status: string;
    };
  };
}

export interface HealthStatus {
  status: string;
  timestamp: string;
  worker: WorkerStatus;
  database: string;
  storage: string;
  universe: {
    cached: boolean;
    cache_valid: boolean;
    symbols_count: number;
  };
  alerts: {
    discord: boolean;
    telegram: boolean;
  };
}

// Additional API response types
export interface SettingsResponse {
  settings: Record<string, string>;
  universe: {
    cached: boolean;
    cache_valid: boolean;
    symbols_count: number;
  };
  alert_channels: {
    discord: boolean;
    telegram: boolean;
  };
}

export interface ApiResponse {
  status: string;
  message: string;
}

export interface UniverseResponse {
  symbols: string[];
  count: number;
  cache_info: {
    cached: boolean;
    cache_valid: boolean;
    symbols_count: number;
  };
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = '/api') {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    
    const response = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || 'Request failed');
    }

    return response.json();
  }

  // Settings
  async getSettings(): Promise<SettingsResponse> {
    return this.request<SettingsResponse>('/settings');
  }

  async updateSettings(settings: Settings): Promise<ApiResponse> {
    return this.request<ApiResponse>('/settings', {
      method: 'POST',
      body: JSON.stringify(settings),
    });
  }

  // Worker control
  async startWorker(): Promise<ApiResponse> {
    return this.request<ApiResponse>('/control/start', { method: 'POST' });
  }

  async stopWorker(): Promise<ApiResponse> {
    return this.request<ApiResponse>('/control/stop', { method: 'POST' });
  }

  // Universe
  async getUniverse(): Promise<UniverseResponse> {
    return this.request<UniverseResponse>('/universe');
  }

  async refreshUniverse(): Promise<UniverseResponse & ApiResponse> {
    return this.request<UniverseResponse & ApiResponse>('/universe/refresh', { method: 'POST' });
  }

  // Candles
  async getCandles(params: {
    symbol: string;
    tf?: string;
    from_time?: string;
    to_time?: string;
    limit?: number;
  }): Promise<{ symbol: string; tf: string; candles: Candle[]; count: number }> {
    const searchParams = new URLSearchParams();
    searchParams.set('symbol', params.symbol);
    if (params.tf) searchParams.set('tf', params.tf);
    if (params.from_time) searchParams.set('from_time', params.from_time);
    if (params.to_time) searchParams.set('to_time', params.to_time);
    if (params.limit) searchParams.set('limit', params.limit.toString());

    return this.request(`/candles?${searchParams.toString()}`);
  }

  // Signals
  async getSignals(params?: {
    symbol?: string;
    tf?: string;
    limit?: number;
  }): Promise<{ signals: Signal[]; count: number }> {
    const searchParams = new URLSearchParams();
    if (params?.symbol) searchParams.set('symbol', params.symbol);
    if (params?.tf) searchParams.set('tf', params.tf);
    if (params?.limit) searchParams.set('limit', params.limit.toString());

    const query = searchParams.toString();
    return this.request(`/signals${query ? `?${query}` : ''}`);
  }

  async resendSignalAlert(signalId: number): Promise<ApiResponse> {
    return this.request<ApiResponse>(`/signals/${signalId}/alert`, { method: 'POST' });
  }

  // Health and stats
  async getHealth(): Promise<HealthStatus> {
    return this.request('/healthz');
  }

  async getStats(): Promise<any> {
    return this.request<any>('/stats');
  }
}

export const api = new ApiClient();