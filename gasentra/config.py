"""Loads the per-deployment configuration. Only these files change between industries."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"


class Config:
    def __init__(self, config_dir=None):
        d = Path(config_dir) if config_dir else CONFIG_DIR

        def load(name):
            return json.loads((d / name).read_text(encoding="utf-8"))

        self.labels = load("labels.json")
        self.contacts = load("trusted_contacts.json")
        self.tools = load("tools.json")
        self.policy = load("policy.json")

    @property
    def order(self):
        return self.labels["sensitivity_order"]

    @property
    def taint_labels(self):
        return set(self.labels["taint_labels"])

    @property
    def internal_domains(self):
        return [d.lower() for d in self.contacts["internal_domains"]]

    @property
    def trusted_contacts(self):
        return {c.lower() for c in self.contacts["trusted_contacts"]}

    def label_for_path(self, path):
        for prefix, label in self.labels["path_labels"].items():
            if path.startswith(prefix):
                return label
        return self.labels["default_label"]

    def highest(self, labels):
        """Highest sensitivity label in a list (falls back to the default label)."""
        best = self.labels["default_label"]
        best_i = self.order.index(best)
        for lab in labels:
            if lab in self.order and self.order.index(lab) > best_i:
                best, best_i = lab, self.order.index(lab)
        return best
