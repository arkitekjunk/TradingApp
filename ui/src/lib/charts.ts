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

export class LineChart {
  private chart: IChartApi;
  private lineSeries!: ISeriesApi<'Line'>;
  private volumeSeries!: ISeriesApi<'Histogram'>;
  private ema9Series!: ISeriesApi<'Line'>;
  private ema21Series!: ISeriesApi<'Line'>;
  private vwapSeries!: ISeriesApi<'Line'>;
  private bbUpperSeries!: ISeriesApi<'Line'>;
  private bbMiddleSeries!: ISeriesApi<'Line'>;
  private bbLowerSeries!: ISeriesApi<'Line'>;
  private rsiSeries!: ISeriesApi<'Line'>;
  private rsiChart!: IChartApi;
  private isFirstLoad: boolean = true;
  private savedTimeRange: any = null;
  private userHasZoomed: boolean = false;
  private markers: Array<{ time: number; position: any; color: string; shape: any; text: string; size?: number }>;
  private zoomPersistKey: string | null = null;
  private wheelZoomEnabled: boolean = true;
  private dragPanEnabled: boolean = true;

  constructor(container: HTMLElement) {
    try {
      console.log('LineChart: Starting construction', container);
      
      // Clear any existing content
      container.innerHTML = '';
      
      // Create main chart container
      const mainContainer = document.createElement('div');
      mainContainer.style.height = `${container.clientHeight * 0.75}px`;
      mainContainer.style.width = '100%';
      container.appendChild(mainContainer);
      
      console.log('LineChart: Main container created', mainContainer.style.height);

    // Main chart
    this.chart = createChart(mainContainer, {
      width: container.clientWidth,
      height: container.clientHeight * 0.75,
      layout: {
        background: { type: ColorType.Solid, color: '#1f2937' },
        textColor: '#d1d5db',
        fontSize: 12,
        fontFamily: 'JetBrains Mono, Consolas, Monaco, monospace',
      },
      watermark: { visible: false },
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
        barSpacing: 6,
        minBarSpacing: 0.5,
        rightOffset: 12,
      },
      crosshair: { mode: 1 },
    });

    this.markers = [];

    // RSI subchart
    const rsiContainer = document.createElement('div');
    rsiContainer.style.height = `${container.clientHeight * 0.25}px`;
    rsiContainer.style.width = '100%';
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
      watermark: { visible: false },
      grid: {
        vertLines: { color: '#374151' },
        horzLines: { color: '#374151' },
      },
      rightPriceScale: {
        borderColor: '#4b5563',
        textColor: '#d1d5db',
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      timeScale: { borderColor: '#4b5563', visible: false },
    });

      this.initializeSeries();
      this.setupEventHandlers();
      this.applyInteractionOptions();
      
      console.log('LineChart: Construction completed successfully');
    } catch (error) {
      console.error('LineChart: Construction failed:', error);
      throw error;
    }
  }

  private initializeSeries() {
    // Line series (instead of candlestick)
    this.lineSeries = this.chart.addLineSeries({
      color: '#10b981',
      lineWidth: 2,
    });

    // Volume
    this.volumeSeries = this.chart.addHistogramSeries({
      color: '#6b7280',
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    });
    this.chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.7, bottom: 0 },
      visible: false,
    });

    // Indicators - same as candlestick chart
    this.ema9Series = this.chart.addLineSeries({ color: '#3b82f6', lineWidth: 2 });
    this.ema21Series = this.chart.addLineSeries({ color: '#f59e0b', lineWidth: 2 });
    this.vwapSeries = this.chart.addLineSeries({ color: '#8b5cf6', lineWidth: 2, lineStyle: LineStyle.Dashed });
    this.bbUpperSeries = this.chart.addLineSeries({ color: '#6b7280', lineWidth: 1, lineStyle: LineStyle.Dotted });
    this.bbMiddleSeries = this.chart.addLineSeries({ color: '#6b7280', lineWidth: 1 });
    this.bbLowerSeries = this.chart.addLineSeries({ color: '#6b7280', lineWidth: 1, lineStyle: LineStyle.Dotted });

    // RSI - same as candlestick chart
    this.rsiSeries = this.rsiChart.addLineSeries({ color: '#14b8a6', lineWidth: 2 });
    this.rsiChart.addLineSeries({ color: '#ef4444', lineWidth: 1, lineStyle: LineStyle.Dashed }).setData([
      { time: 0 as any, value: 70 },
    ]);
    this.rsiChart.addLineSeries({ color: '#10b981', lineWidth: 1, lineStyle: LineStyle.Dashed }).setData([
      { time: 0 as any, value: 30 },
    ]);
    this.rsiChart.priceScale('').applyOptions({ scaleMargins: { top: 0.1, bottom: 0.1 }, entireTextOnly: true });
  }

  private setupEventHandlers() {
    // Sync crosshairs
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

    // Persist user's time range
    this.chart.timeScale().subscribeVisibleTimeRangeChange((timeRange) => {
      if (timeRange) {
        this.savedTimeRange = timeRange;
        if (!this.isFirstLoad) this.userHasZoomed = true;
        if (this.zoomPersistKey) {
          try {
            localStorage.setItem(`zoom:${this.zoomPersistKey}`, JSON.stringify(timeRange));
          } catch {}
        }
      }
    });
  }

  private applyInteractionOptions() {
    const handleScale: any = this.wheelZoomEnabled
      ? { axisPressedMouseMove: false, mouseWheel: true, pinch: true }
      : { axisPressedMouseMove: false, mouseWheel: false, pinch: false };
    const handleScroll: any = this.dragPanEnabled
      ? { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true }
      : { mouseWheel: false, pressedMouseMove: false, horzTouchDrag: false, vertTouchDrag: false };
    try {
      (this.chart as any).applyOptions({ handleScale, handleScroll });
    } catch {}
  }

  setZoomPersistenceKey(key: string) {
    this.zoomPersistKey = key;
    try {
      const raw = localStorage.getItem(`zoom:${key}`);
      if (raw) {
        const rng = JSON.parse(raw);
        this.savedTimeRange = rng;
        this.userHasZoomed = true;
        this.chart.timeScale().setVisibleRange(rng);
        this.rsiChart.timeScale().setVisibleRange(rng);
      }
    } catch {}
  }

  setInteractionOptions(opts: { wheelZoom?: boolean; dragPan?: boolean }) {
    if (typeof opts.wheelZoom === 'boolean') this.wheelZoomEnabled = opts.wheelZoom;
    if (typeof opts.dragPan === 'boolean') this.dragPanEnabled = opts.dragPan;
    this.applyInteractionOptions();
  }

  updateData(candles: Candle[]) {
    if (candles.length === 0) return;

    // Line data (using closing prices)
    const lineData = candles.map(c => ({
      time: c.time,
      value: c.close
    }));
    this.lineSeries.setData(lineData as any);

    // Volume - same as candlestick chart
    const volumeData = candles.map(c => ({ time: c.time, value: c.volume, color: c.close >= c.open ? '#10b98180' : '#ef444480' }));
    this.volumeSeries.setData(volumeData as any);

    // Indicators - same as candlestick chart
    this.updateIndicators(candles);

    // Zoom handling - same as candlestick chart
    if (this.userHasZoomed && this.savedTimeRange) {
      try {
        this.chart.timeScale().setVisibleRange(this.savedTimeRange);
        this.rsiChart.timeScale().setVisibleRange(this.savedTimeRange);
      } catch {}
      return;
    }

    if (this.isFirstLoad) {
      this.chart.timeScale().fitContent();
      this.rsiChart.timeScale().fitContent();
      this.isFirstLoad = false;
    }
  }

  private updateIndicators(candles: Candle[]) {
    const ema9Data = candles.filter(c => c.ema_9 !== undefined).map(c => ({ time: c.time, value: c.ema_9! }));
    if (ema9Data.length) this.ema9Series.setData(ema9Data as any);

    const ema21Data = candles.filter(c => c.ema_21 !== undefined).map(c => ({ time: c.time, value: c.ema_21! }));
    if (ema21Data.length) this.ema21Series.setData(ema21Data as any);

    const vwapData = candles.filter(c => c.vwap !== undefined).map(c => ({ time: c.time, value: c.vwap! }));
    if (vwapData.length) this.vwapSeries.setData(vwapData as any);

    const bbU = candles.filter(c => c.bb_upper !== undefined).map(c => ({ time: c.time, value: c.bb_upper! }));
    if (bbU.length) this.bbUpperSeries.setData(bbU as any);

    const bbM = candles.filter(c => c.bb_middle !== undefined).map(c => ({ time: c.time, value: c.bb_middle! }));
    if (bbM.length) this.bbMiddleSeries.setData(bbM as any);

    const bbL = candles.filter(c => c.bb_lower !== undefined).map(c => ({ time: c.time, value: c.bb_lower! }));
    if (bbL.length) this.bbLowerSeries.setData(bbL as any);

    const rsi = candles.filter(c => c.rsi !== undefined).map(c => ({ time: c.time, value: c.rsi! }));
    if (rsi.length) this.rsiSeries.setData(rsi as any);
  }

  addSignalMarker(time: number, _price: number, _details: string) {
    this.markers.push({ time: time as any, position: 'belowBar', color: '#10b981', shape: 'arrowUp', text: 'LONG', size: 2 });
    this.lineSeries.setMarkers(this.markers as any);
  }

  setMarkers(markers: Array<{ time: number; position: any; color: string; shape: any; text: string; size?: number }>) {
    this.markers = markers;
    this.lineSeries.setMarkers(this.markers as any);
  }

  resize(width: number, height: number) {
    this.chart.applyOptions({ width, height: height * 0.75 });
    this.rsiChart.applyOptions({ width, height: height * 0.25 });
    if (this.savedTimeRange) {
      try {
        this.chart.timeScale().setVisibleRange(this.savedTimeRange);
        this.rsiChart.timeScale().setVisibleRange(this.savedTimeRange);
      } catch {}
    }
  }

  zoomIn() {
    const ts = this.chart.timeScale();
    const range = ts.getVisibleLogicalRange();
    if (!range) return;
    const current = range.to - range.from;
    if (current <= 20) return;
    const newRange = Math.max(20, current * 0.7);
    const center = (range.from + range.to) / 2;
    ts.setVisibleLogicalRange({ from: center - newRange / 2, to: center + newRange / 2 });
    this.userHasZoomed = true;
  }

  zoomOut() {
    const ts = this.chart.timeScale();
    const range = ts.getVisibleLogicalRange();
    if (!range) return;
    const current = range.to - range.from;
    const newRange = Math.min(current * 1.4, 5000);
    const center = (range.from + range.to) / 2;
    ts.setVisibleLogicalRange({ from: center - newRange / 2, to: center + newRange / 2 });
    this.userHasZoomed = true;
  }

  fitContent() {
    // Clear any saved zoom state first
    this.userHasZoomed = false;
    this.savedTimeRange = null;
    if (this.zoomPersistKey) {
      try { localStorage.removeItem(`zoom:${this.zoomPersistKey}`); } catch {}
    }
    
    // Force both time and price scales to fit content
    this.chart.timeScale().fitContent();
    this.rsiChart.timeScale().fitContent();
    
    // Also reset price scale to auto-fit the data range
    try {
      (this.chart as any).priceScale('right').applyOptions({
        autoScale: true
      });
    } catch {}
  }

  zoomToRange(days: number) {
    const ts = this.chart.timeScale();
    const vr = ts.getVisibleRange();
    if (!vr) return;
    const end = Number((vr.to as unknown) as number);
    const start = end - (days * 24 * 60 * 60);
    ts.setVisibleRange({ from: start as any, to: end as any });
    this.userHasZoomed = true;
  }

  destroy() {
    try {
      this.chart.remove();
      this.rsiChart.remove();
    } catch (error) {
      console.warn('Error destroying LineChart:', error);
    }
  }
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
  private isFirstLoad: boolean = true;
  private savedTimeRange: any = null; // persisted time range (from/to)
  private userHasZoomed: boolean = false;
  private markers: Array<{ time: number; position: any; color: string; shape: any; text: string; size?: number }>; // cache markers
  private zoomPersistKey: string | null = null;
  private wheelZoomEnabled: boolean = true;
  private dragPanEnabled: boolean = true;

  constructor(container: HTMLElement) {
    // Clear any existing content first
    container.innerHTML = '';
    
    // Main chart
    this.chart = createChart(container, {
      width: container.clientWidth,
      height: container.clientHeight * 0.75,
      layout: {
        background: { type: ColorType.Solid, color: '#1f2937' },
        textColor: '#d1d5db',
        fontSize: 12,
        fontFamily: 'JetBrains Mono, Consolas, Monaco, monospace',
      },
      watermark: { visible: false },
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
        barSpacing: 6,
        minBarSpacing: 0.5,
        rightOffset: 12,
      },
      crosshair: { mode: 1 },
    });

    this.markers = [];

    // RSI subchart
    const rsiContainer = document.createElement('div');
    rsiContainer.style.height = `${container.clientHeight * 0.25}px`;
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
      watermark: { visible: false },
      grid: {
        vertLines: { color: '#374151' },
        horzLines: { color: '#374151' },
      },
      rightPriceScale: {
        borderColor: '#4b5563',
        textColor: '#d1d5db',
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      timeScale: { borderColor: '#4b5563', visible: false },
    });

    this.initializeSeries();
    this.setupEventHandlers();

    // Default interaction options
    this.applyInteractionOptions();
  }

  private initializeSeries() {
    // Candlestick
    this.candlestickSeries = this.chart.addCandlestickSeries({
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    });

    // Volume
    this.volumeSeries = this.chart.addHistogramSeries({
      color: '#6b7280',
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    });
    this.chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.7, bottom: 0 },
      visible: false,
    });

    // Indicators
    this.ema9Series = this.chart.addLineSeries({ color: '#3b82f6', lineWidth: 2 });
    this.ema21Series = this.chart.addLineSeries({ color: '#f59e0b', lineWidth: 2 });
    this.vwapSeries = this.chart.addLineSeries({ color: '#8b5cf6', lineWidth: 2, lineStyle: LineStyle.Dashed });
    this.bbUpperSeries = this.chart.addLineSeries({ color: '#6b7280', lineWidth: 1, lineStyle: LineStyle.Dotted });
    this.bbMiddleSeries = this.chart.addLineSeries({ color: '#6b7280', lineWidth: 1 });
    this.bbLowerSeries = this.chart.addLineSeries({ color: '#6b7280', lineWidth: 1, lineStyle: LineStyle.Dotted });

    // RSI
    this.rsiSeries = this.rsiChart.addLineSeries({ color: '#14b8a6', lineWidth: 2 });
    this.rsiChart.addLineSeries({ color: '#ef4444', lineWidth: 1, lineStyle: LineStyle.Dashed }).setData([
      { time: 0 as any, value: 70 },
    ]);
    this.rsiChart.addLineSeries({ color: '#10b981', lineWidth: 1, lineStyle: LineStyle.Dashed }).setData([
      { time: 0 as any, value: 30 },
    ]);
    this.rsiChart.priceScale('').applyOptions({ scaleMargins: { top: 0.1, bottom: 0.1 }, entireTextOnly: true });
  }

  private setupEventHandlers() {
    // Sync crosshairs
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

    // Persist user's time range
    this.chart.timeScale().subscribeVisibleTimeRangeChange((timeRange) => {
      if (timeRange) {
        this.savedTimeRange = timeRange;
        if (!this.isFirstLoad) this.userHasZoomed = true;
        // Persist per key
        if (this.zoomPersistKey) {
          try {
            localStorage.setItem(`zoom:${this.zoomPersistKey}`, JSON.stringify(timeRange));
          } catch {}
        }
      }
    });
  }

  private applyInteractionOptions() {
    // Best-effort: newer lightweight-charts accepts object options; older versions ignore gracefully.
    const handleScale: any = this.wheelZoomEnabled
      ? { axisPressedMouseMove: false, mouseWheel: true, pinch: true }
      : { axisPressedMouseMove: false, mouseWheel: false, pinch: false };
    const handleScroll: any = this.dragPanEnabled
      ? { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true }
      : { mouseWheel: false, pressedMouseMove: false, horzTouchDrag: false, vertTouchDrag: false };
    try {
      (this.chart as any).applyOptions({ handleScale, handleScroll });
    } catch {}
  }

  setZoomPersistenceKey(key: string) {
    this.zoomPersistKey = key;
    // Try restore
    try {
      const raw = localStorage.getItem(`zoom:${key}`);
      if (raw) {
        const rng = JSON.parse(raw);
        this.savedTimeRange = rng;
        this.userHasZoomed = true;
        this.chart.timeScale().setVisibleRange(rng);
        this.rsiChart.timeScale().setVisibleRange(rng);
      }
    } catch {}
  }

  setInteractionOptions(opts: { wheelZoom?: boolean; dragPan?: boolean }) {
    if (typeof opts.wheelZoom === 'boolean') this.wheelZoomEnabled = opts.wheelZoom;
    if (typeof opts.dragPan === 'boolean') this.dragPanEnabled = opts.dragPan;
    this.applyInteractionOptions();
  }

  updateData(candles: Candle[]) {
    if (candles.length === 0) return;

    // Candles
    const candleData: ChartData[] = candles.map(c => ({
      time: c.time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
      volume: c.volume,
    }));
    this.candlestickSeries.setData(candleData as any);

    // Volume
    const volumeData = candles.map(c => ({ time: c.time, value: c.volume, color: c.close >= c.open ? '#10b98180' : '#ef444480' }));
    this.volumeSeries.setData(volumeData as any);

    // Indicators
    this.updateIndicators(candles);

    // Respect user's zoom: restore previous time range if they have zoomed
    if (this.userHasZoomed && this.savedTimeRange) {
      try {
        this.chart.timeScale().setVisibleRange(this.savedTimeRange);
        this.rsiChart.timeScale().setVisibleRange(this.savedTimeRange);
      } catch {}
      return;
    }

    // Initial fit only once
    if (this.isFirstLoad) {
      this.chart.timeScale().fitContent();
      this.rsiChart.timeScale().fitContent();
      this.isFirstLoad = false;
    }
  }

  private updateIndicators(candles: Candle[]) {
    const ema9Data = candles.filter(c => c.ema_9 !== undefined).map(c => ({ time: c.time, value: c.ema_9! }));
    if (ema9Data.length) this.ema9Series.setData(ema9Data as any);

    const ema21Data = candles.filter(c => c.ema_21 !== undefined).map(c => ({ time: c.time, value: c.ema_21! }));
    if (ema21Data.length) this.ema21Series.setData(ema21Data as any);

    const vwapData = candles.filter(c => c.vwap !== undefined).map(c => ({ time: c.time, value: c.vwap! }));
    if (vwapData.length) this.vwapSeries.setData(vwapData as any);

    const bbU = candles.filter(c => c.bb_upper !== undefined).map(c => ({ time: c.time, value: c.bb_upper! }));
    if (bbU.length) this.bbUpperSeries.setData(bbU as any);

    const bbM = candles.filter(c => c.bb_middle !== undefined).map(c => ({ time: c.time, value: c.bb_middle! }));
    if (bbM.length) this.bbMiddleSeries.setData(bbM as any);

    const bbL = candles.filter(c => c.bb_lower !== undefined).map(c => ({ time: c.time, value: c.bb_lower! }));
    if (bbL.length) this.bbLowerSeries.setData(bbL as any);

    const rsi = candles.filter(c => c.rsi !== undefined).map(c => ({ time: c.time, value: c.rsi! }));
    if (rsi.length) this.rsiSeries.setData(rsi as any);
  }

  addSignalMarker(time: number, _price: number, _details: string) {
    this.markers.push({ time: time as any, position: 'belowBar', color: '#10b981', shape: 'arrowUp', text: 'LONG', size: 2 });
    this.candlestickSeries.setMarkers(this.markers as any);
  }

  setMarkers(markers: Array<{ time: number; position: any; color: string; shape: any; text: string; size?: number }>) {
    this.markers = markers;
    this.candlestickSeries.setMarkers(this.markers as any);
  }

  resize(width: number, height: number) {
    this.chart.applyOptions({ width, height: height * 0.75 });
    this.rsiChart.applyOptions({ width, height: height * 0.25 });
    // Keep current zoom after resize
    if (this.savedTimeRange) {
      try {
        this.chart.timeScale().setVisibleRange(this.savedTimeRange);
        this.rsiChart.timeScale().setVisibleRange(this.savedTimeRange);
      } catch {}
    }
  }

  // Zoom controls with clamps
  zoomIn() {
    const ts = this.chart.timeScale();
    const range = ts.getVisibleLogicalRange();
    if (!range) return;
    const current = range.to - range.from;
    if (current <= 20) return; // minimum ~20 bars
    const newRange = Math.max(20, current * 0.7);
    const center = (range.from + range.to) / 2;
    ts.setVisibleLogicalRange({ from: center - newRange / 2, to: center + newRange / 2 });
    this.userHasZoomed = true;
  }

  zoomOut() {
    const ts = this.chart.timeScale();
    const range = ts.getVisibleLogicalRange();
    if (!range) return;
    const current = range.to - range.from;
    const newRange = Math.min(current * 1.4, 5000); // cap zoom-out
    const center = (range.from + range.to) / 2;
    ts.setVisibleLogicalRange({ from: center - newRange / 2, to: center + newRange / 2 });
    this.userHasZoomed = true;
  }

  fitContent() {
    // Clear any saved zoom state first
    this.userHasZoomed = false;
    this.savedTimeRange = null;
    if (this.zoomPersistKey) {
      try { localStorage.removeItem(`zoom:${this.zoomPersistKey}`); } catch {}
    }
    
    // Force both time and price scales to fit content
    this.chart.timeScale().fitContent();
    this.rsiChart.timeScale().fitContent();
    
    // Also reset price scale to auto-fit the data range
    try {
      (this.chart as any).priceScale('right').applyOptions({
        autoScale: true
      });
    } catch {}
  }

  zoomToRange(days: number) {
    const ts = this.chart.timeScale();
    const vr = ts.getVisibleRange();
    if (!vr) return;
    const end = Number((vr.to as unknown) as number);
    const start = end - (days * 24 * 60 * 60);
    ts.setVisibleRange({ from: start as any, to: end as any });
    this.userHasZoomed = true;
  }

  destroy() {
    this.chart.remove();
    this.rsiChart.remove();
  }
}