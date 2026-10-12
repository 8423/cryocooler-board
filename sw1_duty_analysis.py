#!/usr/bin/env python3
"""
sw1_duty_analysis.py  --  Test 3, done without a current probe.

Recovers the inductor current I_L(t) of the V4 cryocooler board from a scope
capture of the SW1 node, using nothing but volt-second balance:

        L * dI_L/dt = v_SW1(t) - v_SW2(t)

In buck mode Q4 is held on, so v_SW2(t) = v_OUT(t) (to within I*Rds_on + I*DCR,
a few tens of mV, ignored here).  Everything else follows.

Two independent reconstructions are performed and compared:

  METHOD A (raw)  : integrate (v_SW1 - v_OUT) sample by sample.
                    Exact.  Keeps the ~386 kHz triangular ripple.
  METHOD B (duty) : find every switching edge, reduce each switching cycle to a
                    single duty number D_i, then integrate (D(t)*V_in - v_OUT).
                    This is the cycle-averaged current -- the ~30 kHz envelope
                    with the fast ripple removed.

If A and B disagree by more than ~10% in peak-to-peak, something is wrong with
the edge detection (check --threshold and the reported edge count).

The integration constant is fixed by charge balance, not guessed:
over a whole number of oscillation periods the capacitor gains no net charge,
so   mean(I_L) = mean(I_load) = mean(v_OUT)/R_load.

USAGE
-----
    python3 sw1_duty_analysis.py scope.csv --rload 176 --vin 24

    # explicit columns (0-based), e.g. t in col 0, SW1 in col 1, VOUT in col 2
    python3 sw1_duty_analysis.py scope.csv --tcol 0 --sw1col 1 --voutcol 2

    # no VOUT channel captured -- supply the DC value instead
    python3 sw1_duty_analysis.py scope.csv --vout-const 10.27 --rload 176

    # sanity-check the script itself on synthetic data
    python3 sw1_duty_analysis.py --selftest

REQUIREMENTS
------------
    numpy, matplotlib (matplotlib optional -- omit --plot if unavailable)

SCOPE SETUP
-----------
    Ch1 -> SW1, DC coupled, 10x probe, ground clip AT the FET source (short!)
    Ch2 -> VOUT, DC coupled
    Timebase: capture >= 10 oscillation periods (>= 350 us at 30 kHz)
    Sample rate: >= 40 MSa/s  (1% duty resolution = 26 ns at 386 kHz)
    Trigger: normal, on Ch2 AC-coupled, so the capture is envelope-aligned
"""

import argparse
import sys

import numpy as np

# ---------------------------------------------------------------- board facts
L_DEFAULT = 10.0e-6  # XAL1010-103MED
DCR = 13.4e-3  # ohm, typ
VIN_DEFAULT = 24.0


# ------------------------------------------------------------------ CSV input
def load_csv(path, tcol, sw1col, voutcol):
    """Read a scope CSV.  Skips any leading non-numeric header lines."""
    rows = []
    ncols = None
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            parts = [p.strip() for p in line.replace(";", ",").split(",")]
            try:
                vals = [float(p) for p in parts if p != ""]
            except ValueError:
                continue
            if len(vals) < 2:
                continue
            if ncols is None:
                ncols = len(vals)
            if len(vals) == ncols:
                rows.append(vals)
    if not rows:
        sys.exit(f"no numeric rows found in {path}")
    a = np.asarray(rows, dtype=float)
    print(f"  read {a.shape[0]} samples x {a.shape[1]} columns")

    t = a[:, tcol]
    sw1 = a[:, sw1col]
    vout = a[:, voutcol] if voutcol is not None and voutcol < a.shape[1] else None

    # Some scopes export time in ms or us.  If the whole record is shorter than
    # 1 us, the units are almost certainly not seconds.
    span = t[-1] - t[0]
    if span > 1.0:  # more than a second of "seconds" is not a switching capture
        print(f"  WARNING: time span is {span:g} -- are the units really seconds?")
    return t, sw1, vout


# ----------------------------------------------------------- edge / duty pass
def find_threshold(sw1):
    """Midpoint between the two levels of the square wave, from percentiles.
    Percentiles (not min/max) so ringing and overshoot do not set the level."""
    lo = np.percentile(sw1, 5)
    hi = np.percentile(sw1, 95)
    return 0.5 * (lo + hi), lo, hi


def extract_duty(t, sw1, thresh, hyst_frac=0.10):
    """Return (t_cycle, D, f_sw_inst) with one entry per switching cycle.

    A cycle runs from one rising edge to the next, so a SKIPPED PULSE simply
    produces one long cycle with a small D -- which is exactly the correct
    cycle-average and needs no special handling.

    Schmitt hysteresis is applied so ringing on the switch node does not
    produce spurious edges.
    """
    lo = np.percentile(sw1, 5)
    hi = np.percentile(sw1, 95)
    h = hyst_frac * (hi - lo)
    hi_th, lo_th = thresh + h, thresh - h

    # State machine over the samples (robust; the array is only ~1e5 long).
    state = sw1[0] > thresh
    rises, falls = [], []
    for i in range(1, len(sw1)):
        if not state and sw1[i] > hi_th:
            state = True
            rises.append(interp_cross(t, sw1, i, thresh))
        elif state and sw1[i] < lo_th:
            state = False
            falls.append(interp_cross(t, sw1, i, thresh))
    rises = np.asarray(rises)
    falls = np.asarray(falls)

    if len(rises) < 3:
        sys.exit(
            f"only {len(rises)} rising edges found -- check --threshold "
            f"(auto = {thresh:.2f} V, levels {lo:.2f}/{hi:.2f} V)"
        )

    tc, D, fs = [], [], []
    for k in range(len(rises) - 1):
        t0, t1 = rises[k], rises[k + 1]
        T = t1 - t0
        f_in = falls[(falls > t0) & (falls < t1)]
        ton = (f_in[0] - t0) if len(f_in) else T  # no fall -> stayed high
        tc.append(0.5 * (t0 + t1))
        D.append(ton / T)
        fs.append(1.0 / T)
    return np.asarray(tc), np.asarray(D), np.asarray(fs), rises, falls


def interp_cross(t, y, i, level):
    """Linear-interpolated crossing time between samples i-1 and i."""
    y0, y1 = y[i - 1], y[i]
    if y1 == y0:
        return t[i]
    frac = (level - y0) / (y1 - y0)
    return t[i - 1] + frac * (t[i] - t[i - 1])


# ----------------------------------------------------------------- spectrum
def dominant_freq(t, y, fmin=1e3, fmax=200e3):
    """Largest spectral line of y(t) between fmin and fmax.  Uniform t assumed;
    if t is non-uniform the signal is first resampled onto a uniform grid."""
    n = len(t)
    tu = np.linspace(t[0], t[-1], n)
    yu = np.interp(tu, t, y)
    yu = yu - yu.mean()
    yu = yu * np.hanning(n)
    dt = tu[1] - tu[0]
    Y = np.abs(np.fft.rfft(yu))
    f = np.fft.rfftfreq(n, dt)
    m = (f >= fmin) & (f <= fmax)
    if not m.any():
        return float("nan"), f, Y
    k = np.argmax(Y[m])
    return f[m][k], f, Y


# ------------------------------------------------------------- reconstruction
def integrate_current(t, vL, L, i_mean_target, detrend=True):
    """I_L(t) = I0 + (1/L) * cumulative_integral(vL dt).

    Any DC offset in vL integrates into a linear ramp, so a first-order
    detrend is applied (the true steady-state current has zero net drift over
    an integer number of oscillation periods).  The DC level is then set by
    charge balance rather than by the (unknown) integration constant.
    """
    i = np.concatenate([[0.0], np.cumsum(0.5 * (vL[1:] + vL[:-1]) * np.diff(t))]) / L
    drift = 0.0
    if detrend:
        p = np.polyfit(t, i, 1)
        drift = p[0] * L  # equivalent volts of offset that caused the ramp
        i = i - np.polyval(p, t)
    i = i - i.mean() + i_mean_target
    return i, drift


def summarize(name, t, i):
    ipk = i.max()
    itr = i.min()
    irms = float(np.sqrt(np.mean(i**2)))
    print(f"  {name:22s} peak {ipk:7.3f} A   trough {itr:7.3f} A   "
          f"p-p {ipk - itr:7.3f} A   RMS {irms:6.3f} A")
    return dict(peak=ipk, trough=itr, pp=ipk - itr, rms=irms)


# ------------------------------------------------------------------- selftest
def selftest():
    """Synthetic 386 kHz PWM whose duty is sinusoidally modulated at 30 kHz,
    driving a known 10 uH inductor into a 10.27 V rail.  The script should
    recover the modulation frequency and a current amplitude close to the
    analytic value."""
    print("SELFTEST: synthesising a 386 kHz PWM, duty modulated at 30 kHz\n")
    fsw, fosc, vin, vout, Lh, R = 385.7e3, 30.23e3, 24.0, 10.27, 10e-6, 176.0
    fs = 200e6
    t = np.arange(0, 12 / fosc, 1 / fs)
    D0, Dm = vout / vin, 0.30
    phase = (t * fsw) % 1.0
    D = D0 + Dm * np.sin(2 * np.pi * fosc * t)
    sw1 = np.where(phase < D, vin, 0.0) + np.random.normal(0, 0.05, t.size)
    vo = vout * np.ones_like(t)

    # analytic expectation: dI/dt = (D-D0)*vin/L -> I amplitude = Dm*vin/(L*w)
    ia = Dm * vin / (Lh * 2 * np.pi * fosc)
    print(f"  analytic current amplitude = {ia:.3f} A  (p-p {2*ia:.3f} A)\n")
    run(t, sw1, vo, Lh, vin, R, None, False)
    print("\n  -> p-p should match the analytic figure to a few percent.")


# ----------------------------------------------------------------- main logic
def run(t, sw1, vout, L, vin, rload, thresh, do_plot):
    if thresh is None:
        thresh, lo, hi = find_threshold(sw1)
        print(f"\nSW1 levels: low {lo:.2f} V, high {hi:.2f} V "
              f"-> threshold {thresh:.2f} V")
    vout_mean = float(np.mean(vout))
    i_load = vout_mean / rload
    print(f"VOUT mean {vout_mean:.3f} V, p-p {vout.max()-vout.min():.3f} V "
          f"-> mean load current {i_load:.4f} A")

    # ---- duty extraction
    tc, D, fs_inst, rises, falls = extract_duty(t, sw1, thresh)
    print(f"\nEdges: {len(rises)} rising, {len(falls)} falling, "
          f"{len(D)} complete cycles")
    print(f"Switching frequency: mean {np.mean(fs_inst)/1e3:8.2f} kHz   "
          f"min {np.min(fs_inst)/1e3:8.2f}   max {np.max(fs_inst)/1e3:8.2f}")
    print(f"  (a wide spread here = skipped pulses, not a modulated clock)")
    n_skip = int(np.sum(fs_inst < 0.7 * np.median(fs_inst)))
    print(f"  cycles longer than 1.4x the median (i.e. skipped pulses): {n_skip}"
          f"  ({100*n_skip/len(D):.1f} %)")

    print(f"\nDuty cycle: mean {D.mean():.4f}   min {D.min():.4f}   "
          f"max {D.max():.4f}   p-p {D.max()-D.min():.4f}")
    print(f"  steady-state D for buck at this rail = Vout/Vin = "
          f"{vout_mean/vin:.4f}")
    print(f"  modulation depth about that point    = "
          f"+{D.max()-vout_mean/vin:.4f} / -{vout_mean/vin-D.min():.4f}")
    if D.max() > 0.97:
        print("  NOTE: D saturating at 1.0 -- the loop is railing, not "
              "small-signal.")
    if D.min() < 0.03:
        print("  NOTE: D reaching 0 -- pulses are being dropped entirely.")

    # ---- frequencies
    f_D, _, _ = dominant_freq(tc, D)
    vout_ripple = float(vout.max() - vout.min())
    f_V = dominant_freq(t, vout)[0] if vout_ripple > 0.05 else float("nan")
    print(f"\nOscillation frequency from duty envelope : {f_D/1e3:7.3f} kHz")
    print(f"Oscillation frequency from VOUT          : {f_V/1e3:7.3f} kHz")
    if np.isfinite(f_D) and np.isfinite(f_V) and abs(f_D - f_V) > 0.05 * f_V:
        print("  *** These disagree by >5%.  Two separate oscillators would "
              "explain that; so would a bad threshold.  Check the edge count.")

    # Both methods are evaluated only over the span where D(t) is actually
    # defined (first to last complete switching cycle), so the two are
    # compared over identical data.
    m = (t >= tc[0]) & (t <= tc[-1])
    tm, sw1m, voutm = t[m], sw1[m], vout[m]

    # ---- METHOD A: raw volt-second integration
    print("\nInductor current:")
    vL_raw = sw1m - voutm
    iA, driftA = integrate_current(tm, vL_raw, L, i_load)
    sA = summarize("A raw (with ripple)", tm, iA)

    # ---- METHOD B: cycle-averaged duty integration
    D_i = np.interp(tm, tc, D)
    vL_avg = D_i * vin - voutm
    iB, driftB = integrate_current(tm, vL_avg, L, i_load)
    sB = summarize("B duty (envelope)", tm, iB)

    # A still carries the switching ripple, so compare B against A boxcar-
    # averaged over one switching period -- that is the like-for-like test.
    nsw = max(1, int(round((1.0 / np.median(fs_inst)) / np.median(np.diff(tm)))))
    k = np.ones(nsw) / nsw
    iA_avg = np.convolve(iA, k, mode="valid")
    ppA_avg = iA_avg.max() - iA_avg.min()
    print(f"\n  A boxcar-averaged over one switching period: "
          f"p-p {ppA_avg:.3f} A  (vs B {sB['pp']:.3f} A)")
    print(f"  ripple attributable to switching = {sA['pp'] - ppA_avg:.3f} A p-p "
          f"(textbook D(1-D)Vin/(L*fsw) = "
          f"{D.mean()*(1-D.mean())*vin/(L*np.median(fs_inst)):.3f} A)")
    print(f"  detrend removed the equivalent of {driftA*1e3:.1f} mV (A) / "
          f"{driftB*1e3:.1f} mV (B) of channel offset")
    if ppA_avg > 0 and abs(sB["pp"] - ppA_avg) / ppA_avg > 0.15:
        print("  *** A and B differ by >15% in p-p.  Suspect edge detection: "
              "check the threshold and the reported edge count.")

    # ---- what that current costs
    print("\nLosses implied by the envelope current (method B RMS):")
    irms = sB["rms"]
    p_dcr = irms**2 * DCR
    print(f"  I_L RMS                     {irms:6.3f} A")
    print(f"  L1 DCR loss  (13.4 mOhm)    {p_dcr*1e3:6.0f} mW")
    for rds, label in [(5.9e-3, "Q1+Q2 conduction, 5.9 mOhm")]:
        print(f"  {label:27s} {irms**2*rds*1e3:6.0f} mW")
    print("  (core loss and switching loss are NOT included -- they are the "
          "poorly-bounded terms)")
    print(f"\n  For comparison, DC-only operation at this rail would carry "
          f"{i_load:.3f} A RMS,\n  i.e. {(irms/i_load)**2:.0f}x less "
          f"conduction loss." if i_load > 0 else "")

    if do_plot:
        make_plot(tm, sw1m, voutm, tc, D, iA, iB, vout_mean / vin)

    return dict(t=tm, D=D, tc=tc, iA=iA, iB=iB, f_D=f_D, f_V=f_V)


def make_plot(t, sw1, vout, tc, D, iA, iB, D0):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n(matplotlib not available -- skipping plot)")
        return
    us = 1e6
    fig, ax = plt.subplots(4, 1, figsize=(11, 10), sharex=True)
    ax[0].plot(t * us, sw1, lw=0.4)
    ax[0].set_ylabel("SW1  [V]")
    ax[1].plot(t * us, vout, lw=0.8, color="tab:green")
    ax[1].set_ylabel("VOUT  [V]")
    ax[2].plot(tc * us, D, ".-", ms=2, lw=0.6, color="tab:red")
    ax[2].axhline(D0, ls="--", lw=0.8, color="k")
    ax[2].set_ylabel("duty D")
    ax[3].plot(t * us, iA, lw=0.4, color="0.6", label="A raw")
    ax[3].plot(t * us, iB, lw=1.2, color="tab:blue", label="B envelope")
    ax[3].set_ylabel("I_L  [A]")
    ax[3].set_xlabel("time  [us]")
    ax[3].legend(loc="upper right", fontsize=8)
    for a in ax:
        a.grid(alpha=0.3)
    fig.suptitle("V4 SW1 capture -- duty and reconstructed inductor current")
    fig.tight_layout()
    fig.savefig("sw1_analysis.png", dpi=140)
    print("\nwrote sw1_analysis.png")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv", nargs="?", help="scope CSV export")
    p.add_argument("--tcol", type=int, default=0, help="time column (default 0)")
    p.add_argument("--sw1col", type=int, default=1, help="SW1 column (default 1)")
    p.add_argument("--voutcol", type=int, default=2, help="VOUT column (default 2)")
    p.add_argument("--vout-const", type=float, default=None,
                   help="use this constant VOUT instead of a captured channel")
    p.add_argument("--vin", type=float, default=VIN_DEFAULT)
    p.add_argument("--L", type=float, default=L_DEFAULT, help="henries")
    p.add_argument("--rload", type=float, default=176.0, help="load resistor, ohms")
    p.add_argument("--threshold", type=float, default=None,
                   help="SW1 logic threshold in volts (default: auto)")
    p.add_argument("--plot", action="store_true", help="write sw1_analysis.png")
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args()

    if a.selftest:
        selftest()
        return
    if not a.csv:
        p.error("give a CSV file, or --selftest")

    print(f"Reading {a.csv} ...")
    t, sw1, vout = load_csv(a.csv, a.tcol, a.sw1col, a.voutcol)
    if a.vout_const is not None or vout is None:
        if a.vout_const is None:
            p.error("no VOUT column found -- pass --vout-const")
        vout = np.full_like(sw1, a.vout_const)
        print(f"  using constant VOUT = {a.vout_const} V "
              f"(this understates the true dI/dt swing)")
    run(t, sw1, vout, a.L, a.vin, a.rload, a.threshold, a.plot)


if __name__ == "__main__":
    main()
