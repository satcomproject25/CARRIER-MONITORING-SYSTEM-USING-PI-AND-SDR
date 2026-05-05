import numpy as np
import time
from gnuradio import gr

class blk(gr.sync_block):

    def __init__(self, sample_rate=10e6, center_freq=70e6,
                 fft_size=2048, snr_margin_db=6):

        gr.sync_block.__init__(
            self,
            name='Carrier Detector',
            in_sig=[(np.float32, fft_size)],
            out_sig=None
        )

        self.sample_rate = sample_rate
        self.center_freq = center_freq
        self.fft_size = fft_size
        self.df = sample_rate / fft_size
        self.snr_margin_db = snr_margin_db

        self.carriers = {}
        self.next_id = 1

        self.last_print = 0
        self.print_interval = 0.5  # seconds

    def work(self, input_items, output_items):
        now = time.time()

        for psd in input_items[0]:

            noise_floor = np.median(psd)
            threshold = noise_floor + self.snr_margin_db

            active_bins = np.where(psd > threshold)[0]
            if active_bins.size == 0:
                self.carriers.clear()
                continue

            clusters = np.split(
                active_bins,
                np.where(np.diff(active_bins) > 1)[0] + 1
            )

            updated = {}

            for cluster in clusters:
                if len(cluster) < 3:
                    continue

                bw_hz = len(cluster) * self.df
                center_bin = np.mean(cluster)
                freq = self.center_freq + (center_bin - self.fft_size/2) * self.df

                lin_power = np.sum(10 ** (psd[cluster] / 10))
                power_db = 10 * np.log10(lin_power + 1e-12)

                cid = None
                for pid, pfreq in self.carriers.items():
                    if abs(freq - pfreq) < self.df:
                        cid = pid
                        break

                if cid is None:
                    cid = self.next_id
                    self.next_id += 1

                updated[cid] = freq

                # PRINT ONLY PERIODICALLY
                if now - self.last_print >= self.print_interval:
                    print(
                        f"[Carrier {cid}] "
                        f"Freq={freq/1e6:.3f} MHz | "
                        f"BW={bw_hz/1e3:.1f} kHz | "
                        f"Pwr={power_db:.1f} dB"
                    )

            if now - self.last_print >= self.print_interval:
                self.last_print = now

            self.carriers = updated

        return len(input_items[0])
