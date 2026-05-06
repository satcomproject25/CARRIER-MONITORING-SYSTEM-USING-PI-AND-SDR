import { X, MapPin, Cpu, User, Compass, Radio, Wifi } from 'lucide-react';
import { useAppStore } from '@/store/appStore';

export const DetailPanel = () => {
  const { selectedSatellite: sat, setShowDetailPanel } = useAppStore();
  if (!sat) return null;

  const isOnline = sat.status === 'online';
  const details = [
    { icon: User, label: 'Incharge', value: sat.inchargeName },
    { icon: Compass, label: 'Azimuth', value: `${sat.azimuth}°` },
    { icon: Compass, label: 'Elevation', value: `${sat.elevation}°` },
    { icon: Compass, label: 'Facing', value: sat.facingPosition },
    { icon: MapPin, label: 'Lat / Long', value: `${sat.latitude}° / ${sat.longitude}°` },
    { icon: MapPin, label: 'Ground Station', value: `${sat.groundStation}, ${sat.state}` },
    { icon: Radio, label: 'Band', value: sat.band },
    { icon: Cpu, label: 'Hardware', value: sat.hardwareSpecs },
    { icon: Wifi, label: 'Pi IP', value: sat.piIpAddress },
  ];

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={() => setShowDetailPanel(false)}>
      <div className="absolute inset-0 bg-background/60 backdrop-blur-sm" />
      <div className="relative w-full max-w-md glass-panel rounded-none border-r-0 border-y-0 animate-slide-in-right overflow-y-auto"
        onClick={e => e.stopPropagation()}>
        <div className="p-6">
          <div className="flex justify-between items-start mb-6">
            <div>
              <h2 className="text-lg font-bold">{sat.name}</h2>
              <div className="flex items-center gap-2 mt-1">
                <div className={`w-2 h-2 rounded-full ${isOnline ? 'status-online' : 'status-offline'}`} />
                <span className="text-xs font-mono text-muted-foreground">{sat.status.toUpperCase()} • {sat.band}</span>
              </div>
            </div>
            <button onClick={() => setShowDetailPanel(false)} className="text-muted-foreground hover:text-foreground">
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Signal Status Bar */}
          <div className="glass-card p-4 mb-6">
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs text-muted-foreground uppercase">Signal Health</span>
              <span className={`text-sm font-mono font-bold ${sat.signalHealth > 70 ? 'text-success' : 'text-destructive'}`}>
                {sat.signalHealth}%
              </span>
            </div>
            <div className="w-full h-2 bg-secondary/50 rounded-full overflow-hidden">
              <div className={`h-full rounded-full transition-all ${sat.signalHealth > 70 ? 'bg-success' : sat.signalHealth > 30 ? 'bg-warning' : 'bg-destructive'}`}
                style={{ width: `${sat.signalHealth}%` }} />
            </div>
          </div>

          {/* Details */}
          <div className="space-y-3">
            {details.map((d, i) => {
              const Icon = d.icon;
              return (
                <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-secondary/20 border border-border/20">
                  <Icon className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                  <div>
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">{d.label}</p>
                    <p className="text-sm font-mono text-foreground">{d.value}</p>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mt-6 p-3 rounded-lg bg-secondary/20 border border-border/20">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Launch Date</p>
            <p className="text-sm font-mono text-foreground">{sat.launchDate}</p>
          </div>
        </div>
      </div>
    </div>
  );
};
