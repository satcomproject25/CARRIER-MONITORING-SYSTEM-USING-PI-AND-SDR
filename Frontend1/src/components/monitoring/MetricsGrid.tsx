import { Activity, Gauge, Radio, AlertTriangle, Wifi } from 'lucide-react';
import { SignalData } from '@/types/satellite';

interface Props { data?: SignalData; anomaly: boolean; connected: boolean; }

export const MetricsGrid = ({ data, anomaly, connected }: Props) => {
  const metrics = [
    {
      icon: Activity,
      label: 'Signal Health',
      value: data ? `${data.signalHealth.toFixed(1)}%` : '—',
      color: data && data.signalHealth > 70 ? 'text-success' : data && data.signalHealth > 40 ? 'text-warning' : 'text-destructive',
      bg: data && data.signalHealth > 70 ? 'bg-success/10 border-success/20' : data && data.signalHealth > 40 ? 'bg-warning/10 border-warning/20' : 'bg-destructive/10 border-destructive/20',
    },
    {
      icon: Gauge,
      label: 'C/N Ratio',
      value: data ? `${data.cnRatio.toFixed(1)} dB` : '—',
      color: 'text-primary',
      bg: 'bg-primary/10 border-primary/20',
    },
    {
      icon: Radio,
      label: 'Eb/No',
      value: data ? `${data.ebNo.toFixed(1)} dB` : '—',
      color: 'text-primary',
      bg: 'bg-primary/10 border-primary/20',
    },
    {
      icon: anomaly ? AlertTriangle : Wifi,
      label: 'Interference',
      value: anomaly ? 'DETECTED' : connected ? 'CLEAR' : 'SCANNING...',
      color: anomaly ? 'text-destructive' : 'text-success',
      bg: anomaly ? 'bg-destructive/10 border-destructive/20 animate-pulse' : 'bg-success/10 border-success/20',
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {metrics.map((m, i) => {
        const Icon = m.icon;
        return (
          <div key={i} className={`glass-card p-4 border ${m.bg} animate-fade-in`} style={{ animationDelay: `${i * 80}ms` }}>
            <div className="flex items-center gap-2 mb-2">
              <Icon className={`w-4 h-4 ${m.color}`} />
              <span className="text-[10px] text-muted-foreground uppercase tracking-wider">{m.label}</span>
            </div>
            <p className={`text-2xl font-mono font-bold ${m.color}`}>{m.value}</p>
          </div>
        );
      })}
    </div>
  );
};
