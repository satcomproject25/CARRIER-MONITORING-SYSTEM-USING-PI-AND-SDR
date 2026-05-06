export interface Satellite {
  id: string;
  name: string;
  band: string;
  status: 'online' | 'offline';
  elevation: number;
  azimuth: number;
  latitude: number;
  longitude: number;
  state: string;
  country: string;
  groundStation: string;
  piIpAddress: string;
  inchargeName: string;
  facingPosition: string;
  hardwareSpecs: string;
  signalHealth: number;
  cnRatio: number;
  ebNo: number;
  launchDate: string;
}

export interface SignalData {
  time: string;
  frequency: number;
  power: number;
  noise: number;
  cnRatio: number;
  ebNo: number;
  signalHealth: number;
}

export interface AuthState {
  isAuthenticated: boolean;
  user: UserProfile | null;
}

export interface UserProfile {
  name: string;
  email: string;
  mobile: string;
  orgId: string;
  verified: boolean;
}

export type SignupStep = 1 | 2 | 3;
