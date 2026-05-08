import { Satellite as SatType } from '@/types/satellite';
import { Radio, Eye, Activity, MapPin, Settings } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAppStore } from '@/store/appStore';

interface SatelliteMetrics {
  signalHealth: number;
  cnRatio: number;
  ebNo: number;
  noiseFloor?: number;
  lastUpdate?: number;
}

interface Props { 
  satellite: SatType; 
  index: number;
  liveMetrics?: SatelliteMetrics | null;
}

export const SatelliteCard = ({ satellite, index, liveMetrics }: Props) => {
  const { selectSatellite, setMonitoringSatellite, setEditingSatellite } = useAppStore();
  const isOnline = satellite.status === 'online';
  
  // Allow monitoring for any satellite that is online and has a valid Pi IP
  const hasValidIp = satellite.piIpAddress && satellite.piIpAddress !== '—' && !satellite.piIpAddress.includes('(');
  const canMonitor = isOnline && hasValidIp;

  // Use live metrics if available, otherwise fall back to stored values
  // For offline satellites or those without valid IP, show "—"
  const shouldShowLiveMetrics = isOnline && hasValidIp;
  
  const displayMetrics = shouldShowLiveMetrics && liveMetrics ? {
    signalHealth: liveMetrics.signalHealth,
    cnRatio: liveMetrics.cnRatio,
    ebNo: liveMetrics.ebNo,
  } : {
    signalHealth: satellite.signalHealth,
    cnRatio: satellite.cnRatio,
    ebNo: satellite.ebNo,
  };

  // Format display values - show "—" for offline or invalid
  const formatMetric = (value: number | undefined, suffix: string = '') => {
    if (!shouldShowLiveMetrics) return '—';
    if (value === undefined || value === null || !isFinite(value)) return '—';
    return `${value}${suffix}`;
  };

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
          <p className={`text-sm font-mono font-bold ${
            !shouldShowLiveMetrics || !liveMetrics ? 'text-muted-foreground' :
            displayMetrics.signalHealth > 70 ? 'text-success' : 
            displayMetrics.signalHealth > 30 ? 'text-warning' : 'text-destructive'
          }`}>
            {formatMetric(displayMetrics.signalHealth, '%')}
          </p>
        </div>
        <div className="bg-secondary/30 rounded-md p-2 text-center">
          <p className="text-[9px] text-muted-foreground uppercase">C/N</p>
          <p className={`text-sm font-mono font-bold ${!shouldShowLiveMetrics || !liveMetrics ? 'text-muted-foreground' : 'text-foreground'}`}>
            {formatMetric(displayMetrics.cnRatio)}<span className="text-[9px] text-muted-foreground">{shouldShowLiveMetrics && liveMetrics ? 'dB' : ''}</span>
          </p>
        </div>
        <div className="bg-secondary/30 rounded-md p-2 text-center">
          <p className="text-[9px] text-muted-foreground uppercase">Eb/No</p>
          <p className={`text-sm font-mono font-bold ${!shouldShowLiveMetrics || !liveMetrics ? 'text-muted-foreground' : 'text-foreground'}`}>
            {formatMetric(displayMetrics.ebNo)}<span className="text-[9px] text-muted-foreground">{shouldShowLiveMetrics && liveMetrics ? 'dB' : ''}</span>
          </p>
        </div>
      </div>

      {/* Location */}
      <div className="flex items-center gap-1.5 mb-4">
        <MapPin className="w-3 h-3 text-muted-foreground" />
        <span className="text-[10px] text-muted-foreground truncate">{satellite.groundStation}, {satellite.country}</span>
      </div>

      {/* Actions */}
      <div className="flex gap-2">
        <Button variant="ghost" size="sm" className="h-8 w-8 p-0 border-border/40 hover:border-primary/50 hover:bg-primary/5"
          onClick={() => setEditingSatellite(satellite)}
          title="Edit satellite details">
          <Settings className="w-3.5 h-3.5" />
        </Button>
        <Button variant="outline" size="sm" className="flex-1 text-xs h-8 border-border/40 hover:border-primary/50 hover:bg-primary/5"
          onClick={() => selectSatellite(satellite)}>
          <Eye className="w-3 h-3 mr-1.5" /> Details
        </Button>
        <Button size="sm" className="flex-1 text-xs h-8 glow-primary hover:scale-[1.02] active:scale-[0.98] transition-transform"
          onClick={() => setMonitoringSatellite(satellite)} disabled={!canMonitor}
          title={!canMonitor ? (isOnline ? 'No valid Pi IP address configured' : 'Satellite is offline') : 'Start live monitoring'}>
          <Activity className="w-3 h-3 mr-1.5" /> Monitor
        </Button>
      </div>
    </div>
  );
};
