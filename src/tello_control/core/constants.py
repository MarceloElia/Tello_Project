"""Shared SDK limit constants — single source of truth for both MockTello and the
voice validation layer.  Import from here; never duplicate these literals."""

DIST_MIN, DIST_MAX = 20, 500    # cm
ANGLE_MIN, ANGLE_MAX = 1, 360   # degrees

RC_MIN, RC_MAX = -100, 100      # send_rc_control value range (per axis)
RC_CRUISE = 40                  # default per-axis gesture speed (safe < full throttle)
