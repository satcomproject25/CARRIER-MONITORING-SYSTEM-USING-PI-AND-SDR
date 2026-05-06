import { Plus, Search } from 'lucide-react';
import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { useAppStore } from '@/store/appStore';
import { SatelliteCard } from './SatelliteCard';

export const SatelliteGrid = () => {
  const { satellites, setShowAddModal } = useAppStore();
  const [search, setSearch] = useState('');

  const filtered = satellites.filter(s =>
    s.name.toLowerCase().includes(search.toLowerCase()) ||
    s.band.toLowerCase().includes(search.toLowerCase()) ||
    s.groundStation.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-6">
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-bold text-foreground">Satellite Fleet</h2>
          <p className="text-xs text-muted-foreground font-mono">{satellites.length} satellites tracked</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <Input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search fleet..."
              className="pl-9 h-9 w-48 bg-secondary/30 border-border/30 text-sm" />
          </div>
        </div>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {filtered.map((sat, i) => (
          <SatelliteCard key={sat.id} satellite={sat} index={i} />
        ))}
      </div>

      {/* FAB */}
      <button onClick={() => setShowAddModal(true)}
        className="fixed bottom-8 right-8 w-14 h-14 rounded-2xl bg-primary flex items-center justify-center glow-primary hover:scale-110 active:scale-95 transition-transform shadow-2xl z-30">
        <Plus className="w-6 h-6 text-primary-foreground" />
      </button>
    </div>
  );
};
