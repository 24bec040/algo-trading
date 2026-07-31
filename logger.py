import csv
import os
from datetime import datetime

class DataLogger:
    def __init__(self, filename="trade_log.csv"):
        self.filename = filename
        self.headers = [
            "timestamp", "btc_price", "atm_strike", "call_prem", "put_prem", 
            "combined_prem", "iv", "btc_change_15m", "edge_score", "decision"
        ]
        self._init_file()

    def _init_file(self):
        if not os.path.exists(self.filename):
            with open(self.filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(self.headers)

    def log_sample(self, data):
        """Expects a dictionary with header keys."""
        with open(self.filename, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.headers)
            writer.writerow(data)

    def log_event(self, message):
        """Log general events for debugging."""
        with open("events.log", "a") as f:
            f.write(f"{datetime.now().isoformat()} - {message}\n")
