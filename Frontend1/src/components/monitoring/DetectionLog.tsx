import { useRef, useEffect, useState } from 'react';
import { LogEntry } from '@/lib/dspEngine';
import { ScrollArea } from '@/components/ui/scroll-area';

interface Props {
  logs: LogEntry[];
  onClear: () => void;
}

export const DetectionLog = ({ logs, onClear }: Props) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  useEffect(() => {
    if (!autoScroll) return;
    const viewport = scrollRef.current?.querySelector('[data-radix-scroll-area-viewport]');
    if (viewport) {
      viewport.scrollTop = viewport.scrollHeight;
    }
  }, [logs.length, autoScroll]);

  const handleScroll = () => {
    const viewport = scrollRef.current?.querySelector('[data-radix-scroll-area-viewport]');
    if (!viewport) return;
    const isAtBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < 40;
    setAutoScroll(isAtBottom);
  };

  return (
    <div className="glass-card p-4 h-full flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-bold text-foreground">Carrier & Interference Detection Log</h3>
          <p className="text-[10px] font-mono text-muted-foreground">REAL-TIME DETECTION EVENTS • {logs.length} entries</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setAutoScroll(!autoScroll)}
            className={`text-[10px] font-mono px-2 py-1 rounded border transition-colors ${
              autoScroll ? 'border-primary/40 text-primary' : 'border-border/40 text-muted-foreground'
            }`}
          >
            Auto-scroll: {autoScroll ? 'ON' : 'OFF'}
          </button>
          <button
            onClick={onClear}
            className="text-[10px] font-mono px-2 py-1 rounded border border-border/40 text-muted-foreground hover:text-foreground hover:border-border/60 transition-colors"
          >
            Clear
          </button>
        </div>
      </div>

      <ScrollArea ref={scrollRef} className="flex-1 min-h-0 rounded border border-border/20 bg-background/50" onScrollCapture={handleScroll}>
        <div className="p-2 font-mono text-[10px] leading-relaxed space-y-0.5">
          {logs.length === 0 && (
            <p className="text-muted-foreground/50 py-4 text-center">Waiting for detections...</p>
          )}
          {logs.map((log, i) => (
            <div key={i} className="flex gap-2">
              <span className="text-muted-foreground/60 shrink-0">{log.time}</span>
              <span style={{ color: log.color }}>{log.message}</span>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
};
