/**
 * Hook to fetch real-time satellite metrics from backend
 * Updates Signal Health, C/N, Eb/No on dashboard cards
 */

import { useState, useEffect } from 'react';
import { Satellite } from '@/types/satellite';
import { setApiTarget } from '@/lib/cmsApi';

interface SatelliteMetrics {
  signalHealth: number;
  cnRatio: number;
  ebNo: number;
  noiseFloor?: number;
  lastUpdate?: number;
}

/**
 * Fetch metrics from a single satellite's backend
 * Uses the SAME calculation as SignalMonitor for consistency
 */
async function fetchSatelliteMetrics(satellite: Satellite): Promise<SatelliteMetrics | null> {
  // Skip if no valid IP
  if (!satellite.piIpAddress || satellite.piIpAddress === '—' || satellite.piIpAddress.includes('(')) {
    return null;
  }

  // Skip if offline
  if (satellite.status !== 'online') {
    return null;
  }

  try {
    const baseUrl = satellite.piIpAddress === '127.0.0.1' || satellite.piIpAddress === 'localhost'
      ? '/api'
      : `http://${satellite.piIpAddress}:8780/api`;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2000); // 2 second timeout

    const response = await fetch(`${baseUrl}/snapshot`, {
      method: 'GET',
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      return null;
    }

    const data = await response.json();

    // Validate data exists
    if (!data || typeof data.noise_db !== 'number' || typeof data.detect_threshold_db !== 'number') {
      console.warn(`[Metrics] Invalid or empty data from ${satellite.name}`);
      return null;
    }

    // ============================================================
    // USE EXACT SAME CALCULATION AS SignalMonitor.tsx (lines 233-244)
    // This ensures dashboard and monitoring view show SAME values
    // ============================================================
    
    const noiseFloor = data.noise_db;
    const detectThreshold = data.detect_threshold_db;
    
    // C/N calculation: ONLY if carriers exist (same as monitoring view)
    // If no carriers detected, C/N = 0
    const hasCarriers = Array.isArray(data.carriers) && data.carriers.length > 0;
    const cnRatio = hasCarriers 
      ? Math.max(0, detectThreshold - noiseFloor)
      : 0;
    
    // Eb/No calculation: C/N * 0.7 (same as monitoring view)
    const ebNo = cnRatio * 0.7;
    
    // Signal health calculation: based on anomalies (same as monitoring view)
    const intfCount = (Array.isArray(data.interference) ? data.interference.length : 0) + 
                      (Array.isArray(data.gap_interference) ? data.gap_interference.length : 0);
    const unauthCount = data.unauth_count ?? 0;
    const hasAnomaly = intfCount > 0 || unauthCount > 0;
    
    const signalHealth = hasAnomaly ? 52 : 90;

    // Validate all values are finite
    if (!isFinite(cnRatio) || !isFinite(ebNo) || !isFinite(signalHealth)) {
      console.warn(`[Metrics] Non-finite values calculated for ${satellite.name}`);
      return null;
    }

    return {
      signalHealth: Math.round(signalHealth),
      cnRatio: Math.round(cnRatio * 10) / 10,
      ebNo: Math.round(ebNo * 10) / 10,
      noiseFloor: Math.round(noiseFloor * 10) / 10,
      lastUpdate: Date.now(),
    };
  } catch (error) {
    // Network error, timeout, or backend not running
    console.warn(`[Metrics] Failed to fetch from ${satellite.name}:`, error);
    return null;
  }
}

/**
 * Hook to continuously fetch metrics for all online satellites
 */
export function useSatelliteMetrics(satellites: Satellite[], updateInterval = 5000) {
  const [metrics, setMetrics] = useState<Map<string, SatelliteMetrics>>(new Map());
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let mounted = true;

    const fetchAllMetrics = async () => {
      if (!mounted) return;
      
      setLoading(true);
      const newMetrics = new Map<string, SatelliteMetrics>();

      // Fetch metrics for all online satellites in parallel
      const promises = satellites
        .filter(sat => sat.status === 'online')
        .map(async (sat) => {
          const m = await fetchSatelliteMetrics(sat);
          if (m && mounted) {
            newMetrics.set(sat.id, m);
          }
        });

      await Promise.all(promises);

      if (mounted) {
        setMetrics(newMetrics);
        setLoading(false);
      }
    };

    // Initial fetch
    fetchAllMetrics();

    // Set up interval for continuous updates
    const intervalId = setInterval(fetchAllMetrics, updateInterval);

    return () => {
      mounted = false;
      clearInterval(intervalId);
    };
  }, [satellites, updateInterval]);

  return { metrics, loading };
}

/**
 * Hook to fetch metrics for a single satellite
 */
export function useSingleSatelliteMetrics(satellite: Satellite | null, updateInterval = 5000) {
  const [metrics, setMetrics] = useState<SatelliteMetrics | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!satellite) {
      setMetrics(null);
      return;
    }

    let mounted = true;

    const fetchMetrics = async () => {
      if (!mounted) return;
      
      setLoading(true);
      const m = await fetchSatelliteMetrics(satellite);
      
      if (mounted) {
        setMetrics(m);
        setLoading(false);
      }
    };

    // Initial fetch
    fetchMetrics();

    // Set up interval
    const intervalId = setInterval(fetchMetrics, updateInterval);

    return () => {
      mounted = false;
      clearInterval(intervalId);
    };
  }, [satellite, updateInterval]);

  return { metrics, loading };
}
