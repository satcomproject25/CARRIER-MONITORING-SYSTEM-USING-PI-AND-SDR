import { Satellite as SatType } from '@/types/satellite';
import { Radio, Eye, Activity, MapPin } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAppStore } from '@/store/appStore';

interface Props { satellite: SatType; index: number; }

const LIVE_MONITOR_NAME = 'GSAT-30';

export const SatelliteCard = ({ satellite, index }: Props) => {
  const { selectSatellite, setMonitoringSatellite } = useAppStore();
  const isOnline = satellite.status === 'online';
  const canMonitorLive = satellite.name === LIVE_MONITOR_NAME && isOnline;

  return (
    <div className="glass-card p-5 hover:border-primary/30 transition-all duration-300 group animate-fade-in"
      style={{ animationDelay: `${index * 50}ms` }}>
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
            isOnline ? 'bg-primary/10 border border-primary/30' : 'bg-destructive/10 border border-destructive/30'
          }`}>
            <Radio className={`w-5 h-5 ${isOnline ? 'text-primary' : 'text-destructive'}`} />
          </div>
          <div>
            <h3 className="font-semibold text-sm text-foreground">{satellite.name}</h3>
            <p className="text-[10px] font-mono text-muted-foreground">{satellite.band}</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <div className={`w-2 h-2 rounded-full ${isOnline ? 'status-online animate-pulse' : 'status-offline'}`} />
          <span className={`text-[10px] font-mono font-semibold ${isOnline ? 'text-success' : 'text-destructive'}`}>
            {satellite.status.toUpperCase()}
          </span>
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-3 gap-2 mb-4">
        <div className="bg-secondary/30 rounded-md p-2 text-center">
          <p className="text-[9px] text-muted-foreground uppercase">Health</p>
          <p className={`text-sm font-mono font-bold ${satellite.signalHealth > 70 ? 'text-success' : satellite.signalHealth > 30 ? 'text-warning' : 'text-destructive'}`}>
            {satellite.signalHealth}%
          </p>
        </div>
        <div className="bg-secondary/30 rounded-md p-2 text-center">
          <p className="text-[9px] text-muted-foreground uppercase">C/N</p>
          <p className="text-sm font-mono font-bold text-foreground">{satellite.cnRatio}<span className="text-[9px] text-muted-foreground">dB</span></p>
        </div>
        <div className="bg-secondary/30 rounded-md p-2 text-center">
          <p className="text-[9px] text-muted-foreground uppercase">Eb/No</p>
          <p className="text-sm font-mono font-bold text-foreground">{satellite.ebNo}<span className="text-[9px] text-muted-foreground">dB</span></p>
        </div>
      </div>

      {/* Location */}
      <div className="flex items-center gap-1.5 mb-4">
        <MapPin className="w-3 h-3 text-muted-foreground" />
        <span className="text-[10px] text-muted-foreground truncate">{satellite.groundStation}, {satellite.country}</span>
      </div>

      {/* Actions */}
      <div className="flex gap-2">
        <Button variant="outline" size="sm" className="flex-1 text-xs h-8 border-border/40 hover:border-primary/50 hover:bg-primary/5"
          onClick={() => selectSatellite(satellite)}>
          <Eye className="w-3 h-3 mr-1.5" /> View Details
        </Button>
        <Button size="sm" className="flex-1 text-xs h-8 glow-primary hover:scale-[1.02] active:scale-[0.98] transition-transform"
          onClick={() => setMonitoringSatellite(satellite)} disabled={!canMonitorLive}
          title={!canMonitorLive ? 'Live monitoring is only available for GSAT-30 on this deployment.' : undefined}>
          <Activity className="w-3 h-3 mr-1.5" /> Monitor
        </Button>
      </div>
    </div>
  );
};
