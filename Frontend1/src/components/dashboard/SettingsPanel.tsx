import { useState } from 'react';
import { Download, Upload, RotateCcw, Database, AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useAppStore } from '@/store/appStore';
import { toast } from 'sonner';
import { Satellite } from '@/types/satellite';

interface Props {
  open: boolean;
  onClose: () => void;
}

export const SettingsPanel = ({ open, onClose }: Props) => {
  const { satellites, resetSatellites } = useAppStore();
  const [showResetConfirm, setShowResetConfirm] = useState(false);

  const handleExport = () => {
    try {
      const dataStr = JSON.stringify(satellites, null, 2);
      const dataBlob = new Blob([dataStr], { type: 'application/json' });
      const url = URL.createObjectURL(dataBlob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `scipy-satellites-${new Date().toISOString().split('T')[0]}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      toast.success('Satellite configuration exported successfully');
    } catch (error) {
      toast.error('Failed to export configuration');
      console.error('Export error:', error);
    }
  };

  const handleImport = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;

      try {
        const text = await file.text();
        const imported = JSON.parse(text) as Satellite[];

        // Validate structure
        if (!Array.isArray(imported)) {
          throw new Error('Invalid format: expected array');
        }

        // Basic validation of satellite objects
        for (const sat of imported) {
          if (!sat.id || !sat.name || !sat.piIpAddress) {
            throw new Error('Invalid satellite data structure');
          }
        }

        // Save to localStorage
        localStorage.setItem('scipy-satellites', JSON.stringify(imported));
        
        // Reload page to apply changes
        toast.success('Configuration imported successfully. Reloading...');
        setTimeout(() => window.location.reload(), 1000);
      } catch (error) {
        toast.error('Failed to import configuration: ' + (error as Error).message);
        console.error('Import error:', error);
      }
    };
    input.click();
  };

  const handleReset = () => {
    resetSatellites();
    setShowResetConfirm(false);
    toast.success('Satellite configuration reset to defaults');
    onClose();
  };

  const handleClearStorage = () => {
    try {
      localStorage.removeItem('scipy-satellites');
      localStorage.removeItem('scipy-cms-storage');
      toast.success('All data cleared. Reloading...');
      setTimeout(() => window.location.reload(), 1000);
    } catch (error) {
      toast.error('Failed to clear storage');
      console.error('Clear storage error:', error);
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onClose}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Database className="w-5 h-5" />
              Data Management
            </DialogTitle>
            <DialogDescription>
              Export, import, or reset your satellite configuration
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 mt-4">
            {/* Export */}
            <div className="p-4 rounded-lg border border-border/50 bg-secondary/20">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <h4 className="font-semibold text-sm mb-1">Export Configuration</h4>
                  <p className="text-xs text-muted-foreground">
                    Download all satellite data as JSON file
                  </p>
                </div>
                <Button size="sm" variant="outline" onClick={handleExport}>
                  <Download className="w-4 h-4 mr-1.5" />
                  Export
                </Button>
              </div>
            </div>

            {/* Import */}
            <div className="p-4 rounded-lg border border-border/50 bg-secondary/20">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <h4 className="font-semibold text-sm mb-1">Import Configuration</h4>
                  <p className="text-xs text-muted-foreground">
                    Load satellite data from JSON file
                  </p>
                </div>
                <Button size="sm" variant="outline" onClick={handleImport}>
                  <Upload className="w-4 h-4 mr-1.5" />
                  Import
                </Button>
              </div>
            </div>

            {/* Reset */}
            <div className="p-4 rounded-lg border border-destructive/30 bg-destructive/5">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <h4 className="font-semibold text-sm mb-1 text-destructive">Reset to Defaults</h4>
                  <p className="text-xs text-muted-foreground">
                    Restore original satellite configuration
                  </p>
                </div>
                <Button 
                  size="sm" 
                  variant="destructive" 
                  onClick={() => setShowResetConfirm(true)}
                >
                  <RotateCcw className="w-4 h-4 mr-1.5" />
                  Reset
                </Button>
              </div>
            </div>

            {/* Storage Info */}
            <div className="p-3 rounded-lg bg-muted/50 border border-border/30">
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Satellites stored:</span>
                <span className="font-mono font-semibold">{satellites.length}</span>
              </div>
              <div className="flex items-center justify-between text-xs mt-1">
                <span className="text-muted-foreground">Storage location:</span>
                <span className="font-mono text-[10px]">localStorage</span>
              </div>
              <Button 
                size="sm" 
                variant="ghost" 
                className="w-full mt-2 h-7 text-xs"
                onClick={handleClearStorage}
              >
                Clear All Storage
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Reset Confirmation */}
      <AlertDialog open={showResetConfirm} onOpenChange={setShowResetConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-destructive" />
              Reset Configuration?
            </AlertDialogTitle>
            <AlertDialogDescription>
              This will restore the default satellite configuration and discard all your changes.
              Any custom satellites or modifications will be lost.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleReset} className="bg-destructive hover:bg-destructive/90">
              Reset to Defaults
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
};
