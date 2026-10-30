"""Snap-fit hooks: will the hook survive being bent, and how many times? A hook is a cantilever beam. Its peak strain when its tip is pushed
back by `deflection` is  e = 1.5 * t * deflection / length^2  (t = thickness in the bending direction, rectangular section, constant thickness).
Judged against the profile's strain limit (profiles/*.toml [snap]); the limit is a starting guess until a hook coupon is printed."""
from .settings import Settings

def strain(thickness, length, deflection):
    return 1.5 * thickness * deflection / length ** 2

def check(thickness, length, deflection, cfg=None):
    """-> (verdict, strain, message). CHECK above the limit, BLOCK above twice the limit."""
    cfg = cfg or Settings()
    e = strain(thickness, length, deflection)
    v = "BLOCK" if e > 2 * cfg.snap_strain_limit else "CHECK" if e > cfg.snap_strain_limit else "PASS"
    return v, e, f"hook {thickness} x {length} mm bent {deflection} mm: strain {e * 100:.1f} % (limit {cfg.snap_strain_limit * 100:.1f} %)"

def min_length(thickness, deflection, cfg=None):
    """The shortest hook that stays inside the limit."""
    cfg = cfg or Settings()
    return (1.5 * thickness * deflection / cfg.snap_strain_limit) ** 0.5
