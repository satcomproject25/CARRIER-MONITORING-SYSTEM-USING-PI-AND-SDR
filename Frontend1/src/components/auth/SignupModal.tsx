import { useState, useRef, useCallback } from 'react';
import { X, ChevronRight, ChevronLeft, Camera, Upload, CheckCircle2, User, Building, ScanFace } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAppStore } from '@/store/appStore';
import { SignupStep } from '@/types/satellite';

interface Props { onClose: () => void; }

export const SignupModal = ({ onClose }: Props) => {
  const [step, setStep] = useState<SignupStep>(1);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [mobile, setMobile] = useState('');
  const [orgId, setOrgId] = useState('');
  const [idCardUploaded, setIdCardUploaded] = useState(false);
  const [capturedImage, setCapturedImage] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [verified, setVerified] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const login = useAppStore((s) => s.login);

  const startCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: 320, height: 240 } });
      streamRef.current = stream;
      if (videoRef.current) videoRef.current.srcObject = stream;
    } catch { /* camera not available */ }
  }, []);

  const capturePhoto = () => {
    if (!videoRef.current) return;
    const canvas = document.createElement('canvas');
    canvas.width = 320; canvas.height = 240;
    canvas.getContext('2d')?.drawImage(videoRef.current, 0, 0);
    setCapturedImage(canvas.toDataURL('image/jpeg'));
    streamRef.current?.getTracks().forEach(t => t.stop());
  };

  const handleVerification = () => {
    setVerifying(true);
    setTimeout(() => {
      setVerifying(false);
      setVerified(true);
      setTimeout(() => {
        login({ name, email, mobile, orgId, verified: true });
        onClose();
      }, 1500);
    }, 2500);
  };

  const steps = [
    { icon: User, label: 'Basic Info' },
    { icon: Building, label: 'Professional ID' },
    { icon: ScanFace, label: 'Bio-Verify' },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm" onClick={onClose}>
      <div className="glass-panel w-full max-w-lg p-8 animate-scale-in m-4" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-bold text-gradient">Personnel Registration</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors"><X className="w-5 h-5" /></button>
        </div>

        {/* Steps indicator */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {steps.map((s, i) => {
            const Icon = s.icon;
            const stepNum = (i + 1) as SignupStep;
            const active = step === stepNum;
            const done = step > stepNum;
            return (
              <div key={i} className="flex items-center gap-2">
                <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                  active ? 'bg-primary/20 text-primary border border-primary/30' :
                  done ? 'bg-success/20 text-success border border-success/30' :
                  'bg-secondary/50 text-muted-foreground border border-border/30'
                }`}>
                  {done ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Icon className="w-3.5 h-3.5" />}
                  <span className="hidden sm:inline">{s.label}</span>
                </div>
                {i < 2 && <ChevronRight className="w-3 h-3 text-muted-foreground/40" />}
              </div>
            );
          })}
        </div>

        {/* Step 1: Basic Info */}
        {step === 1 && (
          <div className="space-y-4 animate-fade-in">
            <div className="space-y-2">
              <Label className="text-muted-foreground text-xs uppercase tracking-wider">Full Name</Label>
              <Input value={name} onChange={e => setName(e.target.value)} placeholder="Dr. Ananya Sharma" className="bg-secondary/50 border-border/50 h-11" />
            </div>
            <div className="space-y-2">
              <Label className="text-muted-foreground text-xs uppercase tracking-wider">Organization Email</Label>
              <Input value={email} onChange={e => setEmail(e.target.value)} placeholder="name@isro.gov.in" className="bg-secondary/50 border-border/50 h-11" />
            </div>
            <div className="space-y-2">
              <Label className="text-muted-foreground text-xs uppercase tracking-wider">Mobile Number</Label>
              <Input value={mobile} onChange={e => setMobile(e.target.value)} placeholder="+91-9876543210" className="bg-secondary/50 border-border/50 h-11" />
            </div>
          </div>
        )}

        {/* Step 2: Professional ID */}
        {step === 2 && (
          <div className="space-y-4 animate-fade-in">
            <div className="space-y-2">
              <Label className="text-muted-foreground text-xs uppercase tracking-wider">Organization ID Number</Label>
              <Input value={orgId} onChange={e => setOrgId(e.target.value)} placeholder="ISRO-2024-XXXX" className="bg-secondary/50 border-border/50 h-11 font-mono" />
            </div>
            <div className="space-y-2">
              <Label className="text-muted-foreground text-xs uppercase tracking-wider">ID Card Image</Label>
              <div className={`border-2 border-dashed rounded-lg p-8 text-center transition-all cursor-pointer ${
                idCardUploaded ? 'border-success/50 bg-success/5' : 'border-border/50 hover:border-primary/30 bg-secondary/20'
              }`} onClick={() => setIdCardUploaded(true)}>
                {idCardUploaded ? (
                  <div className="flex flex-col items-center gap-2">
                    <CheckCircle2 className="w-8 h-8 text-success" />
                    <span className="text-sm text-success">ID Card Uploaded</span>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-2">
                    <Upload className="w-8 h-8 text-muted-foreground" />
                    <span className="text-sm text-muted-foreground">Click to upload Organization ID Card</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Step 3: Bio-verification */}
        {step === 3 && (
          <div className="space-y-4 animate-fade-in">
            <div className="flex flex-col items-center">
              {verified ? (
                <div className="flex flex-col items-center gap-4 py-8">
                  <div className="w-20 h-20 rounded-full bg-success/20 border-2 border-success flex items-center justify-center glow-success">
                    <CheckCircle2 className="w-10 h-10 text-success" />
                  </div>
                  <p className="text-success font-semibold text-lg">Verification Complete</p>
                  <p className="text-muted-foreground text-sm">Redirecting to Mission Control...</p>
                </div>
              ) : capturedImage ? (
                <div className="flex flex-col items-center gap-4">
                  <img src={capturedImage} alt="Captured" className="w-64 h-48 rounded-lg border border-border/50 object-cover" />
                  {verifying ? (
                    <div className="flex items-center gap-3">
                      <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                      <span className="text-primary font-mono text-sm">Running Bio-Verification...</span>
                    </div>
                  ) : (
                    <Button onClick={handleVerification} className="glow-primary">
                      <ScanFace className="w-4 h-4 mr-2" /> Verify Identity
                    </Button>
                  )}
                </div>
              ) : (
                <div className="flex flex-col items-center gap-4">
                  <div className="relative w-64 h-48 rounded-lg overflow-hidden border border-border/50 bg-secondary/30">
                    <video ref={videoRef} autoPlay playsInline muted className="w-full h-full object-cover" />
                    <div className="absolute inset-0 border-2 border-primary/30 rounded-lg" />
                    {/* Scan overlay */}
                    <div className="absolute top-2 left-2 w-6 h-6 border-l-2 border-t-2 border-primary/60" />
                    <div className="absolute top-2 right-2 w-6 h-6 border-r-2 border-t-2 border-primary/60" />
                    <div className="absolute bottom-2 left-2 w-6 h-6 border-l-2 border-b-2 border-primary/60" />
                    <div className="absolute bottom-2 right-2 w-6 h-6 border-r-2 border-b-2 border-primary/60" />
                  </div>
                  <div className="flex gap-3">
                    <Button variant="outline" onClick={startCamera}>
                      <Camera className="w-4 h-4 mr-2" /> Start Camera
                    </Button>
                    <Button onClick={capturePhoto} className="glow-primary">
                      Capture Image
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Navigation */}
        {!verified && (
          <div className="flex justify-between mt-8">
            <Button variant="outline" onClick={() => step > 1 ? setStep((step - 1) as SignupStep) : onClose}
              className="border-border/50">
              <ChevronLeft className="w-4 h-4 mr-1" /> {step === 1 ? 'Cancel' : 'Back'}
            </Button>
            {step < 3 && (
              <Button onClick={() => setStep((step + 1) as SignupStep)}
                disabled={step === 1 ? !name || !email : step === 2 ? !orgId : false}
                className="glow-primary">
                Next <ChevronRight className="w-4 h-4 ml-1" />
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
