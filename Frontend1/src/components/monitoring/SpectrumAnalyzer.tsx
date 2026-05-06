import { useRef, useEffect, useCallback, useState } from 'react';
import { DSP_CONFIG, DetectionResult } from '@/lib/dspEngine';

interface Props {
  data: DetectionResult | null;
  enableMaxHold: boolean;
  enableMinHold: boolean;
}

export const SpectrumAnalyzer = ({ data, enableMaxHold, enableMinHold }: Props) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 400 });
  const [mousePos, setMousePos] = useState<{ x: number; y: number; freq: number; power: number } | null>(null);

  // Margins for the plot area
  const margin = { top: 30, right: 20, bottom: 40, left: 55 };

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const obs = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setDimensions({ width: Math.floor(width), height: Math.floor(height) });
    });
    obs.observe(container);
    return () => obs.disconnect();
  }, []);

  const freqToX = useCallback((freq: number) => {
    const { CENTER_FREQ, DISPLAY_BW } = DSP_CONFIG;
    const fMin = (CENTER_FREQ - DISPLAY_BW / 2) / 1e6;
    const fMax = (CENTER_FREQ + DISPLAY_BW / 2) / 1e6;
    const plotW = dimensions.width - margin.left - margin.right;
    return margin.left + ((freq / 1e6 - fMin) / (fMax - fMin)) * plotW;
  }, [dimensions.width]);

  const powerToY = useCallback((power: number) => {
    const { Y_MIN, Y_MAX } = DSP_CONFIG;
    const plotH = dimensions.height - margin.top - margin.bottom;
    return margin.top + ((Y_MAX - power) / (Y_MAX - Y_MIN)) * plotH;
  }, [dimensions.height]);

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas || !data) return;
    const rect = canvas.getBoundingClientRect();
    const x = (e.clientX - rect.left) * (canvas.width / rect.width);
    const y = (e.clientY - rect.top) * (canvas.height / rect.height);

    const plotW = dimensions.width - margin.left - margin.right;
    const plotH = dimensions.height - margin.top - margin.bottom;
    const { CENTER_FREQ, DISPLAY_BW, Y_MIN, Y_MAX } = DSP_CONFIG;
    const fMin = (CENTER_FREQ - DISPLAY_BW / 2) / 1e6;
    const fMax = (CENTER_FREQ + DISPLAY_BW / 2) / 1e6;

    if (x >= margin.left && x <= margin.left + plotW && y >= margin.top && y <= margin.top + plotH) {
      const freq = fMin + ((x - margin.left) / plotW) * (fMax - fMin);
      const power = Y_MAX - ((y - margin.top) / plotH) * (Y_MAX - Y_MIN);
      setMousePos({ x, y, freq, power });
    } else {
      setMousePos(null);
    }
  }, [data, dimensions]);

  // Draw
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    canvas.width = dimensions.width;
    canvas.height = dimensions.height;

    const { CENTER_FREQ, DISPLAY_BW, Y_MIN, Y_MAX } = DSP_CONFIG;
    const fMin = (CENTER_FREQ - DISPLAY_BW / 2) / 1e6;
    const fMax = (CENTER_FREQ + DISPLAY_BW / 2) / 1e6;
    const plotW = dimensions.width - margin.left - margin.right;
    const plotH = dimensions.height - margin.top - margin.bottom;

    // Clear
    ctx.fillStyle = 'hsl(222, 47%, 5%)';
    ctx.fillRect(0, 0, dimensions.width, dimensions.height);

    // Grid
    ctx.strokeStyle = 'hsla(222, 30%, 25%, 0.4)';
    ctx.lineWidth = 0.5;

    // Horizontal grid lines
    for (let p = Y_MIN; p <= Y_MAX; p += 10) {
      const y = powerToY(p);
      ctx.beginPath();
      ctx.moveTo(margin.left, y);
      ctx.lineTo(margin.left + plotW, y);
      ctx.stroke();

      ctx.fillStyle = 'hsl(215, 20%, 50%)';
      ctx.font = '10px JetBrains Mono, monospace';
      ctx.textAlign = 'right';
      ctx.fillText(`${p}`, margin.left - 5, y + 3);
    }

    // Vertical grid lines
    const freqStep = 2; // MHz
    for (let f = Math.ceil(fMin / freqStep) * freqStep; f <= fMax; f += freqStep) {
      const x = margin.left + ((f - fMin) / (fMax - fMin)) * plotW;
      ctx.beginPath();
      ctx.moveTo(x, margin.top);
      ctx.lineTo(x, margin.top + plotH);
      ctx.stroke();

      ctx.fillStyle = 'hsl(215, 20%, 50%)';
      ctx.font = '10px JetBrains Mono, monospace';
      ctx.textAlign = 'center';
      ctx.fillText(`${f}`, x, margin.top + plotH + 15);
    }

    // Axis labels
    ctx.fillStyle = 'hsl(215, 20%, 60%)';
    ctx.font = '11px JetBrains Mono, monospace';
    ctx.textAlign = 'center';
    ctx.fillText('Frequency (MHz)', margin.left + plotW / 2, dimensions.height - 5);

    ctx.save();
    ctx.translate(12, margin.top + plotH / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText('Power (dB)', 0, 0);
    ctx.restore();

    // Title
    ctx.fillStyle = 'hsl(210, 40%, 92%)';
    ctx.font = 'bold 12px JetBrains Mono, monospace';
    ctx.textAlign = 'left';
    ctx.fillText('Real-Time FFT Spectrum + Carrier Detection', margin.left, 18);

    // Carrier highlights — authorized: green; unauthorized / unauth hits: red
    for (const carrier of data.carriers) {
      const x1 = freqToX(carrier.startFreq);
      const x2 = freqToX(carrier.endFreq);
      const auth = carrier.isAuthorized !== false;

      ctx.fillStyle = auth ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.28)';
      ctx.fillRect(x1, margin.top, x2 - x1, plotH);

      ctx.strokeStyle = auth ? 'rgba(249, 115, 22, 0.8)' : 'rgba(248, 113, 113, 0.9)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x1, margin.top);
      ctx.lineTo(x1, margin.top + plotH);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(x2, margin.top);
      ctx.lineTo(x2, margin.top + plotH);
      ctx.stroke();

      const cx = (x1 + x2) / 2;
      const bwKHz = carrier.bandwidth / 1e3;
      ctx.font = '9px JetBrains Mono, monospace';
      ctx.textAlign = 'center';

      const labelText = auth ? `${bwKHz.toFixed(0)} kHz` : `UNAUTH ${bwKHz.toFixed(0)} kHz`;
      const labelW = ctx.measureText(labelText).width + 8;
      ctx.fillStyle = auth ? 'rgba(34, 197, 94, 0.85)' : 'rgba(239, 68, 68, 0.9)';
      ctx.fillRect(cx - labelW / 2, margin.top + 3, labelW, 14);
      ctx.fillStyle = auth ? '#000' : '#fff';
      ctx.fillText(labelText, cx, margin.top + 13);
    }

    // Draw interference highlights (red spans)
    for (const intf of data.interferences) {
      const x1 = freqToX(intf.startFreq);
      const x2 = freqToX(intf.endFreq);

      ctx.fillStyle = 'rgba(239, 68, 68, 0.35)';
      ctx.fillRect(x1, margin.top, x2 - x1, plotH);

      const cx = (x1 + x2) / 2;
      const labelText = `INTF ${intf.strengthDb.toFixed(1)}dB`;
      const labelW = ctx.measureText(labelText).width + 8;
      ctx.fillStyle = 'rgba(239, 68, 68, 0.9)';
      ctx.fillRect(cx - labelW / 2, margin.top + 20, labelW, 14);
      ctx.fillStyle = '#fff';
      ctx.font = '8px JetBrains Mono, monospace';
      ctx.textAlign = 'center';
      ctx.fillText(labelText, cx, margin.top + 30);
    }

    // Draw noise floor line
    const nfY = powerToY(data.noiseFloor);
    ctx.strokeStyle = 'rgba(168, 85, 247, 0.6)';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(margin.left, nfY);
    ctx.lineTo(margin.left + plotW, nfY);
    ctx.stroke();
    ctx.setLineDash([]);

    // NF label
    ctx.fillStyle = 'rgba(168, 85, 247, 0.8)';
    ctx.font = '9px JetBrains Mono, monospace';
    ctx.textAlign = 'left';
    ctx.fillText(`NF: ${data.noiseFloor.toFixed(1)} dB`, margin.left + plotW - 80, nfY - 4);

    // Detection threshold line
    const dtY = powerToY(data.detectThreshold);
    ctx.strokeStyle = 'rgba(251, 191, 36, 0.4)';
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 3]);
    ctx.beginPath();
    ctx.moveTo(margin.left, dtY);
    ctx.lineTo(margin.left + plotW, dtY);
    ctx.stroke();
    ctx.setLineDash([]);

    // Draw Max Hold (green line)
    if (enableMaxHold && data.maxHold) {
      ctx.strokeStyle = 'rgba(34, 197, 94, 0.7)';
      ctx.lineWidth = 0.8;
      ctx.beginPath();
      let first = true;
      for (let i = 0; i < data.maxHold.length; i++) {
        const x = margin.left + (i / (data.maxHold.length - 1)) * plotW;
        const y = powerToY(data.maxHold[i]);
        if (y >= margin.top && y <= margin.top + plotH) {
          if (first) { ctx.moveTo(x, y); first = false; }
          else ctx.lineTo(x, y);
        }
      }
      ctx.stroke();
    }

    // Draw Min Hold (red line)
    if (enableMinHold && data.minHold) {
      ctx.strokeStyle = 'rgba(239, 68, 68, 0.5)';
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      let first = true;
      for (let i = 0; i < data.minHold.length; i++) {
        const x = margin.left + (i / (data.minHold.length - 1)) * plotW;
        const y = powerToY(data.minHold[i]);
        if (y >= margin.top && y <= margin.top + plotH) {
          if (first) { ctx.moveTo(x, y); first = false; }
          else ctx.lineTo(x, y);
        }
      }
      ctx.stroke();
    }

    // Draw live PSD (main cyan line with gradient fill)
    const gradient = ctx.createLinearGradient(0, margin.top, 0, margin.top + plotH);
    gradient.addColorStop(0, 'rgba(14, 165, 233, 0.3)');
    gradient.addColorStop(1, 'rgba(14, 165, 233, 0)');

    // Fill
    ctx.beginPath();
    ctx.moveTo(margin.left, margin.top + plotH);
    for (let i = 0; i < data.psd.length; i++) {
      const x = margin.left + (i / (data.psd.length - 1)) * plotW;
      const y = Math.max(margin.top, Math.min(margin.top + plotH, powerToY(data.psd[i])));
      ctx.lineTo(x, y);
    }
    ctx.lineTo(margin.left + plotW, margin.top + plotH);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Stroke
    ctx.strokeStyle = 'hsl(199, 89%, 48%)';
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    let started = false;
    for (let i = 0; i < data.psd.length; i++) {
      const x = margin.left + (i / (data.psd.length - 1)) * plotW;
      const y = Math.max(margin.top, Math.min(margin.top + plotH, powerToY(data.psd[i])));
      if (!started) { ctx.moveTo(x, y); started = true; }
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Mouse crosshair
    if (mousePos) {
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
      ctx.lineWidth = 0.5;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(mousePos.x, margin.top);
      ctx.lineTo(mousePos.x, margin.top + plotH);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(margin.left, mousePos.y);
      ctx.lineTo(margin.left + plotW, mousePos.y);
      ctx.stroke();
      ctx.setLineDash([]);

      // Readout
      ctx.fillStyle = 'rgba(0, 0, 0, 0.8)';
      ctx.fillRect(mousePos.x + 10, mousePos.y - 30, 130, 28);
      ctx.strokeStyle = 'rgba(14, 165, 233, 0.6)';
      ctx.lineWidth = 1;
      ctx.strokeRect(mousePos.x + 10, mousePos.y - 30, 130, 28);
      ctx.fillStyle = '#fff';
      ctx.font = '10px JetBrains Mono, monospace';
      ctx.textAlign = 'left';
      ctx.fillText(`${mousePos.freq.toFixed(3)} MHz`, mousePos.x + 15, mousePos.y - 18);
      ctx.fillText(`${mousePos.power.toFixed(1)} dB`, mousePos.x + 15, mousePos.y - 6);
    }

    // Border
    ctx.strokeStyle = 'hsl(222, 30%, 25%)';
    ctx.lineWidth = 1;
    ctx.strokeRect(margin.left, margin.top, plotW, plotH);

  }, [data, dimensions, mousePos, enableMaxHold, enableMinHold, freqToX, powerToY]);

  return (
    <div ref={containerRef} className="glass-card p-3 h-full w-full" style={{ minHeight: 400 }}>
      <canvas
        ref={canvasRef}
        className="w-full h-full cursor-crosshair"
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setMousePos(null)}
      />
    </div>
  );
};
