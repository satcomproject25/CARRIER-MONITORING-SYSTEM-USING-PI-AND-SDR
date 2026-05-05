SDR-Based Carrier Monitoring & Interference Detection System
1. Project Title & Description
Carrier Monitoring System A high-performance spectrum analysis and signal monitoring suite designed for Raspberry Pi and Software-Defined Radio (SDR) hardware. This system provides real-time detection of authorized and unauthorized transmissions by combining GNU Radio signal processing with a custom Python-based visualization and management layer.
2. Purpose
In complex RF environments, identifying unauthorized signals or "rogue" carriers is critical for maintaining link integrity. This project automates the process of spectrum surveying, comparing live signals against a database of "authorized" frequencies to immediately flag interference or unexpected spectrum usage.
3. Features
* Real-Time Carrier Detection: Automatically identifies signal peaks, calculates their center frequency, bandwidth, and power.
* Authorization Management: A built-in Web UI to manage a list of "Known Good" frequencies at runtime.
* Interference Alerting: Visual and logged alerts when a signal is detected outside of the authorized parameters.
* Distributed Architecture: Uses ZeroMQ (ZMQ) to decouple heavy signal processing (GNU Radio) from the visualization and logging dashboard.
* Dynamic Configuration: Adjust FFT size, sample rates, and detection thresholds without restarting the flowgraph.
4. Technologies Used
* Languages: Python 3
* Signal Processing: GNU Radio, SciPy, NumPy
* Communication: ZeroMQ (ZMQ), XML-RPC
* Web Framework: Flask (for the Authorization Manager)
* GUI: PyQt5, Matplotlib
5. Project Structure
* sdr_scipy.grc / .py: The core GNU Radio flowgraph that interfaces with the SDR hardware and publishes PSD data.
* Interference.py: The main visualization dashboard and interference detection logic.
* config_manager.py: A Flask-based utility to manage authorized frequency ranges via a web browser.
* sdr_scipy_epy_block_1.py: Embedded Python block for real-time carrier clustering and power estimation.
6. Usage
Prerequisites
Ensure you have GNU Radio 3.10+ and the required Python libraries installed:
Bash
pip install flask pyzmq numpy scipy matplotlib PyQt5
Running the System
The system operates in three parts that should be started in order:
1. Start the Authorization Manager: This opens the Web UI at http://localhost:5580 to define your "Authorized" signals.
Bash
python3 config_manager.py
2. Run the GNU Radio Flowgraph: This starts the SDR data acquisition and ZMQ transmission.
Bash
python3 sdr_scipy.py
3. Launch the Interference Dashboard: This displays the spectrum and highlights unauthorized carriers in real-time.
Bash
python3 Interference.py
Example: Authorizing a Signal
1. Open http://localhost:5580 in your browser.
2. Add a new frequency:
o Label: "Satellite Uplink A"
o Center: 70000000 (70 MHz)
o Bandwidth: 1000000 (1 MHz)
3. The Interference.py dashboard will now treat any signal within 69.5–70.5 MHz as "Authorized." Any signal appearing outside this range will be flagged in the logs.

