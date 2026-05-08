import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { Satellite, AuthState, UserProfile } from '@/types/satellite';
import { initialSatellites } from '@/data/satellites';

interface AppStore {
  auth: AuthState;
  satellites: Satellite[];
  selectedSatellite: Satellite | null;
  monitoringSatellite: Satellite | null;
  showAddModal: boolean;
  showDetailPanel: boolean;
  showEditModal: boolean;
  editingSatellite: Satellite | null;

  login: (user: UserProfile) => void;
  logout: () => void;
  addSatellite: (sat: Omit<Satellite, 'id'>) => void;
  updateSatellite: (sat: Satellite) => void;
  deleteSatellite: (id: string) => void;
  selectSatellite: (sat: Satellite | null) => void;
  setMonitoringSatellite: (sat: Satellite | null) => void;
  setShowAddModal: (v: boolean) => void;
  setShowDetailPanel: (v: boolean) => void;
  setShowEditModal: (v: boolean) => void;
  setEditingSatellite: (sat: Satellite | null) => void;
  resetSatellites: () => void;
}

// Load satellites from localStorage or use initial data
const loadSatellites = (): Satellite[] => {
  try {
    const stored = localStorage.getItem('scipy-satellites');
    if (stored) {
      const parsed = JSON.parse(stored);
      // Validate that it's an array
      if (Array.isArray(parsed) && parsed.length > 0) {
        return parsed;
      }
    }
  } catch (error) {
    console.error('Failed to load satellites from localStorage:', error);
  }
  // Return initial satellites if nothing in storage or error
  return initialSatellites;
};

// Save satellites to localStorage
const saveSatellites = (satellites: Satellite[]) => {
  try {
    localStorage.setItem('scipy-satellites', JSON.stringify(satellites));
  } catch (error) {
    console.error('Failed to save satellites to localStorage:', error);
  }
};

export const useAppStore = create<AppStore>()(
  persist(
    (set) => ({
      auth: { isAuthenticated: false, user: null },
      satellites: loadSatellites(),
      selectedSatellite: null,
      monitoringSatellite: null,
      showAddModal: false,
      showDetailPanel: false,
      showEditModal: false,
      editingSatellite: null,

      login: (user) => set({ auth: { isAuthenticated: true, user } }),
      logout: () => set({ auth: { isAuthenticated: false, user: null }, monitoringSatellite: null, selectedSatellite: null }),
      
      addSatellite: (sat) => set((s) => {
        const newSatellites = [...s.satellites, { ...sat, id: String(Date.now()) }];
        saveSatellites(newSatellites);
        return {
          satellites: newSatellites,
          showAddModal: false,
        };
      }),
      
      updateSatellite: (sat) => set((s) => {
        const updatedSatellites = s.satellites.map(existing => existing.id === sat.id ? sat : existing);
        saveSatellites(updatedSatellites);
        return {
          satellites: updatedSatellites,
          selectedSatellite: s.selectedSatellite?.id === sat.id ? sat : s.selectedSatellite,
          monitoringSatellite: s.monitoringSatellite?.id === sat.id ? sat : s.monitoringSatellite,
          showEditModal: false,
          editingSatellite: null,
        };
      }),
      
      deleteSatellite: (id) => set((s) => {
        const filteredSatellites = s.satellites.filter(sat => sat.id !== id);
        saveSatellites(filteredSatellites);
        return {
          satellites: filteredSatellites,
          selectedSatellite: s.selectedSatellite?.id === id ? null : s.selectedSatellite,
          monitoringSatellite: s.monitoringSatellite?.id === id ? null : s.monitoringSatellite,
        };
      }),
      
      selectSatellite: (sat) => set({ selectedSatellite: sat, showDetailPanel: !!sat }),
      setMonitoringSatellite: (sat) => set({ monitoringSatellite: sat }),
      setShowAddModal: (v) => set({ showAddModal: v }),
      setShowDetailPanel: (v) => set({ showDetailPanel: v, selectedSatellite: v ? undefined : null }),
      setShowEditModal: (v) => set({ showEditModal: v }),
      setEditingSatellite: (sat) => set({ editingSatellite: sat, showEditModal: !!sat }),
      
      resetSatellites: () => set(() => {
        saveSatellites(initialSatellites);
        return { satellites: initialSatellites };
      }),
    }),
    {
      name: 'scipy-cms-storage',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({ 
        auth: state.auth,
        satellites: state.satellites,
      }),
    }
  )
);
