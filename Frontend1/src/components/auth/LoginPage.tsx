import { useState } from 'react';
import { Shield, Eye, EyeOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SignupModal } from './SignupModal';
import { useAppStore } from '@/store/appStore';
import isroLogo from '../../../image/isro_dark.png';

export const LoginPage = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showSignup, setShowSignup] = useState(false);
  const [error, setError] = useState('');
  const login = useAppStore((s) => s.login);

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (email === 'admin@isro.gov.in' && password === 'isro2024') {
      login({ name: 'Mission Control', email, mobile: '+91-9876543210', orgId: 'ISRO-MC-001', verified: true });
    } else {
      setError('Invalid credentials. Use admin@isro.gov.in / isro2024');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center relative overflow-hidden bg-background">
      {/* Animated background */}
      <div className="absolute inset-0">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary/5 rounded-full blur-3xl animate-pulse-slow" />
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-primary/3 rounded-full blur-3xl animate-pulse-slow" style={{ animationDelay: '1.5s' }} />
        {/* Stars */}
        {Array.from({ length: 50 }).map((_, i) => (
          <div key={i} className="absolute w-px h-px bg-foreground/40 rounded-full animate-pulse" style={{
            left: `${Math.random() * 100}%`, top: `${Math.random() * 100}%`,
            animationDelay: `${Math.random() * 3}s`, animationDuration: `${2 + Math.random() * 3}s`,
          }} />
        ))}
      </div>

      <div className="relative z-10 w-full max-w-md p-8">
        <div className="glass-panel p-8 animate-scale-in">
          {/* ISRO Logo */}
          <div className="flex flex-col items-center mb-8">
            <img
              src={isroLogo}
              alt="ISRO"
              className="h-20 w-auto object-contain mb-4"
            />
            <h1 className="text-2xl font-bold text-gradient">ISRO CMS</h1>
            <p className="text-muted-foreground text-sm mt-1">Carrier Monitoring System</p>
          </div>

          <form onSubmit={handleLogin} className="space-y-5">
            <div className="space-y-2">
              <Label className="text-muted-foreground text-xs uppercase tracking-wider">Organization Email</Label>
              <Input value={email} onChange={(e) => { setEmail(e.target.value); setError(''); }}
                placeholder="user@isro.gov.in" className="bg-secondary/50 border-border/50 focus:border-primary/50 h-11" />
            </div>
            <div className="space-y-2">
              <Label className="text-muted-foreground text-xs uppercase tracking-wider">Password</Label>
              <div className="relative">
                <Input type={showPassword ? 'text' : 'password'} value={password}
                  onChange={(e) => { setPassword(e.target.value); setError(''); }}
                  placeholder="••••••••" className="bg-secondary/50 border-border/50 focus:border-primary/50 h-11 pr-10" />
                <button type="button" onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors">
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
            {error && <p className="text-destructive text-sm font-mono">{error}</p>}
            <Button type="submit" className="w-full h-11 font-semibold glow-primary transition-all hover:scale-[1.02] active:scale-[0.98]">
              <Shield className="w-4 h-4 mr-2" /> Secure Login
            </Button>
          </form>

          <div className="mt-6 text-center">
            <button onClick={() => setShowSignup(true)}
              className="text-primary/80 hover:text-primary text-sm transition-colors">
              New Personnel? <span className="underline">Register Access</span>
            </button>
          </div>

          <div className="mt-6 pt-4 border-t border-border/30 text-center">
            <p className="text-muted-foreground/60 text-xs font-mono">RESTRICTED ACCESS • ISRO MISSION CONTROL</p>
          </div>
        </div>
      </div>

      {showSignup && <SignupModal onClose={() => setShowSignup(false)} />}
    </div>
  );
};
