import { useRef, useEffect, useState } from 'react';
import { LogEntry } from '@/lib/dspEngine';
import { ScrollArea } from '@/components/ui/scroll-area';

interface Props {
  logs: LogEntry[];
  onClear: () => void;
}

const MAX_LOGS = 5000;

export const DetectionLog = ({ logs, onClear }: Props) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const isScrollingRef = useRef(false);
  const scrollTimeoutRef = useRef<NodeJS.Timeout>();

  // Limit logs to 5000 entries
  const displayLogs = logs.slice(-MAX_LOGS);

  useEffect(() => {
    // Only scroll if auto-scroll is enabled
    if (!autoScroll) return;

    const viewport = scrollRef.current?.querySelector('[data-radix-scroll-area-viewport]');
    if (!viewport) return;

    // Use requestAnimationFrame to ensure DOM has updated
    requestAnimationFrame(() => {
      viewport.scrollTop = viewport.scrollHeight;
    });
  }, [displayLogs.length, autoScroll]);

  const handleScroll = () => {
    // Prevent scroll handler from running during programmatic scrolls
    if (isScrollingRef.current) return;

    const viewport = scrollRef.current?.querySelector('[data-radix-scroll-area-viewport]');
    if (!viewport) return;

    // Clear existing timeout
    if (scrollTimeoutRef.current) {
      clearTimeout(scrollTimeoutRef.current);
    }

    // Debounce scroll detection
    scrollTimeoutRef.current = setTimeout(() => {
      if (!autoScroll) return; // Don't change state if already OFF

      const isAtBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < 50;
      
      // Only disable auto-scroll if user scrolled away from bottom
      if (!isAtBottom) {
        setAutoScroll(false);
      }
    }, 100);
  };

  const toggleAutoScroll = () => {
    const newAutoScroll = !autoScroll;
    setAutoScroll(newAutoScroll);
    
    // If enabling auto-scroll, immediately scroll to bottom
    if (newAutoScroll) {
      isScrollingRef.current = true;
      const viewport = scrollRef.current?.querySelector('[data-radix-scroll-area-viewport]');
      if (viewport) {
        requestAnimationFrame(() => {
          viewport.scrollTop = viewport.scrollHeight;
          // Reset flag after scroll completes
          setTimeout(() => {
            isScrollingRef.current = false;
          }, 100);
        });
      }
    }
  };

  return (
    <div className="glass-card p-4 h-full flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-bold text-foreground">Carrier & Interference Detection Log</h3>
          <p className="text-[10px] font-mono text-muted-foreground">
            REAL-TIME DETECTION EVENTS • {displayLogs.length} entries {displayLogs.length >= MAX_LOGS && `(max ${MAX_LOGS})`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={toggleAutoScroll}
            className={`text-[10px] font-mono px-2 py-1 rounded border transition-colors ${
              autoScroll ? 'border-primary/40 text-primary bg-primary/5' : 'border-border/40 text-muted-foreground'
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
          {displayLogs.length === 0 && (
            <p className="text-muted-foreground/50 py-4 text-center">Waiting for detections...</p>
          )}
          {displayLogs.map((log, i) => (
            <div key={`${i}-${log.time}`} className="flex gap-2">
              <span className="text-muted-foreground/60 shrink-0">{log.time}</span>
              <span style={{ color: log.color }}>{log.message}</span>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
};
