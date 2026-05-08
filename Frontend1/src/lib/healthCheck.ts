/**
 * Health check utilities for automatic satellite status detection
 */

import { Satellite } from '@/types/satellite';

/**
 * Check if a Raspberry Pi is reachable by testing its health endpoint
 */
export async function checkPiHealth(piIpAddress: string): Promise<boolean> {
  // Skip check for simulation mode or invalid IPs
  if (!piIpAddress || piIpAddress === '—' || piIpAddress.includes('(')) {
    return false;
  }

  try {
    const baseUrl = piIpAddress === '127.0.0.1' || piIpAddress === 'localhost'
      ? '/api'
      : `http://${piIpAddress}:8780/api`;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000); // 3 second timeout

    const response = await fetch(`${baseUrl}/health`, {
      method: 'GET',
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (response.ok) {
      const data = await response.json();
      return data.status === 'ok';
    }
    return false;
  } catch (error) {
    // Network error, timeout, or CORS issue
    return false;
  }
}

/**
 * Check health for multiple satellites in parallel
 */
export async function checkMultipleSatellitesHealth(
  satellites: Satellite[]
): Promise<Map<string, boolean>> {
  const results = new Map<string, boolean>();

  const checks = satellites.map(async (sat) => {
    const isHealthy = await checkPiHealth(sat.piIpAddress);
    results.set(sat.id, isHealthy);
  });

  await Promise.all(checks);
  return results;
}

/**
 * Get suggested status based on Pi health check
 */
export async function getSuggestedStatus(piIpAddress: string): Promise<'online' | 'offline'> {
  const isHealthy = await checkPiHealth(piIpAddress);
  return isHealthy ? 'online' : 'offline';
}
