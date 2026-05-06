import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { Button } from '@/components/ui/button';
import { RotateCcw } from 'lucide-react';

interface Props {
  enableIntf: boolean;
  setEnableIntf: (v: boolean) => void;
  enableMaxHold: boolean;
  setEnableMaxHold: (v: boolean) => void;
  enableMinHold: boolean;
  setEnableMinHold: (v: boolean) => void;
  smoothEnabled: boolean;
  setSmoothEnabled: (v: boolean) => void;
  smoothAlpha: number;
  setSmoothAlpha: (v: number) => void;
  onResetHold: () => void;
}

export const SpectrumControls = ({
  enableIntf, setEnableIntf,
  enableMaxHold, setEnableMaxHold,
  enableMinHold, setEnableMinHold,
  smoothEnabled, setSmoothEnabled,
  smoothAlpha, setSmoothAlpha,
  onResetHold,
}: Props) => {
  const controls = [
    { label: 'Interference', checked: enableIntf, onChange: setEnableIntf, color: 'text-destructive' },
    { label: 'Max Hold', checked: enableMaxHold, onChange: setEnableMaxHold, color: 'text-success' },
    { label: 'Min Hold', checked: enableMinHold, onChange: setEnableMinHold, color: 'text-destructive/60' },
    { label: 'Smooth', checked: smoothEnabled, onChange: setSmoothEnabled, color: 'text-primary' },
  ];

  return (
    <div className="glass-card p-4">
      <h3 className="text-sm font-bold text-foreground mb-3">Detection Controls</h3>
      <div className="space-y-3">
        {controls.map((ctrl) => (
          <div key={ctrl.label} className="flex items-center justify-between">
            <span className={`text-[11px] font-mono ${ctrl.color}`}>{ctrl.label}</span>
            <Switch checked={ctrl.checked} onCheckedChange={ctrl.onChange} />
          </div>
        ))}

        {smoothEnabled && (
          <div className="pt-1">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] font-mono text-muted-foreground">Smooth α</span>
              <span className="text-[10px] font-mono text-primary">{smoothAlpha.toFixed(2)}</span>
            </div>
            <Slider
              min={0} max={100} step={1}
              value={[smoothAlpha * 100]}
              onValueChange={([v]) => setSmoothAlpha(v / 100)}
              className="w-full"
            />
            <p className="text-[9px] font-mono text-muted-foreground mt-1">
              Temporal EMA across display frames. α=0 raw, α=1 max persistence.
            </p>
          </div>
        )}

        <Button
          variant="outline" size="sm"
          onClick={onResetHold}
          className="w-full text-[10px] font-mono border-border/40 mt-2"
        >
          <RotateCcw className="w-3 h-3 mr-1.5" /> Reset Hold
        </Button>
      </div>

      {/* Stats */}
      <div className="mt-4 pt-3 border-t border-border/20">
        <h4 className="text-[10px] font-mono text-muted-foreground mb-2 uppercase tracking-wider">Config</h4>
        <div className="space-y-1 text-[10px] font-mono">
          <div className="flex justify-between">
            <span className="text-muted-foreground">FFT Size</span>
            <span className="text-foreground">2048</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Sample Rate</span>
            <span className="text-foreground">20 MHz</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Center Freq</span>
            <span className="text-foreground">70 MHz</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Display BW</span>
            <span className="text-foreground">20 MHz</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Carrier k·σ</span>
            <span className="text-foreground">3.5</span>
          </div>
        </div>
      </div>
    </div>
  );
};
