"""Printer and material settings, read from a profile file (profiles/*.toml). No limit is hard-coded in a check."""
import math, os
from dataclasses import dataclass, field
try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None

ROOT = os.environ.get("FIT2PRINT_HOME") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # the folder holding deps.toml and profiles/
DEFAULT_PROFILE = os.path.join(ROOT, "profiles", "bambu_a1_pla.toml")

@dataclass
class Settings:
    name: str = "defaults"
    filament_diameter: float = 1.75
    flow_limit: float = 12.0
    flow_share_check: float = 0.05
    air_support_distance: float = 0.9
    air_check: float = 8.0
    air_block: float = 25.0
    resolution: float = 0.25
    reach: float = 0.6
    look: float = 15.0
    cantilever_check: float = 3.5
    cantilever_block: float = 6.0
    bridge_check: float = 15.0
    bridge_block: float = 30.0

    @property
    def filament_area(self):
        return math.pi * (self.filament_diameter / 2) ** 2

    @classmethod
    def load(cls, path=None):
        path = path or DEFAULT_PROFILE
        if tomllib is None:
            raise RuntimeError("Python 3.11+ is needed to read profile files")
        with open(path, "rb") as f:
            d = tomllib.load(f)
        a, k = d.get("air", {}), d.get("anchor", {})
        return cls(name=d.get("name", os.path.basename(path)), filament_diameter=d.get("filament_diameter", 1.75),
                   flow_limit=d.get("flow_limit", 12.0), flow_share_check=d.get("flow_share_check", 0.05),
                   air_support_distance=a.get("support_distance", 0.9), air_check=a.get("check", 8.0), air_block=a.get("block", 25.0),
                   resolution=k.get("resolution", 0.25), reach=k.get("reach", 0.6), look=k.get("look", 15.0),
                   cantilever_check=k.get("cantilever_check", 3.5), cantilever_block=k.get("cantilever_block", 6.0),
                   bridge_check=k.get("bridge_check", 15.0), bridge_block=k.get("bridge_block", 30.0))
