import { useMemo } from 'react';
import { SignalData } from '@/types/satellite';

interface Props { data: SignalData[]; anomaly: boolean; }

export const RadarView = ({ data, anomaly }: Props) => {
  const heatmapCells = useMemo(() => {
    const cells: { x: number; y: number; intensity: number; isAnomaly: boolean }[] = [];
    const gridSize = 8;
    for (let x = 0; x < gridSize; x++) {
      for (let y = 0; y < gridSize; y++) {
        const dist = Math.sqrt((x - gridSize/2)**2 + (y - gridSize/2)**2) / (gridSize/2);
        const baseIntensity = Math.max(0, 1 - dist);
        const noise = (Math.random() - 0.5) * 0.3;
        const intensity = Math.max(0, Math.min(1, baseIntensity + noise));
        const isAnomaly = anomaly && Math.random() > 0.85 && dist > 0.3;
        cells.push({ x, y, intensity, isAnomaly });
      }
    }
    return cells;
  }, [data.length, anomaly]);

  return (
    <div className="glass-card p-5 h-full flex flex-col">
      <div className="mb-4">
        <h3 className="text-sm font-bold text-foreground">Interference Radar</h3>
        <p className="text-[10px] font-mono text-muted-foreground">CARRIER vs NOISE FLOOR HEATMAP</p>
      </div>

      {/* Radar Circle */}
      <div className="flex-1 flex items-center justify-center">
        <div className="relative w-64 h-64">
          {/* Background circles */}
          {[1, 0.75, 0.5, 0.25].map(scale => (
            <div key={scale} className="absolute rounded-full border border-border/20"
              style={{
                width: `${scale * 100}%`, height: `${scale * 100}%`,
                left: `${(1-scale)*50}%`, top: `${(1-scale)*50}%`,
              }} />
          ))}
          {/* Cross lines */}
          <div className="absolute top-0 bottom-0 left-1/2 w-px bg-border/20" />
          <div className="absolute left-0 right-0 top-1/2 h-px bg-border/20" />
          
          {/* Sweep line */}
          <div className="absolute top-1/2 left-1/2 w-1/2 h-px origin-left animate-radar"
            style={{ background: 'linear-gradient(90deg, hsl(199, 89%, 48%, 0.6), transparent)' }} />

          {/* Heatmap dots */}
          {heatmapCells.map((cell, i) => {
            const cx = (cell.x / 7) * 80 + 10;
            const cy = (cell.y / 7) * 80 + 10;
            const dist = Math.sqrt((cx-50)**2 + (cy-50)**2);
            if (dist > 45) return null;
            return (
              <div key={i} className="absolute w-2.5 h-2.5 rounded-full transition-all duration-500"
                style={{
                  left: `${cx}%`, top: `${cy}%`, transform: 'translate(-50%,-50%)',
                  backgroundColor: cell.isAnomaly
                    ? `hsla(0, 72%, 51%, ${cell.intensity})`
                    : `hsla(199, 89%, 48%, ${cell.intensity * 0.7})`,
                  boxShadow: cell.isAnomaly
                    ? `0 0 6px hsla(0, 72%, 51%, ${cell.intensity})`
                    : cell.intensity > 0.6 ? `0 0 4px hsla(199, 89%, 48%, ${cell.intensity * 0.5})` : 'none',
                }} />
            );
          })}

          {/* Labels */}
          <span className="absolute -top-5 left-1/2 -translate-x-1/2 text-[9px] font-mono text-muted-foreground">N</span>
          <span className="absolute -bottom-5 left-1/2 -translate-x-1/2 text-[9px] font-mono text-muted-foreground">S</span>
          <span className="absolute top-1/2 -left-4 -translate-y-1/2 text-[9px] font-mono text-muted-foreground">W</span>
          <span className="absolute top-1/2 -right-4 -translate-y-1/2 text-[9px] font-mono text-muted-foreground">E</span>
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center justify-center gap-4 mt-4 text-[10px] font-mono">
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-primary/70" /> Carrier
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-destructive/70" /> Interference
        </span>
      </div>
    </div>
  );
};
