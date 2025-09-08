import { useState, useEffect } from 'react';
import { X, Save, AlertCircle, Activity } from 'lucide-react';
import { api, type Settings, type HealthStatus } from '../lib/api';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function SettingsModal({ isOpen, onClose }: SettingsModalProps) {
  const [settings, setSettings] = useState<Settings>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string>('');
  const [success, setSuccess] = useState<string>('');
  const [healthStatus, setHealthStatus] = useState<HealthStatus | null>(null);

  useEffect(() => {
    if (isOpen) {
      loadSettings();
    }
  }, [isOpen]);

  const loadSettings = async () => {
    try {
      setLoading(true);
      const [settingsResponse, healthResponse] = await Promise.all([
        api.getSettings(),
        api.getHealth()
      ]);
      setSettings(settingsResponse.settings || {});
      setHealthStatus(healthResponse);
      setError('');
    } catch (err) {
      setError(`Failed to load settings: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setError('');
      setSuccess('');

      await api.updateSettings(settings);
      setSuccess('Settings saved successfully!');
      
      // Auto-close after a short delay
      setTimeout(() => {
        onClose();
      }, 1500);
    } catch (err) {
      setError(`Failed to save settings: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  const updateSetting = (key: keyof Settings, value: string | number) => {
    setSettings(prev => ({
      ...prev,
      [key]: value
    }));
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="trading-card p-6 w-full max-w-2xl max-h-[80vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold">Settings</h2>
          <div className="flex items-center space-x-3">
            {/* API Quota Status */}
            {healthStatus && (
              <div className="flex items-center space-x-2 text-sm">
                <Activity className="w-4 h-4 text-blue-400" />
                <span className="text-gray-300">API Usage:</span>
                <span className={`font-mono ${
                  (healthStatus.budget_remaining_today || 500) < 100 ? 'text-red-400' : 
                  (healthStatus.budget_remaining_today || 500) < 200 ? 'text-yellow-400' : 'text-green-400'
                }`}>
                  {healthStatus.rest_calls_today || 0} / 500
                </span>
              </div>
            )}
            <button
              onClick={onClose}
              className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {loading ? (
          <div className="text-center py-8">
            <div className="text-gray-400">Loading settings...</div>
          </div>
        ) : (
          <div className="space-y-6">
            {/* API Configuration */}
            <div>
              <h3 className="text-lg font-semibold mb-4">API Configuration</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-2">
                    Finnhub API Key <span className="text-red-400">*</span>
                  </label>
                  <input
                    type="password"
                    value={settings.finnhub_api_key || ''}
                    onChange={(e) => updateSetting('finnhub_api_key', e.target.value)}
                    className="trading-input w-full"
                    placeholder="Enter your Finnhub API key"
                  />
                  <p className="text-xs text-gray-400 mt-1">
                    Get your API key from <a href="https://finnhub.io" target="_blank" className="text-blue-400 hover:underline">finnhub.io</a>
                  </p>
                </div>
              </div>
            </div>

            {/* Data Configuration */}
            <div>
              <h3 className="text-lg font-semibold mb-4">Data Configuration</h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Lookback Days</label>
                  <input
                    type="number"
                    min="1"
                    max="365"
                    value={settings.lookback_days || 30}
                    onChange={(e) => updateSetting('lookback_days', parseInt(e.target.value))}
                    className="trading-input w-full"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium mb-2">Base Timeframe</label>
                  <select
                    value={settings.base_timeframe || '5m'}
                    onChange={(e) => updateSetting('base_timeframe', e.target.value)}
                    className="trading-select w-full"
                  >
                    <option value="1m">1 Minute</option>
                    <option value="5m">5 Minutes</option>
                    <option value="15m">15 Minutes</option>
                  </select>
                </div>

                <div className="col-span-2">
                  <label className="block text-sm font-medium mb-2">Universe Symbol</label>
                  <input
                    type="text"
                    value={settings.universe_symbol || '^NDX'}
                    onChange={(e) => updateSetting('universe_symbol', e.target.value)}
                    className="trading-input w-full"
                    placeholder="e.g., ^NDX for NASDAQ-100"
                  />
                  <p className="text-xs text-gray-400 mt-1">
                    Index symbol to fetch constituents from (e.g., ^NDX, ^SPX)
                  </p>
                </div>
                
                <div className="col-span-2">
                  <label className="flex items-center space-x-2">
                    <input
                      type="checkbox"
                      checked={settings.include_extended_hours || false}
                      onChange={(e) => updateSetting('include_extended_hours', e.target.checked)}
                      className="rounded border-gray-600 text-blue-600 focus:ring-blue-500 focus:ring-offset-gray-800"
                    />
                    <span className="text-sm font-medium">Include Extended Hours</span>
                  </label>
                  <p className="text-xs text-gray-400 mt-1">
                    Include pre-market (4:00-9:30 AM ET) and after-hours (4:00-8:00 PM ET) trading
                  </p>
                </div>
              </div>
            </div>

            {/* Alert Configuration */}
            <div>
              <h3 className="text-lg font-semibold mb-4">Alert Configuration</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Discord Webhook URL</label>
                  <input
                    type="url"
                    value={settings.discord_webhook_url || ''}
                    onChange={(e) => updateSetting('discord_webhook_url', e.target.value)}
                    className="trading-input w-full"
                    placeholder="https://discord.com/api/webhooks/..."
                  />
                  <p className="text-xs text-gray-400 mt-1">
                    Optional: Discord webhook for signal alerts
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-2">Telegram Bot Token</label>
                    <input
                      type="password"
                      value={settings.telegram_bot_token || ''}
                      onChange={(e) => updateSetting('telegram_bot_token', e.target.value)}
                      className="trading-input w-full"
                      placeholder="1234567890:ABC..."
                    />
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium mb-2">Telegram Chat ID</label>
                    <input
                      type="text"
                      value={settings.telegram_chat_id || ''}
                      onChange={(e) => updateSetting('telegram_chat_id', e.target.value)}
                      className="trading-input w-full"
                      placeholder="-1001234567890"
                    />
                  </div>
                </div>
                <p className="text-xs text-gray-400">
                  Optional: Telegram bot credentials for signal alerts
                </p>
              </div>
            </div>

            {/* Error/Success Messages */}
            {error && (
              <div className="bg-red-600/20 border border-red-500/50 rounded-lg p-3 flex items-start space-x-2">
                <AlertCircle className="w-5 h-5 text-red-400 mt-0.5 flex-shrink-0" />
                <div className="text-red-300 text-sm">{error}</div>
              </div>
            )}

            {success && (
              <div className="bg-green-600/20 border border-green-500/50 rounded-lg p-3 flex items-start space-x-2">
                <div className="w-5 h-5 rounded-full bg-green-500 flex items-center justify-center mt-0.5 flex-shrink-0">
                  <div className="w-2 h-2 bg-white rounded-full"></div>
                </div>
                <div className="text-green-300 text-sm">{success}</div>
              </div>
            )}

            {/* Actions */}
            <div className="flex justify-end space-x-3 pt-4 border-t border-gray-700">
              <button
                onClick={onClose}
                className="trading-button px-6 py-2 text-gray-300 hover:bg-gray-700"
                disabled={saving}
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving || !settings.finnhub_api_key}
                className="trading-button trading-button-primary px-6 py-2 flex items-center"
              >
                <Save className="w-4 h-4 mr-2" />
                {saving ? 'Saving...' : 'Save Settings'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}