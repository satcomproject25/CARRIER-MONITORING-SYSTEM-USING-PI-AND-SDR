import { LogOut, Radio, Bell } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAppStore } from '@/store/appStore';
import isroLogo from '../../../image/isro_dark.png';

export const DashboardHeader = () => {
  const { auth, logout, satellites } = useAppStore();
  const onlineCount = satellites.filter(s => s.status === 'online').length;

  return (
    <header className="glass-panel rounded-none border-x-0 border-t-0 sticky top-0 z-40">
      <div className="flex items-center justify-between px-6 py-3">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-3">
            <img
              src={isroLogo}
              alt="ISRO"
              className="h-10 w-auto object-contain"
            />
            <div>
              <h1 className="text-sm font-bold text-gradient leading-tight">ISRO CMS</h1>
              <p className="text-[10px] text-muted-foreground font-mono">CARRIER MONITORING</p>
            </div>
          </div>
          <div className="hidden md:flex items-center gap-2 ml-4 px-3 py-1 rounded-full bg-secondary/50 border border-border/30">
            <Radio className="w-3 h-3 text-success animate-pulse" />
            <span className="text-xs font-mono text-muted-foreground">
              <span className="text-success">{onlineCount}</span>/{satellites.length} ACTIVE
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button className="relative p-2 rounded-lg hover:bg-secondary/50 transition-colors">
            <Bell className="w-4 h-4 text-muted-foreground" />
            <span className="absolute top-1 right-1 w-2 h-2 bg-destructive rounded-full" />
          </button>
          <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-secondary/30 border border-border/20">
            <div className="w-6 h-6 rounded-full bg-primary/20 flex items-center justify-center">
              <span className="text-[10px] font-bold text-primary">{auth.user?.name?.[0]}</span>
            </div>
            <span className="text-xs text-muted-foreground">{auth.user?.name}</span>
          </div>
          <Button variant="ghost" size="sm" onClick={logout} className="text-muted-foreground hover:text-destructive">
            <LogOut className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </header>
  );
};
