import { create } from 'zustand';
import { Satellite, AuthState, UserProfile } from '@/types/satellite';
import { initialSatellites } from '@/data/satellites';

interface AppStore {
  auth: AuthState;
  satellites: Satellite[];
  selectedSatellite: Satellite | null;
  monitoringSatellite: Satellite | null;
  showAddModal: boolean;
  showDetailPanel: boolean;

  login: (user: UserProfile) => void;
  logout: () => void;
  addSatellite: (sat: Omit<Satellite, 'id'>) => void;
  selectSatellite: (sat: Satellite | null) => void;
  setMonitoringSatellite: (sat: Satellite | null) => void;
  setShowAddModal: (v: boolean) => void;
  setShowDetailPanel: (v: boolean) => void;
}

export const useAppStore = create<AppStore>((set) => ({
  auth: { isAuthenticated: false, user: null },
  satellites: initialSatellites,
  selectedSatellite: null,
  monitoringSatellite: null,
  showAddModal: false,
  showDetailPanel: false,

  login: (user) => set({ auth: { isAuthenticated: true, user } }),
  logout: () => set({ auth: { isAuthenticated: false, user: null }, monitoringSatellite: null, selectedSatellite: null }),
  addSatellite: (sat) => set((s) => ({
    satellites: [...s.satellites, { ...sat, id: String(Date.now()) }],
    showAddModal: false,
  })),
  selectSatellite: (sat) => set({ selectedSatellite: sat, showDetailPanel: !!sat }),
  setMonitoringSatellite: (sat) => set({ monitoringSatellite: sat }),
  setShowAddModal: (v) => set({ showAddModal: v }),
  setShowDetailPanel: (v) => set({ showDetailPanel: v, selectedSatellite: v ? undefined : null }),
}));
