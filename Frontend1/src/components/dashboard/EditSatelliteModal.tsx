import { useState, useEffect } from 'react';
import { Satellite } from '@/types/satellite';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Save, X, Trash2, AlertTriangle, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { getSuggestedStatus } from '@/lib/healthCheck';
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

interface Props {
  satellite: Satellite | null;
  open: boolean;
  onClose: () => void;
  onSave: (satellite: Satellite) => void;
  onDelete?: (id: string) => void;
}

export const EditSatelliteModal = ({ satellite, open, onClose, onSave, onDelete }: Props) => {
  const [formData, setFormData] = useState<Satellite | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [detectingStatus, setDetectingStatus] = useState(false);

  useEffect(() => {
    if (satellite) {
      setFormData({ ...satellite });
    }
  }, [satellite]);

  if (!formData) return null;

  const handleChange = (field: keyof Satellite, value: string | number) => {
    setFormData(prev => prev ? { ...prev, [field]: value } : null);
  };

  const handleSave = () => {
    if (!formData) return;

    // Validation
    if (!formData.name.trim()) {
      toast.error('Satellite name is required');
      return;
    }
    if (!formData.piIpAddress.trim()) {
      toast.error('Pi IP Address is required');
      return;
    }

    // Basic IP validation
    const ipPattern = /^(\d{1,3}\.){3}\d{1,3}$/;
    if (!ipPattern.test(formData.piIpAddress) && formData.piIpAddress !== '—') {
      toast.error('Invalid IP address format');
      return;
    }

    onSave(formData);
    toast.success('Satellite details updated successfully');
    onClose();
  };

  const handleDelete = () => {
    if (!formData || !onDelete) return;
    onDelete(formData.id);
    setShowDeleteConfirm(false);
    toast.success('Satellite deleted successfully');
    onClose();
  };

  const handleAutoDetectStatus = async () => {
    if (!formData) return;
    
    setDetectingStatus(true);
    toast.info('Checking Pi connection...');
    
    try {
      const suggestedStatus = await getSuggestedStatus(formData.piIpAddress);
      setFormData(prev => prev ? { ...prev, status: suggestedStatus } : null);
      
      if (suggestedStatus === 'online') {
        toast.success('Pi is reachable! Status set to Online');
      } else {
        toast.warning('Pi is not reachable. Status set to Offline');
      }
    } catch (error) {
      toast.error('Failed to detect status');
    } finally {
      setDetectingStatus(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-xl font-bold">Edit Satellite Details</DialogTitle>
        </DialogHeader>

        <Tabs defaultValue="basic" className="w-full">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="basic">Basic Info</TabsTrigger>
            <TabsTrigger value="location">Location</TabsTrigger>
            <TabsTrigger value="technical">Technical</TabsTrigger>
          </TabsList>

          {/* Basic Info Tab */}
          <TabsContent value="basic" className="space-y-4 mt-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="name">Satellite Name *</Label>
                <Input
                  id="name"
                  value={formData.name}
                  onChange={(e) => handleChange('name', e.target.value)}
                  placeholder="e.g., GSAT-30"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="band">Frequency Band *</Label>
                <Input
                  id="band"
                  value={formData.band}
                  onChange={(e) => handleChange('band', e.target.value)}
                  placeholder="e.g., C-Band"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="status">Status</Label>
                <div className="flex gap-2">
                  <Select
                    value={formData.status}
                    onValueChange={(value) => handleChange('status', value)}
                  >
                    <SelectTrigger className="flex-1">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="online">Online</SelectItem>
                      <SelectItem value="offline">Offline</SelectItem>
                    </SelectContent>
                  </Select>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleAutoDetectStatus}
                    disabled={detectingStatus || !formData.piIpAddress}
                    title="Auto-detect status by pinging Pi"
                  >
                    <RefreshCw className={`w-4 h-4 ${detectingStatus ? 'animate-spin' : ''}`} />
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Click refresh to auto-detect based on Pi connectivity
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="piIpAddress">Raspberry Pi IP Address *</Label>
                <Input
                  id="piIpAddress"
                  value={formData.piIpAddress}
                  onChange={(e) => handleChange('piIpAddress', e.target.value)}
                  placeholder="e.g., 192.168.1.100"
                />
                <p className="text-xs text-muted-foreground">
                  Use "—" for simulation mode (no real hardware)
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="inchargeName">Person In-Charge</Label>
                <Input
                  id="inchargeName"
                  value={formData.inchargeName}
                  onChange={(e) => handleChange('inchargeName', e.target.value)}
                  placeholder="e.g., Dr. Sharma"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="launchDate">Launch Date</Label>
                <Input
                  id="launchDate"
                  value={formData.launchDate}
                  onChange={(e) => handleChange('launchDate', e.target.value)}
                  placeholder="e.g., 2020-01-17"
                />
              </div>
            </div>
          </TabsContent>

          {/* Location Tab */}
          <TabsContent value="location" className="space-y-4 mt-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="groundStation">Ground Station</Label>
                <Input
                  id="groundStation"
                  value={formData.groundStation}
                  onChange={(e) => handleChange('groundStation', e.target.value)}
                  placeholder="e.g., Hassan"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="state">State</Label>
                <Input
                  id="state"
                  value={formData.state}
                  onChange={(e) => handleChange('state', e.target.value)}
                  placeholder="e.g., Karnataka"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="country">Country</Label>
                <Input
                  id="country"
                  value={formData.country}
                  onChange={(e) => handleChange('country', e.target.value)}
                  placeholder="e.g., India"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="facingPosition">Facing Position</Label>
                <Input
                  id="facingPosition"
                  value={formData.facingPosition}
                  onChange={(e) => handleChange('facingPosition', e.target.value)}
                  placeholder="e.g., 83°E"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="latitude">Latitude (°)</Label>
                <Input
                  id="latitude"
                  type="number"
                  step="0.0001"
                  value={formData.latitude}
                  onChange={(e) => handleChange('latitude', parseFloat(e.target.value) || 0)}
                  placeholder="e.g., 13.0827"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="longitude">Longitude (°)</Label>
                <Input
                  id="longitude"
                  type="number"
                  step="0.0001"
                  value={formData.longitude}
                  onChange={(e) => handleChange('longitude', parseFloat(e.target.value) || 0)}
                  placeholder="e.g., 77.5877"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="elevation">Elevation (°)</Label>
                <Input
                  id="elevation"
                  type="number"
                  step="0.1"
                  value={formData.elevation}
                  onChange={(e) => handleChange('elevation', parseFloat(e.target.value) || 0)}
                  placeholder="e.g., 45.2"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="azimuth">Azimuth (°)</Label>
                <Input
                  id="azimuth"
                  type="number"
                  step="0.1"
                  value={formData.azimuth}
                  onChange={(e) => handleChange('azimuth', parseFloat(e.target.value) || 0)}
                  placeholder="e.g., 180.5"
                />
              </div>
            </div>
          </TabsContent>

          {/* Technical Tab */}
          <TabsContent value="technical" className="space-y-4 mt-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="hardwareSpecs">Hardware Specifications</Label>
                <Input
                  id="hardwareSpecs"
                  value={formData.hardwareSpecs}
                  onChange={(e) => handleChange('hardwareSpecs', e.target.value)}
                  placeholder="e.g., HackRF One + LNA"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="signalHealth">Signal Health (%)</Label>
                <Input
                  id="signalHealth"
                  type="number"
                  min="0"
                  max="100"
                  value={formData.signalHealth}
                  onChange={(e) => handleChange('signalHealth', parseInt(e.target.value) || 0)}
                  placeholder="e.g., 85"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="cnRatio">C/N Ratio (dB)</Label>
                <Input
                  id="cnRatio"
                  type="number"
                  step="0.1"
                  value={formData.cnRatio}
                  onChange={(e) => handleChange('cnRatio', parseFloat(e.target.value) || 0)}
                  placeholder="e.g., 12.5"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="ebNo">Eb/No (dB)</Label>
                <Input
                  id="ebNo"
                  type="number"
                  step="0.1"
                  value={formData.ebNo}
                  onChange={(e) => handleChange('ebNo', parseFloat(e.target.value) || 0)}
                  placeholder="e.g., 8.2"
                />
              </div>
            </div>

            <div className="bg-muted/50 p-4 rounded-lg border border-border/50">
              <h4 className="text-sm font-semibold mb-2">Connection Information</h4>
              <div className="space-y-1 text-xs text-muted-foreground">
                <p>• API Endpoint: http://{formData.piIpAddress}:8780</p>
                <p>• Config Manager: http://{formData.piIpAddress}:5580</p>
                <p>• Status: {formData.status === 'online' ? '🟢 Ready for monitoring' : '🔴 Offline'}</p>
              </div>
            </div>
          </TabsContent>
        </Tabs>

        {/* Action Buttons */}
        <div className="flex justify-between items-center mt-6 pt-4 border-t">
          {onDelete && (
            <Button 
              variant="destructive" 
              onClick={() => setShowDeleteConfirm(true)}
              className="mr-auto"
            >
              <Trash2 className="w-4 h-4 mr-2" />
              Delete Satellite
            </Button>
          )}
          <div className="flex gap-2 ml-auto">
            <Button variant="outline" onClick={onClose}>
              <X className="w-4 h-4 mr-2" />
              Cancel
            </Button>
            <Button onClick={handleSave}>
              <Save className="w-4 h-4 mr-2" />
              Save Changes
            </Button>
          </div>
        </div>
      </DialogContent>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-destructive" />
              Delete Satellite?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete <strong>{formData.name}</strong>?
              This action cannot be undone. All configuration data for this satellite will be permanently removed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive hover:bg-destructive/90">
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Dialog>
  );
};
