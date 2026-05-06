import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line, Legend } from 'recharts';
import { SignalData } from '@/types/satellite';

interface Props { data: SignalData[]; }

export const SpectrumChart = ({ data }: Props) => {
  return (
    <div className="glass-card p-5 h-full">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-bold text-foreground">Spectrum Analyzer</h3>
          <p className="text-[10px] font-mono text-muted-foreground">REAL-TIME SIGNAL POWER vs NOISE FLOOR</p>
        </div>
        <div className="flex items-center gap-3 text-[10px] font-mono">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-primary" /> Power</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-destructive/60" /> Noise</span>
        </div>
      </div>

      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
            <defs>
              <linearGradient id="powerGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="hsl(199, 89%, 48%)" stopOpacity={0.4} />
                <stop offset="100%" stopColor="hsl(199, 89%, 48%)" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="noiseGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="hsl(0, 72%, 51%)" stopOpacity={0.2} />
                <stop offset="100%" stopColor="hsl(0, 72%, 51%)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(222, 30%, 18%)" />
            <XAxis dataKey="time" tick={{ fontSize: 9, fill: 'hsl(215, 20%, 55%)' }} stroke="hsl(222, 30%, 18%)" />
            <YAxis tick={{ fontSize: 9, fill: 'hsl(215, 20%, 55%)' }} stroke="hsl(222, 30%, 18%)" domain={[-80, -10]} />
            <Tooltip contentStyle={{ background: 'hsl(222, 41%, 10%)', border: '1px solid hsl(222, 30%, 18%)', borderRadius: 8, fontSize: 11, fontFamily: 'JetBrains Mono' }}
              labelStyle={{ color: 'hsl(215, 20%, 55%)' }} />
            <Area type="monotone" dataKey="power" stroke="hsl(199, 89%, 48%)" fill="url(#powerGrad)" strokeWidth={2} dot={false} />
            <Area type="monotone" dataKey="noise" stroke="hsl(0, 72%, 51%)" fill="url(#noiseGrad)" strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Secondary chart: C/N and Eb/No */}
      <div className="mt-6">
        <h3 className="text-xs font-bold text-foreground mb-3">Link Budget Metrics</h3>
        <div className="h-40">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(222, 30%, 18%)" />
              <XAxis dataKey="time" tick={{ fontSize: 9, fill: 'hsl(215, 20%, 55%)' }} stroke="hsl(222, 30%, 18%)" />
              <YAxis tick={{ fontSize: 9, fill: 'hsl(215, 20%, 55%)' }} stroke="hsl(222, 30%, 18%)" />
              <Tooltip contentStyle={{ background: 'hsl(222, 41%, 10%)', border: '1px solid hsl(222, 30%, 18%)', borderRadius: 8, fontSize: 11, fontFamily: 'JetBrains Mono' }} />
              <Line type="monotone" dataKey="cnRatio" name="C/N (dB)" stroke="hsl(142, 71%, 45%)" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="ebNo" name="Eb/No (dB)" stroke="hsl(38, 92%, 50%)" strokeWidth={2} dot={false} />
              <Legend wrapperStyle={{ fontSize: 10, fontFamily: 'JetBrains Mono' }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};
