import { useState } from 'react';
import { X, Satellite } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAppStore } from '@/store/appStore';

export const AddSatelliteModal = () => {
  const { setShowAddModal, addSatellite } = useAppStore();
  const [form, setForm] = useState({
    name: '', band: 'C-Band', elevation: '', azimuth: '', latitude: '', longitude: '',
    state: '', country: 'India', groundStation: '', piIpAddress: '',
    inchargeName: '', facingPosition: '', hardwareSpecs: '',
  });

  const update = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    addSatellite({
      ...form, elevation: +form.elevation, azimuth: +form.azimuth,
      latitude: +form.latitude, longitude: +form.longitude,
      status: 'offline', signalHealth: 0, cnRatio: 0, ebNo: 0, launchDate: new Date().toISOString().split('T')[0],
    });
  };

  const fields: { key: string; label: string; placeholder: string; type?: string }[] = [
    { key: 'name', label: 'Satellite Name', placeholder: 'GSAT-XX' },
    { key: 'band', label: 'Band Type', placeholder: 'C-Band / Ku-Band' },
    { key: 'elevation', label: 'Elevation (°)', placeholder: '45.0', type: 'number' },
    { key: 'azimuth', label: 'Azimuth (°)', placeholder: '183.0', type: 'number' },
    { key: 'latitude', label: 'Latitude', placeholder: '0.05', type: 'number' },
    { key: 'longitude', label: 'Longitude', placeholder: '83.0', type: 'number' },
    { key: 'state', label: 'State', placeholder: 'Karnataka' },
    { key: 'country', label: 'Country', placeholder: 'India' },
    { key: 'groundStation', label: 'Ground Station', placeholder: 'Hassan' },
    { key: 'piIpAddress', label: 'Raspberry Pi IP', placeholder: '192.168.1.XXX' },
    { key: 'inchargeName', label: 'Incharge Name', placeholder: 'Dr. Name' },
    { key: 'facingPosition', label: 'Facing Position', placeholder: 'South-East' },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm" onClick={() => setShowAddModal(false)}>
      <div className="glass-panel w-full max-w-2xl p-6 m-4 max-h-[90vh] overflow-y-auto animate-scale-in" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <div className="flex items-center gap-3">
            <Satellite className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-bold">Add Satellite</h2>
          </div>
          <button onClick={() => setShowAddModal(false)} className="text-muted-foreground hover:text-foreground"><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {fields.map(f => (
              <div key={f.key} className="space-y-1.5">
                <Label className="text-muted-foreground text-[10px] uppercase tracking-wider">{f.label}</Label>
                <Input value={(form as any)[f.key]} onChange={e => update(f.key, e.target.value)}
                  type={f.type || 'text'} placeholder={f.placeholder}
                  className="bg-secondary/50 border-border/50 h-9 text-sm font-mono" />
              </div>
            ))}
            <div className="sm:col-span-2 space-y-1.5">
              <Label className="text-muted-foreground text-[10px] uppercase tracking-wider">Hardware Specs</Label>
              <Input value={form.hardwareSpecs} onChange={e => update('hardwareSpecs', e.target.value)}
                placeholder="Payload details, power specs..."
                className="bg-secondary/50 border-border/50 h-9 text-sm font-mono" />
            </div>
          </div>
          <div className="flex justify-end gap-3 mt-6">
            <Button type="button" variant="outline" onClick={() => setShowAddModal(false)}>Cancel</Button>
            <Button type="submit" disabled={!form.name || !form.piIpAddress} className="glow-primary">
              Add to Fleet
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};
