import { createChart, IChartApi, ISeriesApi, LineStyle, ColorType } from 'lightweight-charts';
import type { Candle } from './api';

export interface ChartData {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface IndicatorData {
  time: number;
  value: number;
}

export class TradingChart {
  private chart: IChartApi;
  private candlestickSeries!: ISeriesApi<'Candlestick'>;
  private volumeSeries!: ISeriesApi<'Histogram'>;
  private ema9Series!: ISeriesApi<'Line'>;
  private ema21Series!: ISeriesApi<'Line'>;
  private vwapSeries!: ISeriesApi<'Line'>;
  private bbUpperSeries!: ISeriesApi<'Line'>;
  private bbMiddleSeries!: ISeriesApi<'Line'>;
  private bbLowerSeries!: ISeriesApi<'Line'>;
  private rsiSeries!: ISeriesApi<'Line'>;
  private rsiChart!: IChartApi;

  constructor(container: HTMLElement) {
    // Main chart
    this.chart = createChart(container, {
      width: container.clientWidth,
      height: container.clientHeight * 0.75, // 75% for main chart
      layout: {
        background: { type: ColorType.Solid, color: '#1f2937' },
        textColor: '#d1d5db',
        fontSize: 12,
        fontFamily: 'JetBrains Mono, Consolas, Monaco, monospace',
      },
      grid: {
        vertLines: { color: '#374151' },
        horzLines: { color: '#374151' },
      },
      rightPriceScale: {
        borderColor: '#4b5563',
        textColor: '#d1d5db',
      },
      timeScale: {
        borderColor: '#4b5563',
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        mode: 1, // Normal crosshair
      },
    });

    // RSI subchart
    const rsiContainer = document.createElement('div');
    rsiContainer.style.height = `${container.clientHeight * 0.25}px`; // 25% for RSI
    container.appendChild(rsiContainer);

    this.rsiChart = createChart(rsiContainer, {
      width: container.clientWidth,
      height: container.clientHeight * 0.25,
      layout: {
        background: { type: ColorType.Solid, color: '#1f2937' },
        textColor: '#d1d5db',
        fontSize: 12,
        fontFamily: 'JetBrains Mono, Consolas, Monaco, monospace',
      },
      grid: {
        vertLines: { color: '#374151' },
        horzLines: { color: '#374151' },
      },
      rightPriceScale: {
        borderColor: '#4b5563',
        textColor: '#d1d5db',
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      timeScale: {
        borderColor: '#4b5563',
        visible: false, // Hide time scale for subchart
      },
    });

    this.initializeSeries();
    this.setupEventHandlers();
  }

  private initializeSeries() {
    // Candlestick series
    this.candlestickSeries = this.chart.addCandlestickSeries({
      upColor: '#10b981', // Green
      downColor: '#ef4444', // Red
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    });

    // Volume series (histogram)
    this.volumeSeries = this.chart.addHistogramSeries({
      color: '#6b7280',
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: 'volume',
    });

    // Volume price scale
    this.chart.priceScale('volume').applyOptions({
      scaleMargins: {
        top: 0.8,
        bottom: 0,
      },
    });

    // EMA series
    this.ema9Series = this.chart.addLineSeries({
      color: '#3b82f6', // Blue
      lineWidth: 2,
      title: 'EMA 9',
    });

    this.ema21Series = this.chart.addLineSeries({
      color: '#f59e0b', // Orange
      lineWidth: 2,
      title: 'EMA 21',
    });

    // VWAP series
    this.vwapSeries = this.chart.addLineSeries({
      color: '#8b5cf6', // Purple
      lineWidth: 2,
      lineStyle: LineStyle.Dashed,
      title: 'VWAP',
    });

    // Bollinger Bands
    this.bbUpperSeries = this.chart.addLineSeries({
      color: '#6b7280', // Gray
      lineWidth: 1,
      lineStyle: LineStyle.Dotted,
      title: 'BB Upper',
    });

    this.bbMiddleSeries = this.chart.addLineSeries({
      color: '#6b7280', // Gray
      lineWidth: 1,
      title: 'BB Middle',
    });

    this.bbLowerSeries = this.chart.addLineSeries({
      color: '#6b7280', // Gray
      lineWidth: 1,
      lineStyle: LineStyle.Dotted,
      title: 'BB Lower',
    });

    // RSI series
    this.rsiSeries = this.rsiChart.addLineSeries({
      color: '#14b8a6', // Teal
      lineWidth: 2,
      title: 'RSI(14)',
    });

    // Add RSI reference lines
    this.rsiChart.addLineSeries({
      color: '#ef4444', // Red
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
    }).setData([
      { time: 0 as any, value: 70 }, // Overbought line
    ]);

    this.rsiChart.addLineSeries({
      color: '#10b981', // Green
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
    }).setData([
      { time: 0 as any, value: 30 }, // Oversold line
    ]);

    // Set RSI scale range
    this.rsiChart.priceScale('').applyOptions({
      scaleMargins: { top: 0.1, bottom: 0.1 },
      entireTextOnly: true,
    });
  }

  private setupEventHandlers() {
    // Sync crosshairs between main chart and RSI
    this.chart.subscribeCrosshairMove((param) => {
      if (param.time !== undefined) {
        this.rsiChart.setCrosshairPosition(param.point?.x ?? 0, 0 as any, param.time as any);
      } else {
        this.rsiChart.clearCrosshairPosition();
      }
    });

    this.rsiChart.subscribeCrosshairMove((param) => {
      if (param.time !== undefined) {
        this.chart.setCrosshairPosition(param.point?.x ?? 0, 0 as any, param.time as any);
      } else {
        this.chart.clearCrosshairPosition();
      }
    });
  }

  updateData(candles: Candle[]) {
    if (candles.length === 0) return;

    // Convert candles to chart format
    const candleData: ChartData[] = candles.map(candle => ({
      time: candle.time,
      open: candle.open,
      high: candle.high,
      low: candle.low,
      close: candle.close,
      volume: candle.volume,
    }));

    // Set candlestick data
    this.candlestickSeries.setData(candleData as any);

    // Set volume data
    const volumeData = candles.map(candle => ({
      time: candle.time,
      value: candle.volume,
      color: candle.close >= candle.open ? '#10b98150' : '#ef444450', // Semi-transparent
    }));
    this.volumeSeries.setData(volumeData as any);

    // Set indicator data
    this.updateIndicators(candles);

    // Fit content
    this.chart.timeScale().fitContent();
    this.rsiChart.timeScale().fitContent();
  }

  private updateIndicators(candles: Candle[]) {
    // EMA 9
    const ema9Data = candles
      .filter(candle => candle.ema_9 !== undefined)
      .map(candle => ({
        time: candle.time,
        value: candle.ema_9!,
      }));
    if (ema9Data.length > 0) {
      this.ema9Series.setData(ema9Data as any);
    }

    // EMA 21
    const ema21Data = candles
      .filter(candle => candle.ema_21 !== undefined)
      .map(candle => ({
        time: candle.time,
        value: candle.ema_21!,
      }));
    if (ema21Data.length > 0) {
      this.ema21Series.setData(ema21Data as any);
    }

    // VWAP
    const vwapData = candles
      .filter(candle => candle.vwap !== undefined)
      .map(candle => ({
        time: candle.time,
        value: candle.vwap!,
      }));
    if (vwapData.length > 0) {
      this.vwapSeries.setData(vwapData as any);
    }

    // Bollinger Bands
    const bbUpperData = candles
      .filter(candle => candle.bb_upper !== undefined)
      .map(candle => ({
        time: candle.time,
        value: candle.bb_upper!,
      }));
    if (bbUpperData.length > 0) {
      this.bbUpperSeries.setData(bbUpperData as any);
    }

    const bbMiddleData = candles
      .filter(candle => candle.bb_middle !== undefined)
      .map(candle => ({
        time: candle.time,
        value: candle.bb_middle!,
      }));
    if (bbMiddleData.length > 0) {
      this.bbMiddleSeries.setData(bbMiddleData as any);
    }

    const bbLowerData = candles
      .filter(candle => candle.bb_lower !== undefined)
      .map(candle => ({
        time: candle.time,
        value: candle.bb_lower!,
      }));
    if (bbLowerData.length > 0) {
      this.bbLowerSeries.setData(bbLowerData as any);
    }

    // RSI
    const rsiData = candles
      .filter(candle => candle.rsi !== undefined)
      .map(candle => ({
        time: candle.time,
        value: candle.rsi!,
      }));
    if (rsiData.length > 0) {
      this.rsiSeries.setData(rsiData as any);
    }
  }

  addSignalMarker(time: number, _price: number, _details: string) {
    // Add a marker for a signal
    this.candlestickSeries.setMarkers([
      {
        time: time as any,
        position: 'belowBar',
        color: '#10b981',
        shape: 'arrowUp',
        text: 'LONG',
        size: 2,
      },
    ]);
  }

  resize(width: number, height: number) {
    this.chart.applyOptions({
      width,
      height: height * 0.75,
    });

    this.rsiChart.applyOptions({
      width,
      height: height * 0.25,
    });
  }

  destroy() {
    this.chart.remove();
    this.rsiChart.remove();
  }
}