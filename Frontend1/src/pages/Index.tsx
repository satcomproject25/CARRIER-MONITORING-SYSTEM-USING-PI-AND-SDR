import { useAppStore } from '@/store/appStore';
import { LoginPage } from '@/components/auth/LoginPage';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { SatelliteGrid } from '@/components/dashboard/SatelliteGrid';
import { AddSatelliteModal } from '@/components/dashboard/AddSatelliteModal';
import { DetailPanel } from '@/components/dashboard/DetailPanel';
import { SignalMonitor } from '@/components/monitoring/SignalMonitor';

const Index = () => {
  const { auth, monitoringSatellite, showAddModal, showDetailPanel } = useAppStore();

  if (!auth.isAuthenticated) return <LoginPage />;
  if (monitoringSatellite) return <SignalMonitor />;

  return (
    <div className="min-h-screen bg-background">
      <DashboardHeader />
      <SatelliteGrid />
      {showAddModal && <AddSatelliteModal />}
      {showDetailPanel && <DetailPanel />}
    </div>
  );
};

export default Index;
