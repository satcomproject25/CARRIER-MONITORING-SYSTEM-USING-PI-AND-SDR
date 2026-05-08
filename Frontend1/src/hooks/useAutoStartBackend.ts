/**
 * Hook to automatically start backend when dashboard loads
 * Ensures backend is always running for real-time metrics
 */

import { useEffect, useRef } from 'react';
import { Satellite } from '@/types/satellite';
import { cmsStartMonitor, cmsHealth, setApiTarget } from '@/lib/cmsApi';

export function useAutoStartBackend(satellites: Satellite[]) {
  const startedRef = useRef(false);

  useEffect(() => {
    // Only run once
    if (startedRef.current) return;

    const startBackends = async () => {
      // Find all online satellites with valid IPs
      const onlineSatellites = satellites.filter(
        sat => sat.status === 'online' && 
               sat.piIpAddress && 
               sat.piIpAddress !== '—' && 
               !sat.piIpAddress.includes('(')
      );

      if (onlineSatellites.length === 0) {
        console.log('[AutoStart] No online satellites with valid IPs');
        return;
      }

      console.log(`[AutoStart] Found ${onlineSatellites.length} online satellite(s)`);

      // Start backend for the first online satellite (primary)
      // In production, you might want to start all of them
      const primarySat = onlineSatellites[0];
      
      try {
        // Set API target to this satellite
        setApiTarget(primarySat.piIpAddress);
        
        // Check if already running
        try {
          const health = await cmsHealth();
          if (health.status === 'ok') {
            console.log(`[AutoStart] Backend already running for ${primarySat.name}`);
            startedRef.current = true;
            return;
          }
        } catch {
          // Not running or not reachable, try to start
        }

        // Start the backend
        const antennaId = primarySat.name.toLowerCase().replace(/\s+/g, '-');
        await cmsStartMonitor(true, antennaId);
        console.log(`[AutoStart] Started backend for ${primarySat.name}`);
        startedRef.current = true;
      } catch (error) {
        console.error(`[AutoStart] Failed to start backend for ${primarySat.name}:`, error);
      }
    };

    // Start after a short delay to let UI render
    const timeoutId = setTimeout(startBackends, 1000);

    return () => clearTimeout(timeoutId);
  }, [satellites]);
}
