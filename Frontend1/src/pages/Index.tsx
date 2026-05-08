import { useAppStore } from '@/store/appStore';
import { LoginPage } from '@/components/auth/LoginPage';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { SatelliteGrid } from '@/components/dashboard/SatelliteGrid';
import { AddSatelliteModal } from '@/components/dashboard/AddSatelliteModal';
import { EditSatelliteModal } from '@/components/dashboard/EditSatelliteModal';
import { DetailPanel } from '@/components/dashboard/DetailPanel';
import { SignalMonitor } from '@/components/monitoring/SignalMonitor';
import { useAutoStartBackend } from '@/hooks/useAutoStartBackend';

const Index = () => {
  const { 
    auth, 
    satellites,
    monitoringSatellite, 
    showAddModal, 
    showDetailPanel, 
    showEditModal, 
    editingSatellite,
    updateSatellite,
    deleteSatellite,
    setShowEditModal 
  } = useAppStore();

  // Auto-start backend for online satellites
  useAutoStartBackend(satellites);

  if (!auth.isAuthenticated) return <LoginPage />;
  if (monitoringSatellite) return <SignalMonitor />;

  return (
    <div className="min-h-screen bg-background">
      <DashboardHeader />
      <SatelliteGrid />
      {showAddModal && <AddSatelliteModal />}
      {showDetailPanel && <DetailPanel />}
      {showEditModal && (
        <EditSatelliteModal
          satellite={editingSatellite}
          open={showEditModal}
          onClose={() => setShowEditModal(false)}
          onSave={updateSatellite}
          onDelete={deleteSatellite}
        />
      )}
    </div>
  );
};

export default Index;
