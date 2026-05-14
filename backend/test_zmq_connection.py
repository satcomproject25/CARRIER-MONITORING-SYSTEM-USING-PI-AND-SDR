#!/usr/bin/env python3
"""
ZMQ Connection Test Utility

Tests connectivity to GNU Radio ZMQ endpoints before starting the full pipeline.
Useful for troubleshooting distributed deployments.

Usage:
    python test_zmq_connection.py
    python test_zmq_connection.py tcp://192.168.1.20:5555
"""

import os
import sys
import time
import zmq
import numpy as np

def test_endpoint(endpoint, socket_type=zmq.SUB, timeout_ms=5000, test_name="Endpoint"):
    """
    Test a single ZMQ endpoint for connectivity and data reception.
    
    Parameters
    ----------
    endpoint : str
        ZMQ endpoint address (e.g., "tcp://192.168.1.20:5555")
    socket_type : int
        ZMQ socket type (default: zmq.SUB)
    timeout_ms : int
        Timeout in milliseconds for receive test
    test_name : str
        Human-readable name for logging
    
    Returns
    -------
    bool
        True if connection successful and data received
    """
    print(f"\n{'='*70}")
    print(f"Testing {test_name}: {endpoint}")
    print(f"{'='*70}")
    
    ctx = zmq.Context()
    sock = None
    
    try:
        # Initialize socket
        print(f"[1/4] Creating ZMQ {socket_type} socket...")
        sock = ctx.socket(socket_type)
        
        # Configure socket
        print(f"[2/4] Configuring socket options...")
        if socket_type == zmq.SUB:
            sock.setsockopt(zmq.SUBSCRIBE, b"")
        sock.setsockopt(zmq.CONFLATE, 1)
        sock.setsockopt(zmq.RCVHWM, 1)
        sock.setsockopt(zmq.LINGER, 0)
        sock.setsockopt(zmq.RCVTIMEO, timeout_ms)
        
        # Connect
        print(f"[3/4] Connecting to {endpoint}...")
        sock.connect(endpoint)
        print(f"✓ Connection established")
        
        # Test receive
        print(f"[4/4] Waiting for data (timeout: {timeout_ms}ms)...")
        start_time = time.time()
        
        try:
            data = sock.recv()
            elapsed_ms = (time.time() - start_time) * 1000
            
            print(f"✓ Data received!")
            print(f"  - Latency: {elapsed_ms:.1f} ms")
            print(f"  - Size: {len(data)} bytes")
            
            # Try to parse as IQ samples
            try:
                iq = np.frombuffer(data, dtype=np.complex64)
                print(f"  - IQ samples: {len(iq)}")
                print(f"  - Sample range: [{np.min(np.abs(iq)):.6f}, {np.max(np.abs(iq)):.6f}]")
            except:
                # Try to parse as JSON
                try:
                    import json
                    obj = json.loads(data.decode('utf-8'))
                    print(f"  - JSON keys: {list(obj.keys())}")
                except:
                    print(f"  - Format: binary (not IQ or JSON)")
            
            print(f"\n✓✓✓ {test_name} TEST PASSED ✓✓✓")
            return True
            
        except zmq.Again:
            print(f"✗ Timeout: No data received within {timeout_ms}ms")
            print(f"\nPossible causes:")
            print(f"  1. GNU Radio not running on remote host")
            print(f"  2. ZMQ PUB not publishing data")
            print(f"  3. Firewall blocking port")
            print(f"  4. Incorrect endpoint address")
            print(f"\n✗✗✗ {test_name} TEST FAILED ✗✗✗")
            return False
            
    except zmq.ZMQError as e:
        print(f"✗ ZMQ Error: {e}")
        print(f"\n✗✗✗ {test_name} TEST FAILED ✗✗✗")
        return False
        
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        print(f"\n✗✗✗ {test_name} TEST FAILED ✗✗✗")
        return False
        
    finally:
        if sock:
            sock.close()
        ctx.term()


def main():
    """Run ZMQ connection tests for all configured endpoints."""
    
    print("\n" + "="*70)
    print("ZMQ CONNECTION TEST UTILITY")
    print("="*70)
    
    # Load configuration from environment or defaults
    LOCAL_MODE = os.environ.get("LOCAL_MODE", "true").lower() == "true"
    REMOTE_MODE = os.environ.get("REMOTE_MODE", "false").lower() == "true"
    
    DEFAULT_IQ_ADDR = "tcp://127.0.0.1:5555"
    DEFAULT_META_ADDR = "tcp://127.0.0.1:5556"
    DEFAULT_CARRIER_ADDR = "tcp://127.0.0.1:5557"
    
    IQ_ADDR = os.environ.get("SCIPY_ZMQ_IQ_ADDR", DEFAULT_IQ_ADDR)
    META_ADDR = os.environ.get("SCIPY_ZMQ_META_ADDR", DEFAULT_META_ADDR)
    CARRIER_ADDR = os.environ.get("SCIPY_ZMQ_CARRIER_ADDR", DEFAULT_CARRIER_ADDR)
    
    # Allow command-line override for quick testing
    if len(sys.argv) > 1:
        IQ_ADDR = sys.argv[1]
        print(f"\nUsing command-line endpoint: {IQ_ADDR}")
    
    # Display configuration
    mode = "LOCAL" if LOCAL_MODE else "REMOTE" if REMOTE_MODE else "HYBRID"
    print(f"\nDeployment mode: {mode}")
    print(f"IQ stream:       {IQ_ADDR}")
    print(f"Metadata stream: {META_ADDR}")
    print(f"Carrier hints:   {CARRIER_ADDR}")
    
    # Run tests
    results = []
    
    # Test IQ stream (most critical)
    results.append(("IQ Stream", test_endpoint(IQ_ADDR, zmq.SUB, 5000, "IQ Stream")))
    
    # Test metadata stream
    results.append(("Metadata", test_endpoint(META_ADDR, zmq.SUB, 5000, "Metadata Stream")))
    
    # Test carrier hints (optional, may timeout if not configured)
    results.append(("Carrier Hints", test_endpoint(CARRIER_ADDR, zmq.SUB, 2000, "Carrier Hints")))
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{name:20s} {status}")
    
    all_passed = all(passed for _, passed in results)
    critical_passed = results[0][1]  # IQ stream is critical
    
    print("="*70)
    
    if all_passed:
        print("\n✓✓✓ ALL TESTS PASSED ✓✓✓")
        print("\nYou can now start Interference.py:")
        print("  python backend/Interference.py")
        return 0
    elif critical_passed:
        print("\n⚠ PARTIAL SUCCESS ⚠")
        print("\nIQ stream is working (critical).")
        print("Optional streams failed but pipeline can still run.")
        print("\nYou can start Interference.py:")
        print("  python backend/Interference.py")
        return 0
    else:
        print("\n✗✗✗ CRITICAL FAILURE ✗✗✗")
        print("\nIQ stream connection failed.")
        print("Cannot start Interference.py until this is resolved.")
        print("\nTroubleshooting steps:")
        print("  1. Verify GNU Radio is running:")
        print("     ps aux | grep sdr_scipy")
        print("  2. Check ZMQ binding:")
        print("     netstat -tuln | grep 5555")
        print("  3. Test network connectivity:")
        print(f"     ping {IQ_ADDR.split('//')[1].split(':')[0]}")
        print("  4. Check firewall rules:")
        print("     sudo ufw status")
        return 1


if __name__ == "__main__":
    sys.exit(main())
