import json
import pmt
from gnuradio import gr

class blk(gr.basic_block):
    def __init__(self):
        gr.basic_block.__init__(
            self,
            name="Control Receiver",
            in_sig=None,
            out_sig=None
        )

        self.message_port_register_in(pmt.intern("in"))
        self.set_msg_handler(pmt.intern("in"), self.handle_msg)

    def handle_msg(self, msg_pmt):
        try:
            msg_str = pmt.symbol_to_string(msg_pmt)
            data = json.loads(msg_str)

            print("Received control:", data)

            if "freq" in data:
                self.tb.set_center_freq(float(data["freq"]))

            if "rate" in data:
                self.tb.set_sample_rate(float(data["rate"]))

            if "fft" in data:
                self.tb.set_fft_size(int(data["fft"]))

        except Exception as e:
            print("Control error:", e)
