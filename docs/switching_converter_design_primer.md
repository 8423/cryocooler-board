# Switching Converters, Buck-Boost Loop Design, and Component Selection

### A first-principles primer, then applied to the DarkNESS cryocooler board

---

**How to read this.** Part I is general theory — how a switching converter works and
what the control loop is doing. Part II is the component-selection procedure, in the
order you should actually make the decisions, with the governing equations and the
failure modes for each part. Part III runs that procedure for your actual specification
and compares the result with what is on V4.

Part III contains one significant **correction** to my earlier review: the 1.88 MHz
switching frequency is far more defensible than I said, and I'll show why.

---
---

# PART I — HOW A SWITCHING CONVERTER WORKS

## 1. Why switch at all

To get 12 V from 24 V you can drop the difference across a series device (a linear
regulator). The device passes the full load current at the full voltage difference, so
it burns `(V_in − V_out) × I_out`. At 24 → 12 V that is 50 % of the delivered power,
always, no matter how good the device is. Efficiency is bounded by `V_out / V_in`.

The switching converter's trick is to never operate the pass device in its resistive
region. It is either **fully on** (large current, near-zero voltage across it) or
**fully off** (large voltage across it, near-zero current). In both states the product
`V × I` is small, so the device dissipates little. The energy that a linear regulator
would have burned is instead *stored* — in an inductor's magnetic field and a
capacitor's electric field — and handed on to the load.

Everything that follows is a consequence of that one idea. The switch produces a
chopped square wave; the inductor and capacitor form a low-pass filter that recovers
the DC average; the control loop adjusts the chopping ratio to hold that average where
you want it. The costs of the trick are: switching transitions are not instantaneous
(so there *is* loss during them), the chopping generates EMI, and the filter's dynamics
create a control problem that can go unstable.

## 2. The two conservation laws

Almost every DC-DC equation you will ever need comes from two steady-state facts.

### 2.1 Volt-second balance (the inductor law)

`V = L · di/dt`. In periodic steady state the inductor current must return to the same
value each cycle, so `∫V dt = 0` over one period. The volts applied during the on-time
must equal (in magnitude) the volt-seconds applied during the off-time:

```
V_on · t_on = V_off · t_off
```

**This single equation gives you the conversion ratio of every topology.** Everything
else — duty cycle limits, minimum on-time constraints, why boost has a maximum duty —
falls out of it.

### 2.2 Charge balance (the capacitor law)

`I = C · dv/dt`. In steady state the capacitor voltage returns to the same value each
cycle, so the average current into a capacitor is zero. Whatever AC current the
switching action produces must circulate through the capacitor, and the DC component
must go to the load.

**This gives you every capacitor RMS-current and ripple-voltage equation.**

## 3. The three basic cells

### 3.1 Buck (step-down)

```
        Q1
 Vin ────/ ──────┬──── L ────┬──── Vout
                 │           │
                Q2          Cout
                 │           │
 GND ────────────┴───────────┴──── GND
```

- Q1 on: inductor sees `V_in − V_out`, current ramps **up**.
- Q1 off, Q2 on: inductor sees `−V_out`, current ramps **down**.
- Volt-seconds: `(V_in − V_out)·D·T = V_out·(1−D)·T`

```
                D = V_out / V_in
```

The inductor is in series with the load, so **the input current is chopped** and the
**output current is continuous**. That is why a buck needs a large input capacitor with
high RMS-current capability, and a comparatively relaxed output capacitor.

Ripple current:
```
                ΔI_L(p-p) = (V_in − V_out)·V_out / (L · f_sw · V_in)
```
which is maximised at `V_out = V_in/2`.

### 3.2 Boost (step-up)

```
              L        D (or Q1)
 Vin ────────▄▄▄▄──┬────/ ──────┬──── Vout
                   │            │
                  Q2           Cout
                   │            │
 GND ──────────────┴────────────┴──── GND
```

- Q2 on: inductor sees `V_in`, ramps up, and the load is supplied **only by C_out**.
- Q2 off: inductor sees `V_in − V_out` (negative), ramps down into the output.
- Volt-seconds: `V_in·D·T = (V_out − V_in)·(1−D)·T`

```
                V_out / V_in = 1 / (1 − D)
```

Now the **input current is continuous** and the **output current is chopped**. So the
output capacitor takes the beating:
```
                I_Cout(RMS) = I_out · √(V_out/V_in − 1)
```
Also note `I_L(DC) = I_out · V_out / (V_in · η)` — the inductor carries *more* than the
load current, by the conversion ratio. This surprises people.

Boost has a hard structural property that buck does not: **you cannot get energy from
input to output instantaneously.** To deliver more current you must first store more
energy, which means increasing the on-time, which momentarily *disconnects* the output
for longer. Output voltage therefore initially goes the **wrong way**. That is the
right-half-plane zero, §11.

### 3.3 Four-switch (non-inverting) buck-boost

```
        Q1                    Q3
 Vin ────/ ────┬────▄▄▄▄──────┬───/ ───┬──── Vout
               │      L       │        │
              Q2             Q4       Cout
               │              │        │
 GND ──────────┴──────────────┴────────┴──── GND
   \___ "buck leg" ___/   \___ "boost leg" ___/
      SW1                       SW2
```

This is your topology. It is a buck cell cascaded with a boost cell sharing one
inductor, and it runs in one of three modes:

| Mode | Condition | Buck leg (Q1/Q2) | Boost leg (Q3/Q4) |
|---|---|---|---|
| **Buck** | V_in comfortably > V_out | switching, D = V_out/V_in | Q3 **on continuously**, Q4 off |
| **Boost** | V_in comfortably < V_out | Q1 **on continuously**, Q2 off | switching, D = 1 − V_in/V_out |
| **Buck-boost** | V_in ≈ V_out | switching | switching |

In the TPS55288, Q3/Q4 are the two integrated 16 A FETs and Q1/Q2 are your external
IPZ40N04S5L parts. The datasheet says it plainly: *"When the input voltage is close to
the output voltage, the TPS55288 operates in one-cycle buck and one-cycle boost mode
alternately."*

**Three consequences you must design around:**

1. **In buck mode only two switches commutate.** In buck-boost mode all four do, so
   switching loss and gate-drive current roughly double. Which mode you are in matters
   enormously to your thermal budget, and you can read it directly from the STATUS
   register (07h, bits [1:0]).
2. **The plant changes shape between modes.** In buck mode there is no right-half-plane
   zero. In boost/buck-boost mode there is, and it moves with load and line. Your
   compensator has to be stable in *both*, which means designing for the worse one.
3. **The transition region is where converters misbehave.** Duty cycle is being pushed
   toward its limits on one leg while the other leg starts moving. Minimum on-time and
   minimum off-time constraints bite here.

## 4. CCM, DCM, and forced PWM

The inductor current is a triangle of peak-to-peak height ΔI riding on a DC level equal
to (buck) the load current.

- **CCM (continuous conduction mode):** `I_out > ΔI/2`, current never reaches zero.
- **DCM (discontinuous):** with a diode or a synchronous FET that turns off at zero
  crossing, current sits at zero for part of the cycle. The conversion ratio becomes
  load-dependent and the small-signal plant changes (the second pole moves far out).
- **FPWM (forced PWM):** the synchronous FET is *not* turned off at zero crossing, so
  the current is allowed to go **negative**. The converter stays in CCM at any load,
  including no load. Frequency stays fixed, the plant stays the same shape, and there
  is no audible or subharmonic behaviour — at the cost of circulating current.
- **PFM / power-save:** the converter skips pulses at light load. Much better light-load
  efficiency, but the effective frequency wanders, which is bad if you care about where
  your EMI lands.

**The non-obvious bit, and it matters a lot for your board:** in FPWM with large ripple,
the negative current at the end of the off-period *charges the switch node back up*
before the high-side FET turns on. That is **zero-voltage switching**. It eliminates the
high-side turn-on loss, the C_oss loss, and the low-side body-diode reverse-recovery
loss. The condition is:

```
        |I_L(min)| > V_in · √(C_oss,total / L)
```

So a converter with "too much" ripple can be *more* efficient per switching event than
one with textbook 30 % ripple. Hold that thought for Part III.

## 5. Synchronous rectification and dead time

Replacing the freewheel diode with a MOSFET drops the conduction loss from
`I·V_f` (~0.5 V) to `I²·R_DS(on)` (~mV). At any current above a few hundred mA this is
a large win, and it is why every modern converter is synchronous.

The price is that you now have two switches across the input rail, and **if both are on
at once you have a short circuit from V_in to ground.** The controller inserts a
**dead time** between one turning off and the other turning on. During dead time the
current freewheels through the body diode (higher loss, hence you want dead time short)
— but if dead time is *too* short you get **cross-conduction / shoot-through**.

Shoot-through energy per event is roughly:
```
        E ≈ V_in · I_avg,overlap · t_overlap ,   I_pk ≈ V_in · t_overlap / L_loop
```
Loop inductance is the only thing limiting the current, so it can be tens of amps. It
dissipates in **both** FETs and is essentially independent of load current. **Shoot-through
is the classic cause of "both FETs are hot and it doesn't get better when I unload it."**

Controllers use fixed dead time, adaptive dead time (sense the gate/switch node and wait),
or predictive dead time. **Adaptive schemes assume the gate node they are watching is
electrically close to the FET.** Long gate traces break that assumption.

## 6. Where the losses actually are

Worth memorising the shape of this list, because it tells you which component decisions
matter.

| Loss | Scales as | Dominant when |
|---|---|---|
| Conduction, FETs | `I_rms² · R_DS(on) · D` | high current |
| Conduction, inductor DCR | `I_rms² · DCR` | high current |
| Turn-on / turn-off switching | `½·V·I·(t_r+t_f)·f_sw` | high voltage × frequency |
| C_oss (output capacitance) | `½·C_oss·V²·f_sw` | high voltage, **load-independent** |
| Reverse recovery Q_rr | `Q_rr·V·f_sw` | hard-switched sync rect, **load-independent** |
| Gate drive | `Q_g·V_drive·f_sw` | **load-independent** |
| Body-diode conduction | `V_f·I·t_dead·f_sw` | long dead time |
| Core loss | `k·f^a·ΔB^b` | large ripple |
| Bias / LDO | `(V_src − V_bias)·I_bias` | high input voltage |
| Shoot-through | `E_ov·f_sw` | bad gate layout, **load-independent** |

**Note how many of these are load-independent.** At light load, a converter's losses are
dominated by the load-independent terms — which are all proportional to frequency and to
the size of the switch. That is the whole story of a big converter running a small load.

## 7. The control problem

You have a plant (the power stage) whose output voltage responds to a control input
(duty cycle, or current command). You want `V_out` to equal a reference despite changes
in line and load. So you close a feedback loop:

```
  V_ref ──►(Σ)──► compensator ──► modulator ──► power stage ──► V_out
             ▲                                                    │
             └──────────────── feedback divider ◄─────────────────┘
```

The loop gain is `T(s) = G_plant(s) · G_mod · G_comp(s) · H_fb`. Stability is judged at
the **crossover frequency** `f_c`, where |T| = 1 (0 dB):

- **Phase margin** = 180° + ∠T at f_c. Target **45–60°**. Below ~30° you get ringing on
  load steps; at 0° you oscillate.
- **Gain margin** = how far below 0 dB the gain is when the phase hits −180°. Target
  **≥ 8–10 dB**.
- A sampled-data system also needs the gain well down by `f_sw/2`; a common rule is at
  least 8 dB of attenuation at half the switching frequency.

**Bandwidth is not free and is not always good.** Higher `f_c` means faster load-step
response and lower output impedance, but less noise rejection and less margin against
component tolerance, DC-bias derating and temperature.

## 8. Control architectures

### 8.1 Voltage mode
Compare `V_out` to a reference; the error drives duty cycle directly against a fixed
sawtooth. The plant is a second-order LC filter: a **complex pole pair** at
`f_0 = 1/(2π√(LC))` with a −180° phase drop, plus the ESR zero. Needs a **Type III**
compensator (3 poles, 2 zeros) to claw back the phase. Simple silicon, complicated
compensation, and no inherent current limiting.

### 8.2 Peak current mode
Inner loop regulates the *peak* inductor current cycle by cycle; the voltage loop
commands that peak. The inductor now behaves like a current source, so the LC double
pole **degenerates into a single pole** — the plant looks first-order and a **Type II**
compensator suffices. You get cycle-by-cycle current limit for free. Downsides: needs
slope compensation above D = 0.5 to avoid subharmonic oscillation, is noise-sensitive
(you are comparing against a small ramp), and has a minimum on-time from leading-edge
blanking.

### 8.3 Average current mode — *what the TPS55288 uses*
Same idea, but the inner loop regulates the **average** inductor current using a
current-error amplifier with its own compensation, rather than comparing an
instantaneous peak. Consequences:

- Much better noise immunity (you're filtering, not sampling a peak).
- No slope-compensation requirement in the peak-CM sense, and no subharmonic instability
  at high duty — but there is an equivalent constraint: **the slope of the current
  amplifier's output must not exceed the downslope of the PWM ramp**, or you get the same
  instability. Dixon's classic criterion (Unitrode U-140 / SLUP113) sets the current
  amplifier's gain at f_sw so the two slopes match.
- Accurate average current limiting, which is why the part can give you a programmable
  16 A average inductor limit.
- **This is why the TPS55288 datasheet says "the inner current loop uses internal
  compensation and requires the inductor value must be larger than 1.2/f_sw".** The
  internal current-amplifier compensation is fixed, so the inductor's current slope
  (`V/L`) must stay within the range that fixed compensation was designed for. Too small
  an inductance and the current ramp is too steep — the loop misbehaves. **That
  constraint is a hard, non-negotiable coupling between L and f_sw.**
- To the outer voltage loop, the closed current loop looks like a transconductance:
  `I_L = g_m,PS · V_comp`. The TI spreadsheet calls this `gm_PS` and puts it at 18.2 S.

### 8.4 Hysteretic / constant-on-time
No compensator at all — a comparator with hysteresis. Superb transient response, trivial
to make stable, but the frequency is not fixed, which usually disqualifies it where EMI
matters.

## 9. The small-signal picture

What the outer voltage loop sees, in current-mode control:

**Buck:**
```
  f_p   = 1 / (2π · R_load · C_out)        single pole (load pole)
  f_ESR = 1 / (2π · R_ESR · C_out)         zero from output-cap ESR
```
Well behaved. Phase never gets near −180° from the plant alone.

**Boost (and buck-boost):**
```
  f_p    = 2 / (2π · R_load · C_out)
  f_ESR  = 1 / (2π · R_ESR · C_out)
  f_RHPZ = R_load · (1−D)² / (2π · L)      ◄── the problem
```

### The right-half-plane zero
A RHP zero **adds gain like a zero but subtracts phase like a pole** — the worst of both.
You cannot compensate it away; the only thing you can do is **cross over well below it**.
The universal rule is:

```
        f_c ≤ min( f_sw / 10 ,  f_RHPZ / 5 )      (some houses use /10 on the RHPZ)
```

Note what `f_RHPZ` depends on: it falls with **increasing load** (R_load down), with
**increasing duty** (deep boost), and with **increasing L**. So the worst case is
*minimum V_in, maximum load*. That is the corner you must design the loop at.

### The ESR zero
Historically the ESR zero of an electrolytic output capacitor provided free phase boost
near crossover, and many compensator designs quietly rely on it. **Move to all-ceramic
output capacitance and that zero jumps from a few kHz to several MHz and disappears from
your loop.** If you inherited a compensation network from a design that had bulk
capacitance, this is a common way to lose 20–30° of phase margin without changing a
single compensation component.

## 10. Type II compensation, concretely

For a transconductance error amplifier (which is what you have) with `R_C`, `C_C` in
series to ground and `C_P` in parallel:

```
  pole at origin (integrator)      → zero DC error
  f_z    = 1 / (2π · R_C · C_C)    → phase boost, place at/below f_c
  f_p2   = 1 / (2π · R_C · C_P)    → high-frequency pole, place between f_c and f_sw
```

Standard placement:
- Choose `f_c` from the rule above.
- `R_C` sets the mid-band gain and therefore `f_c`.
- Place `f_z` at or below the load pole (commonly `f_c/5` to `f_c/10`) so the phase has
  recovered by crossover.
- Place `f_p2` on top of whichever is lower — the ESR zero or the RHPZ — to kill the
  gain there, and to attenuate switching ripple.

The TPS55288 datasheet gives these directly (Eq. 24–26):
```
  R_C = 2π · V_out · R_SENSE · C_out · f_c / [ (1−D) · V_REF · G_EA ]
  C_C = R_load · C_out / (2 · R_C)
  C_P = R_ESR · C_out / R_C          (leave open if < 10 pF)
```
Every one of those has `C_out` in it. **If your real C_out is not the C_out you typed
into the spreadsheet, your compensation is not what you think it is.**

---
---

# PART II — CHOOSING THE COMPONENTS

## 0. Do it in this order

The decisions are coupled, and getting the order wrong is the single most common way a
design goes sideways. This sequence minimises backtracking:

```
 1. Specification (line, load, ripple, transient, environment)
 2. Topology / controller  ◄── the most consequential choice, and the one people skip
 3. Switching frequency
 4. Inductor
 5. Output capacitor
 6. Input capacitor
 7. Power switches
 8. Gate-drive network + bootstrap
 9. Bias (VCC) supply
10. Current sensing
11. Compensation
12. Enable / UVLO
13. Protection and fusing
14. Layout                 ◄── not an afterthought; it is a component
15. Derating and margin review
```

Steps 3–5 iterate: frequency sets inductance, inductance sets ripple, ripple sets
capacitance, and the controller may constrain all three.

---

## 1. Specification

Write these down before anything else. Every later equation consumes one of them.

| Item | Why it matters |
|---|---|
| V_in min / nom / max | min sets duty limits & boost stress; max sets device voltage rating |
| V_out and range | sets duty; a *programmable* output means designing for the worst point, not the nominal |
| I_out max, and the load's *character* | resistive? motor? pulsed? a motor load has a periodic current draw the loop must follow |
| Output ripple allowed | sets C_out (and the ESR of it) |
| Load transient (ΔI, dI/dt, allowed ΔV) | usually sets C_out harder than ripple does |
| Ambient / thermal path | in **vacuum there is no convection** — every watt must conduct into copper and radiate |
| EMI constraints | may fix f_sw, or force spread spectrum / shielded inductors |
| Efficiency target | tells you how hard to fight the load-independent losses |
| Reliability class | derating rules, single-point-failure tolerance, part qualification |

**The most under-specified item is almost always the load transient**, and the most
under-considered is the *character* of the load.

---

## 2. Topology and controller — the choice that dominates everything

Two questions, in order:

**(a) Does V_in ever go below V_out?**
- Never → **buck**. Simplest, cheapest, most efficient, two switches.
- Always → **boost**.
- Sometimes → you need buck-boost. Four-switch non-inverting is the modern answer.

A four-switch buck-boost costs you: two extra switches, a right-half-plane zero, a mode
transition to get right, roughly double the switching loss in the overlap region, and a
much harder layout. **Do not pay that if V_in never drops below V_out.** This sounds
obvious and is skipped constantly, usually because a part with the right feature set
(here, I²C output programming) happens to be a buck-boost.

**(b) Is the converter sized for the load?**
A converter rated for 16 A driving 0.5 A is not "extra margin" — it is a different
design point, and mostly a worse one:

| Effect of oversizing | Consequence |
|---|---|
| Big FETs → big Q_g, big C_oss | load-independent losses stay high at light load |
| Big current limits | protection thresholds you cannot set low enough to be useful |
| Constrained inductance range | you may be unable to get sensible ripple at light load |
| Big bias current | the internal LDO becomes a bottleneck |
| Big package | the thermal path has to carry losses you didn't need to create |

The rule of thumb: **pick a converter whose rated current is roughly 1.5–3× your maximum
load**, not 30×. If the only part with the feature you need is grossly oversized,
consider getting the feature a different way (e.g. a fixed buck with a digital
potentiometer in its feedback divider, rather than an I²C converter).

---

## 3. Switching frequency

Almost everything trades against f_sw:

| Increasing f_sw… | Effect |
|---|---|
| Inductor and capacitor size | **smaller** (good) |
| Ripple current for a given L | **smaller** (good) |
| Loop bandwidth achievable | **higher** (good) |
| Switching, C_oss, Q_rr, gate losses | **linearly higher** (bad) |
| Bias supply current | **linearly higher** (bad, and often the hard limit) |
| Duty-cycle range usable (t_on,min / t_off,min) | **narrower** (bad) |
| EMI fundamental | moves **up** — may be good or bad depending on what you're protecting |

**Constraints that set hard limits:**

1. **Minimum on-time.** `D_min = V_out/V_in` must satisfy `D_min·T > t_on,min`, so
   ```
   f_sw < V_out / (V_in · t_on,min)
   ```
2. **Minimum off-time** (symmetric constraint at high duty). Often unpublished for the
   buck leg — check it empirically.
3. **Bias current.** `I_bias ≈ ΣQ_g · f_sw`. If the controller's internal LDO is rated
   60 mA and your gates need 45 mA, you have no margin.
4. **Inductor SRF.** Keep `f_sw` at least ~10× below the inductor's self-resonance.
5. **The controller's own limits**, including any `L > k/f_sw` requirement from an
   internal current-loop compensation.

**Where EMI enters.** If you are powering a sensitive instrument, you may deliberately
place `f_sw` *above* the victim's band so that neither the fundamental nor its low
harmonics land in it. That is a legitimate reason to run high, and it should be written
down in the design record — otherwise the next reviewer (me, last week) reads it as a
mistake.

---

## 4. Inductor

### What it does
Stores energy and limits `di/dt`. Its value sets ripple current, which propagates into
almost every other choice.

### Sizing
Pick a target ripple ratio `k = ΔI_pp / I_out,max`, conventionally **0.2–0.4**.

```
Buck:   L = (V_in,max − V_out)·V_out / (ΔI_pp · f_sw · V_in,max)
Boost:  L = V_in·(V_out,max − V_in) / (ΔI_pp · f_sw · V_out,max)
```
Evaluate both for a buck-boost and take the larger. Worst case is at
`V_out = V_in/2` (buck) and `V_in = V_out/2` (boost).

**Why 0.2–0.4 and not less?**
- Smaller ripple → lower RMS current, lower core loss, lower output ripple.
- But bigger, heavier, more expensive inductor; slower transient response (the inductor
  resists the current change you want); and in current-mode control the current-sense
  signal gets small, hurting noise immunity.
- And, per §4 of Part I, some ripple can buy you ZVS at light load.

**Why not more?** Peak current rises, saturation margin shrinks, output ripple grows,
core loss grows, and the switches commutate more current than the load needs.

### Ratings — read these carefully, they are not interchangeable

| Rating | Means | Failure if exceeded |
|---|---|---|
| **I_sat** (usually at 20 % or 30 % inductance drop) | magnetic saturation | inductance collapses, current runs away, control loop loses authority. **Catastrophic and fast.** |
| **I_rms** (at 20 °C or 40 °C rise) | self-heating from DCR + core loss | thermal, gradual |
| **DCR** | copper resistance | efficiency, heat |
| **SRF** | parasitic-capacitance resonance | above it the "inductor" is a capacitor |

Rule: `I_sat ≥ 1.3 × I_L,peak` **at the worst-case corner**, where
`I_L,peak = I_L,DC + ΔI/2`, and for a boost `I_L,DC = I_out·V_out/(V_in·η)`.
Check I_sat **hot** — saturation current falls with temperature in ferrites.

Also confirm `I_sat` exceeds the converter's own **peak current limit**. If the IC will
push 25 A before it protects, and the inductor saturates at 17 A, the protection is
downstream of the failure.

### Core material and loss
- **Ferrite**: low loss, but a sharp saturation knee — inductance falls off a cliff.
- **Composite / molded powder** (Coilcraft XAL, Vishay IHLP): soft saturation, higher
  core loss, mechanically robust. Usually the right choice for wide-range converters.
- Core loss ≈ `k·f^a·ΔB^b` with `b ≈ 2–2.7`, so it is driven hard by **ripple**, not by
  DC current. Doubling ripple can quintuple core loss.

### Shielding
Shielded/molded parts contain the flux. For a magnetically sensitive payload this is
not optional.

### Common mistakes
- Using the I_rms rating as if it were I_sat.
- Using the datasheet DCR of the wrong inductance value in the family.
- Ignoring the derating of I_sat at temperature.
- Choosing L from ripple alone when the controller imposes its own `L` range.

---

## 5. Output capacitor

### What it does
Three separate jobs, and usually a *different* one dominates than you expect:
1. Absorbs the AC component of the inductor/switch current → sets ripple voltage.
2. Supplies the load during a transient before the loop responds → sets transient droop.
3. Forms the plant's dominant pole → sets loop dynamics.

### Ripple sizing
```
Buck (capacitive term):   ΔV_C = ΔI_pp / (8 · C_out · f_sw)
Boost (capacitive term):  ΔV_C = I_out·(1 − V_in/V_out) / (C_out · f_sw)
ESR term (both):          ΔV_ESR = ΔI_pp · R_ESR      (buck)
                          ΔV_ESR = (I_out·V_out/V_in) · R_ESR   (boost)
```
Add them (pessimistically) or RSS them (realistically).

### Transient sizing — usually the binding constraint
For a load step ΔI, before the loop reacts the capacitor alone supplies it:
```
        C_out ≥ ΔI / (2π · f_c · ΔV_allowed)
```
This is often 5–10× what the ripple calculation asks for.

### RMS current
Boost mode is brutal: `I_Cout(RMS) = I_out·√(V_out/V_in − 1)`. Ceramics handle this
easily; electrolytics may not.

### The DC-bias problem (this catches everyone)
Class-II ceramics (X5R, X7R) lose capacitance with applied DC voltage, and the loss is
severe. A 10 µF 50 V X7R in 1206 at 24 V bias can be **30–50 % of its nominal value**.
Smaller packages are worse; higher voltage ratings in the same package are better.
Rules:
- Always use the manufacturer's **capacitance vs DC bias** curve, never the marked value.
- Prefer a **larger case size** or a **higher voltage rating** for the same capacitance.
- Class-II ceramics also lose capacitance with **age** (a few % per decade-hour) and vary
  with temperature.
- C0G/NP0 has essentially no bias or temperature dependence but is only available at
  small values — use it for compensation networks, never rely on X7R there.

### Mixing bulk and ceramic
The classic arrangement is a bulk polymer/electrolytic for energy storage and the loop's
ESR zero, plus ceramics for high-frequency decoupling. If you delete the bulk part,
you delete the ESR zero and you change the plant. **A design change from
"bulk + ceramic" to "ceramic only" is a loop change, not a BOM change.**

### Piezoelectric and microphonic effects
Class-II ceramics are piezoelectric — they sing, and they also generate charge when
mechanically excited. Next to a Stirling compressor, this is worth a thought.

---

## 6. Input capacitor

### What it does
Supplies the chopped input current locally so the supply lead doesn't have to. In a buck
this is the **hardest-working capacitor in the converter**.

```
Buck:  I_Cin(RMS) = I_out · √( V_out·(V_in − V_out) ) / V_in
       maximised at V_out = V_in/2, where I_Cin(RMS) = I_out/2
Boost: I_Cin(RMS) = ΔI_pp / √12      (much gentler — input current is continuous)
```

### Sizing
```
        C_in ≥ I_out · D · (1−D) / (ΔV_in · f_sw)
```
Then check RMS-current rating and ESR-driven ripple.

### Placement matters more than value
The high-frequency input capacitor is part of **commutation loop #1**. Its physical
position relative to the high-side FET's drain and the low-side FET's source determines
the loop inductance, which determines the switch-node overshoot and the radiated EMI.
A perfect 22 µF placed 10 mm away is worse than a 1 µF placed 1 mm away for that job.
Use both: small ceramics tight to the FETs, bulk further out.

### Bulk capacitor and the input-filter interaction
A switching converter presents **negative incremental input impedance** (constant power:
if V goes up, I goes down). If your input source has significant inductance (long
harness — think a satellite bus), the source inductance and the input capacitance form a
resonant tank that the negative resistance can drive unstable. This is the
**Middlebrook criterion**: the source output impedance must stay well below the
converter's input impedance across frequency. The practical fix is a bulk capacitor with
**some** ESR (electrolytic/polymer) to damp the tank — which is a second, independent
reason not to go all-ceramic on the input.

### Derating
For aluminium electrolytic and polymer hybrids, hi-rel practice derates voltage to
**60–80 %** of rating (NASA EEE-INST-002 / ECSS-Q-ST-30-11 depending on grade). Ceramics
are typically derated to **50–60 %** of rating for voltage, partly for reliability and
partly because you lose so much capacitance near the rating anyway.

---

## 7. Power switches

### Step 1 — Voltage rating
`V_DS` must exceed the maximum node voltage **plus the switching overshoot**, which is
set by loop inductance and can be 30–50 % of V_in on a poor layout. Then derate:
- Commercial practice: `V_DS ≥ 1.3 × V_max`
- Hi-rel / space: typically **≤ 75 % of rating in steady state**, i.e. `V_DS ≥ 1.33 × V_max`,
  and no transient above rating at all.

### Step 2 — The R_DS(on) vs Q_g trade
These two pull in opposite directions. Bigger die → lower `R_DS(on)`, but proportionally
higher `Q_g`, `C_oss` and `C_rss`.

```
        P_cond  ∝ I²·R_DS(on)          (load-dependent)
        P_sw    ∝ V·I·(t_r+t_f)·f      (t_r,t_f ∝ Q_gd)
        P_coss  ∝ C_oss·V²·f           (load-INdependent)
        P_gate  ∝ Q_g·V_drive·f        (load-INdependent)
```
The **figure of merit** `FOM = R_DS(on) × Q_g` measures the technology; within a family
you then choose *where on the curve* to sit based on your current.

**The optimum die size is the one where conduction loss ≈ switching loss.** Below that
current, a smaller FET is strictly better. This is worth doing explicitly:

```
   I_crossover ≈ √[ (C_oss·V² + Q_g·V_drive) · f_sw / (R_DS(on)·D) ]
```
If your actual current is well below `I_crossover`, you are on the wrong side of the
curve and you should pick a **smaller, higher-R_DS(on)** part.

### Step 3 — Gate threshold and drive voltage
- **Logic level** parts are characterised at `V_GS = 4.5 V`; **standard level** at 10 V.
  Driving a standard-level part from a 5 V rail puts it in the linear region.
- Check `V_GS(th)` **minimum**, not typical — a low minimum threshold makes the part more
  susceptible to dV/dt turn-on.
- Check `V_GS` absolute maximum against ringing on the gate, not just the DC drive level.

### Step 4 — dV/dt-induced turn-on immunity
When the high-side FET turns on, the switch node slews fast and injects current through
the low-side FET's `C_gd` into its gate. If the resulting bump exceeds `V_GS(th)`, the
low-side FET partially turns on → shoot-through.

Infineon's analysis gives, in the fast-transient limit:
```
        V_GS,induced ≈ V_in · C_gd / (C_gd + C_gs)
```
and with finite gate impedance:
```
        V_GS,induced ≈ R_total · C_gd · dV/dt
```
The device-level immunity criterion is the charge ratio:
```
        Q_gd / Q_gs1 ≤ 1
```
(`Q_gs1` is the gate charge up to threshold, roughly 50–60 % of `Q_gs`.) Many modern
low-R_DS(on) parts fail this criterion and rely on a low-impedance gate drive to stay
safe — which means **the layout is what makes them safe**, not the datasheet.

Mitigations, in order of preference:
1. Pick a part with a low `Q_gd/Q_gs1`.
2. Keep the gate loop tiny and the pull-down impedance low.
3. Asymmetric gate drive: series resistor for turn-**on**, Schottky bypass for fast
   turn-**off**.
4. Negative gate bias (AC-coupled gate drive) — rarely needed at these voltages.

### Step 5 — Body diode and Q_rr
In a hard-switched synchronous converter the low-side body diode conducts during dead
time and then reverse-recovers, dumping `Q_rr·V_in·f_sw`. Trench MOSFETs vary a lot
here. If the converter achieves ZVS (§4 of Part I) this term disappears.

### Step 6 — Thermal
`R_θJA` on a datasheet is measured on a specified copper area — usually 1 in² of 2 oz.
Your actual number depends on your pour. In **vacuum**, convection is zero: the only
paths are conduction into the board and radiation, so a datasheet number derived in
still air is optimistic in a way that is easy to forget.

### Common mistakes
- Choosing the lowest `R_DS(on)` available. At light load this is *worse*.
- Using a standard-level FET on a 5 V gate drive.
- Ignoring `C_oss` because it doesn't appear in the "conduction loss" column.
- Forgetting that `Q_g` sets the bias-supply current.

---

## 8. Gate drive network

### Driver strength
Peak current `I_drive ≈ (V_drive − V_plateau) / (R_drv + R_g + R_g,int)`. Transition
time `t ≈ Q_gd / I_drive`. Faster is more efficient but generates more `dV/dt` and more
ringing, and demands a better layout.

### Gate resistor
Sets the trade between switching loss and EMI/ringing. Typical 1–10 Ω.
**Its physical position is not negotiable: it belongs at the MOSFET's gate pad**, so
that its damping acts on the loop that includes the gate-source capacitance and the
trace inductance. Placed at the driver end, it damps the wrong thing.

### The gate loop
This is a real circuit with real inductance:
```
  driver output → R_g → gate → channel → source → back to the driver's reference
```
For the **high-side** driver the reference is the switch node, so the return path is
from the FET's **source pin** to the controller's `SW` pin. This must be a **Kelvin**
connection — a dedicated short trace paired with the gate trace, not a trip through the
power pour. Common-source inductance (inductance shared between the gate loop and the
power loop) directly opposes the gate drive during switching and slows turn-off.

Rules of thumb: gate and gate-return routed as a pair, loop area minimised, total path
of order a few millimetres, and the two halves of a half-bridge routed **symmetrically**
so the controller's dead time means the same thing on both sides.

### Bootstrap capacitor
The high-side driver floats on the switch node and is powered by `C_boot` between BOOT
and SW, refreshed from VCC through a diode when the low-side FET is on.
```
        ΔV_boot = Q_g / C_boot        → keep well under ~0.3 V
        C_boot ≥ 10 × C_iss  is a reasonable floor; 0.1 µF is typical
```
Also check there is **enough off-time to refresh it** at your maximum duty cycle. This
is why very high duty at very high frequency is dangerous: 89 ns of off-time is not much
refresh window.

### Dead time
If adjustable, set it as short as you can without cross-conduction, and verify on a
scope. If fixed, your layout must satisfy the assumption it was designed under.

---

## 9. Bias (VCC) supply

Almost always an internal LDO. Two independent things to check:

**(a) Current.**
```
        I_VCC ≈ Σ Q_g · f_sw  +  I_control  +  I_pullups  +  I_external_loads
```
Compare with the LDO's rating. Gate charge is the dominant term and scales with
frequency, so this is a frequency limit in disguise.

**(b) Dissipation.**
```
        P_LDO = (V_source − V_VCC) · I_VCC
```
dissipated **inside the controller package**, adding directly to its junction
temperature. At high input voltage this can exceed all the switching losses. Many
controllers let you feed VCC from an external 5 V rail precisely to escape this — take
that option if a rail exists.

Decoupling: the VCC capacitor is the source of the low-side gate drive's peak current.
It must be **at the pin**, and its ground must return to the controller's power ground
with low impedance.

---

## 10. Current sensing

### Shunt selection
```
        R_sense = V_sense,full-scale / I_limit
```
Two competing pressures: larger `R_sense` gives better resolution and noise immunity;
smaller wastes less power (`I²R`). Aim to use **most of the sense amplifier's full-scale
range** at your maximum current — if you use 10 % of it, you have thrown away 20 dB of
signal-to-noise and your current limit resolution is ten times coarser than the datasheet
suggests.

### Routing
- **Kelvin connections** at the shunt pads: sense the resistor element, not the solder
  joints or the trace.
- Route the pair **tightly coupled** all the way to the IC so common-mode noise cancels.
- Add a differential filter (series R + differential C) at the IC.
- Keep the pair away from the switch node.

### Shunt physics
Watch the temperature coefficient (a 100 ppm/°C shunt drifts 1 % over 100 °C), the
parasitic inductance (metal-element shunts have some; it appears as a spike at each
edge), and the power rating at the *peak* current, not the average.

---

## 11. Compensation

### Procedure
1. Identify the **worst-case corner**: for a boost-capable topology that is minimum V_in,
   maximum load, because that minimises `f_RHPZ`.
2. Compute the plant poles/zeros there, using **derated, effective** capacitance.
3. Choose `f_c ≤ min(f_sw/10, f_RHPZ/5)`.
4. Set `R_C` for that crossover.
5. Place `f_z` at `f_c/5` … `f_c/10` (or on the load pole).
6. Place `f_p2` on the lower of the ESR zero and the RHPZ.
7. **Verify across the whole operating envelope**, not just the nominal point — plot
   gain and phase at min/max V_in, min/max load, and in both buck and boost mode.
8. **Measure it.** A network analyser injecting across a series resistor in the feedback
   path is the only way to know. A load-step test with a scope is a decent proxy: count
   the overshoot rings. One overshoot and done ≈ 60°; several rings ≈ marginal.

### What breaks compensation after the fact
- Ceramic DC-bias derating (your `C_out` is half what you specified).
- Deleting a bulk capacitor (you lose the ESR zero).
- A load that turns out to be a constant-power or motor load rather than resistive.
- Temperature and ageing of Class-II ceramics.
- Changing the switching frequency without revisiting `f_c`.

**Use C0G/NP0 for `C_C` and `C_P`.** Compensating a loop with X7R is compensating with
a component whose value you don't know.

---

## 12. Enable / UVLO

For a divider from V_in to a comparator with threshold `V_th` and hysteresis current
`I_hys` out of the pin:
```
        V_in(rising)  = V_th · (1 + R_top/R_bot)
        ΔV_in(hyst)   = I_hys · R_top
```
Design rules:
- Set the rising threshold with real margin below your minimum bus voltage, accounting
  for harness drop during the converter's own inrush.
- **Make the hysteresis large enough that bus sag under load cannot cause chatter.**
  Restart cycling into a heavy load is a good way to destroy things.
- Put a capacitor on the node. It is high-impedance and it is a comparator input.
- Keep the divider **at the pin**, not across the board.
- Consider the standing current the divider burns — on a satellite it never stops.
- Bring a **hardware enable** out where a supervisor can reach it. A converter you can
  only disable over a serial bus is a converter you cannot disable when the bus is wedged.

---

## 13. Protection and fusing

Set thresholds relative to **your** load, not the silicon's capability:

| Protection | Set to | Common mistake |
|---|---|---|
| Peak / cycle-by-cycle current limit | above worst-case peak inductor current, below inductor I_sat | leaving it at the IC's maximum, so the inductor saturates first |
| Average current limit | ~1.5–2× max operating current | ditto |
| Output current limit | ~1.3–1.5× max load | ditto |
| OVP | above worst-case transient overshoot | tripping on normal load steps because C_out is too small |
| Input fuse | ~2× max steady input current, with I²t above the inrush | a 10× fuse that protects nothing |
| Hiccup / retry | enabled | latch-off on a payload you can't power-cycle |

A one-shot fuse on an unserviceable payload is a permanent single-point failure. Prefer
electronic current limiting with recoverable hiccup, and use the fuse only as the
last-ditch fire barrier it actually is.

---

## 14. Snubbers

Only if you need them. An RC snubber across the switch node damps the ringing caused by
the loop inductance resonating with `C_oss`. Procedure: measure the ring frequency `f_0`;
add capacitance until it halves (giving you `C_par = C_add/3` and `L_par`); then
`R = √(L_par/C_par)` and `C_snub ≈ 3–4 × C_par`. It costs `C·V²·f` in dissipation.

**A snubber is a patch for loop inductance.** Fix the layout first.

---

## 15. Layout is a component

Three loops, in priority order:

**Loop 1 — input commutation loop** (`C_in` → high-side drain → switch node →
low-side source → back to `C_in`). Highest `di/dt`. Minimise **enclosed area**, and give
it an uninterrupted ground plane immediately beneath so the return current mirrors under
the forward path.

**Loop 2 — output commutation loop** (boost side). Same treatment.

**Loops 3 & 4 — gate loops.** Discussed in §8. Short, paired, symmetric, Kelvin-returned.

**The switch node.** High `dV/dt`. Make it **just big enough** to carry the current and
spread the FETs' heat, and no bigger — every extra mm² is a capacitively-coupled EMI
antenna.

**Grounds.** Separate AGND (references, feedback, compensation) from PGND (power return),
joined at a single defined point — usually at the VCC capacitor's ground terminal.

**Planes and thermal.** A solid ground plane directly under the power stage is the single
highest-value layout feature. Use plane layers for planes, not for routing signals through
them. Thermal vias in **arrays**, not singly: one 0.15 mm-drill via is ~290 K/W, sixteen
in parallel is ~18 K/W. For packages with no exposed pad, the pins are the *only* heat
path — treat them accordingly.

---

## 16. Derating and margin review

The last step. Go through the BOM and check every part against its rating at the worst
case corner, hot:

- Capacitor voltage: ceramics ≤ 50–60 % of rating; electrolytic/polymer ≤ 60–80 %.
- MOSFET `V_DS` ≤ 75 % including overshoot; `V_GS` including ringing.
- Inductor `I_sat` ≥ 1.3 × peak, hot.
- Resistor power ≤ 50 % of rating; resistor **voltage** rating on high-value dividers.
- Junction temperatures with a realistic `R_θJA` for **your** board — and with
  **zero convection** if it flies.
- Every part's temperature range against the actual mission range.

---
---

# PART III — RUNNING THE PROCEDURE ON V4

## 1. The specification, written out

| Item | Value | Source |
|---|---|---|
| V_in | 24 V nominal; UVLO set at 20.23 V | spreadsheet C14/C15; R4/R5 |
| V_out | 12 V default, 17 V and 20 V commanded | DarkNESS paper §6.1 |
| I_out | ~0.42 A @ 12 V (<5 W), ~0.6 A @ 17 V (10 W peak) | paper §6.1 |
| Load character | Stirling compressor — periodic draw at compressor frequency, plus start-up inrush | — |
| Environment | vacuum, no convection; adjacent to a single-electron CCD readout | paper §6 |
| EMI | payload is a skipper-CCD instrument | paper |
| Class | flight, unserviceable | — |

Two things are missing from this list and both matter:
**(a) the actual bus voltage tolerance** (is it a firm 24 V, or can it sag toward 20 V?),
and **(b) the load transient specification** (what does the compressor's current
waveform look like, and what output droop can it tolerate?).

---

## 2. Step 2 — topology and controller: this is where the design was decided

### 2a. Do you need buck-boost at all?

`V_out,max = 20 V`. A synchronous buck can deliver that from 24 V at D = 0.833 with no
difficulty. It only fails if the bus sags to where D approaches 1.

| Bus voltage | D at V_out = 20 V | t_off at 400 kHz | Verdict |
|---|---|---|---|
| 25.2 V (+5 %) | 0.794 | 515 ns | fine |
| 24.0 V | 0.833 | 417 ns | fine |
| 22.8 V (−5 %) | 0.877 | 307 ns | fine |
| 21.0 V | 0.952 | 119 ns | marginal |
| 20.2 V (your UVLO) | 0.990 | 25 ns | **impossible** |

**So: if the bus is a firm 24 V ± 5 %, you do not need a buck-boost.** You are paying for
two extra switches, a right-half-plane zero, a mode-transition problem, roughly double
the switching loss in the overlap region, and a much harder layout — for a corner you
have told the board (via the UVLO) not to operate in anyway.

If the bus genuinely can approach 20 V, then the buck-boost is justified — but then your
UVLO at 20.23 V is set exactly at the point where a buck would fail and a buck-boost is
still fine, which is a strange place to put it.

**This is the single question I would answer before designing V5.**

### 2b. Is the converter sized for the load?

| | TPS55288 | Your load | Ratio |
|---|---|---|---|
| Rated output current | 16 A inductor / 6.35 A output | 0.6 A | **10–27×** |
| Rated power | 100 W from 12 V | 10 W | 10× |
| Internal FETs | 7.1 / 7.6 mΩ | needs ~200 mΩ | ~30× |
| External FETs chosen | 40 A / 4.8 mΩ | needs ~50 mΩ | ~65× |

Per Part II §2, everything downstream inherits this. Watch how it propagates:

```
 16 A converter
   ├─► big internal FETs        → large C_oss and Q_g the load never needs
   ├─► inductance range capped at 13 uH  → cannot get low ripple at 0.6 A
   │      └─► forces f_sw up to ~1.9 MHz  → forces bias current up to ~45 mA
   │             └─► against a 60 mA LDO  → no margin
   ├─► ILIM floor of 3.3 A      → cannot protect a 0.6 A load
   ├─► 10 mΩ sense from the EVM → 6 mV of a 63.5 mV scale used
   └─► 40 A external FETs       → optimum current 5.3 A, actual 0.6 A
```

Nearly every specific finding in my first review is a symptom of this one root cause.

---

## 3. Step 3 — frequency: **I owe you a correction here**

In the first review I said 1.88 MHz was 4.7× the EVM and criticised it against TI's
"stay below 500 kHz for high power" guidance. Running the procedure properly shows that
was too glib. Here are the three binding constraints:

| Constraint | Limit | Direction |
|---|---|---|
| Minimum off-time at V_out = 20 V (t_off,min ≈ 145 ns) | **f_sw < 1.15 MHz** | upper bound |
| VCC bias current with 12 nC gates and a 40 mA budget | **f_sw < 1.67 MHz** | upper bound |
| Getting 40 % ripple at 0.6 A with the IC's maximum 13 µH | **f_sw > 1.92 MHz** | **lower** bound |

**These do not intersect.** There is no switching frequency at which this IC, with these
FETs, gives you conventional ripple *and* respectable off-time margin *and* a bias
current the LDO can supply. Your choice of 1.88 MHz satisfies the ripple constraint
essentially exactly — you optimised the one that a design-by-the-book procedure puts
first, and the other two are what broke.

That is not a mistake in frequency selection. **It is the part being wrong for the load,
showing up as an unsatisfiable frequency constraint.** I should have framed it that way
the first time.

### And there is a further twist: at 400 kHz the large ripple buys you ZVS

If you relax the "30–40 % ripple" guideline — which, per Part II §4, is a guideline and
not a law — 400 kHz is not merely acceptable, it is **better**:

At V_in = 24 V, V_out = 12 V, I_out = 0.42 A, L = 10 µH:

| | 400 kHz | 700 kHz | 1.88 MHz |
|---|---|---|---|
| ΔI_pp | 1500 mA | 857 mA | 319 mA |
| I_L max / min | +1.17 / **−0.33 A** | +0.85 / −0.01 A | +0.58 / +0.26 A |
| ZVS at Q1 turn-on? | **YES** | no | no |
| Q1 turn-off loss | 51 mW | 64 mW | 118 mW |
| Q1 turn-on loss | **0** | 0 | 53 mW |
| C_oss loss | **0** (recycled) | 121 mW | 325 mW |
| Q_rr loss | **0** (no diode conduction) | 0 | 225 mW |
| Conduction | 2.4 mW | 1.6 mW | 1.2 mW |
| **Total in Q1 + Q2** | **53 mW** | 187 mW | **721 mW** |
| VCC gate current | 9.6 mA | 16.8 mA | 45.1 mA |

The ZVS condition is `|I_L,min| > V_in·√(C_oss,tot/L)` = 0.186 A. At 400 kHz the reverse
current is 0.33 A, comfortably above it; the inductor swings the switch node back up to
V_in before Q1 turns on, so turn-on loss, C_oss loss and body-diode reverse recovery all
vanish. The cost is 21 mV of extra output ripple (checked below) and a little more core
loss.

**And the output ripple penalty is negligible:**

| | ΔI_pp | ΔV_out (capacitive term, as-built C_out) |
|---|---|---|
| V_out = 12 V, 400 kHz | 1500 mA | **21 mV** |
| V_out = 12 V, 1.88 MHz | 319 mA | 1.0 mV |
| V_out = 20 V, 400 kHz | 833 mA | **15 mV** |
| V_out = 20 V, 1.88 MHz | 177 mA | 0.7 mV |

21 mV of ripple on a 12 V rail feeding a cryocooler motor controller is a non-issue.

### Which makes the bench observation genuinely strange

The model says moving from 1.88 MHz to 400 kHz should have cut the FET dissipation by
**14×** (721 mW → 53 mW), because you cross from fully hard-switched into ZVS. You
report that Q1 and Q2 are still the dominant heat source at 400 kHz.

**That gap is the finding.** It cannot be explained by conduction (2 mW), by C_oss
(recycled), by Q_rr (none), or by gate drive (that goes into the driver, not the FETs).
The mechanisms left are:

1. **Cross-conduction** — dissipates in both FETs, load-independent, scales with f_sw but
   does not disappear. Consistent with the asymmetric gate layout (§5 below).
2. **ZVS not actually being achieved** — e.g. the part is in PFM rather than FPWM (check
   MODE register 06h bit 1), in which case the low-side FET turns off at zero crossing,
   there is no reverse current, and every switching event is hard. **This is worth
   checking before anything else — it is a one-register read and it would explain the
   entire discrepancy.**
3. **Operating in buck-boost rather than buck** (STATUS register 07h bits [1:0]).
4. **Much higher current than the cryocooler's nominal draw.**

Note that (2) is an easy trap: the MODE *pin* resistor is 0 Ω, which Table 7-2 says
selects PWM. But the MODE *register* (06h) default is `00100000b`, with `MODEST = 0`
meaning "controlled by external resistor" — so it should be FPWM. Confirm rather than
assume, because if something has written `MODEST = 1` with `PFMSEL = 0`, you are in PFM
and hard-switching every cycle.

---

## 4. Steps 4–6 — the passives

### Inductor

| | Procedure says | On the board |
|---|---|---|
| Value | constrained to ≤ 13 µH by the IC; 10 µH is a sensible pick | **10 µH** ✓ |
| I_sat ≥ 1.3 × I_peak | I_peak = 1.17 A → need ≥ 1.5 A | **17.5 A** — 12× oversized |
| I_rms | need ≥ 0.6 A | **11.5 A @ 20 °C rise** |
| SRF ≥ 10 × f_sw | 4 MHz @ 400 kHz; 19 MHz @ 1.88 MHz | **11 MHz** — fine at 400 kHz, 5.9× at 1.88 MHz |
| Shielded | required next to a CCD | ✓ molded composite |

The value is right; the *part* is enormous. An 11.3 × 10 × 10 mm, ~4.5 g inductor is
sized for 17.5 A. A 4–5 mm 10 µH part rated ~2–3 A would do the same job at roughly a
tenth of the mass and volume — which on a 6U you can spend elsewhere. Also note the
inductor's `I_sat` (17.5 A) is **below** the IC's fixed 25 A peak current limit, so the
protection is downstream of the failure mode.

### Output capacitor

Transient sizing (Part II §5), for a 0.6 A step:

| Crossover | 100 mV droop | 200 mV droop |
|---|---|---|
| 10 kHz | 96 µF | 48 µF |
| 20 kHz | 48 µF | 24 µF |
| 37 kHz | 26 µF | 13 µF |

As-built effective capacitance is **18–27 µF** (4 × 10 µF + 1 µF of 50 V X7R, derated
for 12–20 V bias). That is adequate *only* if the loop really is crossing near 37 kHz —
which brings us to the loop.

### Input capacitor

`I_Cin(RMS) = I_out/2 = 0.3 A` worst case — trivial. Ripple sizing wants ≥ 7.5 µF for
50 mV; you have ~9 µF of ceramic plus the 68 µF polymer. **Correctly sized.** The only
issue remains the 35 V rating on a 24 V bus (69 % — outside hi-rel derating; the EVM's
50 V part is a drop-in and is already in your symbol library).

The polymer's ESR is also doing useful work damping the harness-inductance /
input-capacitance tank (Part II §6). Don't delete it in favour of all-ceramic.

---

## 5. Step 7–8 — switches and gate drive

### The crossover-current test

Per Part II §7, the optimum FET is the one where conduction loss ≈ switching loss:

| Device class | Optimum current @ 400 kHz | @ 1.88 MHz |
|---|---|---|
| IPZ40N04S5L-4R8 (4.8 mΩ, 40 A) | **5.3 A** | 11.5 A |
| ~30 mΩ, 5–10 A class | 1.34 A | 2.9 A |
| ~50 mΩ, 3–5 A class | **0.82 A** | 1.8 A |

Your load is **0.42–0.60 A**. The right device for this converter is a **~50 mΩ, 3–5 A
part** — roughly a tenth the die. That would cut Q_g from ~12 nC to ~2.5 nC (VCC gate
current at 1.88 MHz: 45 mA → 9 mA, removing the LDO problem entirely) and C_oss from
300 pF to ~50 pF.

The 40 A parts are on the board because they are on the EVM, and the EVM is a 5 A design.
That is a reasonable thing to inherit and a reasonable thing to now un-inherit.

### Gate drive network — the part I still think is wrong

| | Procedure says | Q1 (high side) | Q2 (low side) |
|---|---|---|---|
| R_g at the gate pad | yes | **12.0 mm away** | 3.1 mm ✓ |
| Gate loop short | a few mm | 5.8 mm F.Cu + **14.7 mm on In2 @ 6 mil + 2 vias** | 3.1 mm @ 0.3 mm ✓ |
| Kelvin source return | mandatory | **U1 pin 23 is outside the SW1 pour**; reaches Q1's source via 5.1 mm F.Cu + 13.4 mm In2 + 2 vias | plane under the pad ✓ |
| Symmetric halves | mandatory | — | **strongly asymmetric** |
| C_boot | 0.1 µF, close | 0.1 µF, 2.65 mm ✓ | — |

The dV/dt-induced-turn-on arithmetic (Part II §7) is actually reassuring for Q2:
`V_GS,induced ≈ V_in · C_gd/(C_gd + C_gs) = 24 × 27/(27+1533) = 0.42 V`, well below the
1.2 V minimum threshold, and with the finite-impedance form
`R_t · C_gd · dV/dt ≈ 4 Ω × 27 pF × 4.8 V/ns ≈ 0.52 V` — still below threshold, *because
Q2's gate loop is short*. The device-level charge ratio `Q_gd/Q_gs1 ≈ 2.3` fails
Infineon's `≤ 1` criterion, so the part is **relying on the low-impedance gate drive** to
stay safe. Q2 has that. Q1 does not.

So the mechanism I would expect is not dV/dt turn-on of Q2, but **delayed turn-off of Q1**
relative to whatever dead time the controller assumes — the controller cannot know that
one of its two gate nodes is 18 mm away through two vias. That produces exactly the
symptom you have: both FETs hot, load-independent, improved but not eliminated at
400 kHz.

---

## 6. Step 9 — bias supply

```
  I_VCC = 2 × Q_g × f_sw + I_control + I_pullups
```

| f_sw | with IPZ40N04S5L (12 nC) | with a 50 mΩ part (2.5 nC) |
|---|---|---|
| 400 kHz | 9.6 mA | 2.0 mA |
| 1.88 MHz | **45.1 mA** (75 % of the 60 mA LDO) | 9.4 mA |

And the dissipation, inside the QFN, with the LDO fed from V_out (Table 7-1):

| V_out | at 1.88 MHz | at 400 kHz |
|---|---|---|
| 12 V | 327 mW | 86 mW |
| 20 V | **712 mW** | 187 mW |

The RPM package has **no exposed thermal pad** — the pins are the only heat path — and
your PGND pads have four 0.15 mm-drill vias (≈ 73 K/W) with none at all on VOUT/ISP.
Per Part II §15, a 4 × 4 array of the same via is ≈ 18 K/W. In vacuum there is no
convection to make up the difference.

TI's own escape hatch applies here: set the MODE resistor to 51.1 kΩ to select an
external 5 V VCC (address 0x74, PWM). That removes both the current ceiling and the
dissipation, if the bus can give you a 5 V rail.

---

## 7. Step 10 — current sensing

| | Procedure says | On the board |
|---|---|---|
| Use most of full scale | R_sense = 50 mV / I_limit → **50 mΩ** for a 1 A limit | **10 mΩ** (from the EVM's 5 A design) |
| Signal at max load | ~50 mV | **6 mV of a 63.5 mV scale** |
| Kelvin, tightly-coupled pair | mandatory | ISP on a pour, **ISN alone on 9.5 mm of 6 mil inner-layer trace** |
| Differential filter at the IC | recommended | none |

You are using under 10 % of the current-monitor's range, which costs you ~20 dB of
signal-to-noise on a measurement you will want in flight, and makes the smallest settable
output current limit far coarser than the datasheet's 50 mA steps suggest.

---

## 8. Step 11 — compensation: a second correction

In the first review I said the loop was "on the conservative side." **That was wrong, and
the sign matters.**

`R_C ∝ C_out × f_c`. Your spreadsheet sized `R_C = 26.4 kΩ` (you fitted 26.1 kΩ) for
`C_out = 82 µF` (41 µF ceramic + 41 µF electrolytic) at a target `f_c = 10 kHz`. The board
has ~22 µF and no electrolytic. With `R_C` fixed, reducing `C_out` moves crossover **up**:

```
        f_c,actual ≈ 10 kHz × 82/22 ≈ 37 kHz
```

| | at f_sw = 1.88 MHz | at f_sw = 400 kHz |
|---|---|---|
| f_c / f_sw | f_sw / 50 — very comfortable | **f_sw / 10.7 — right at the guideline** |
| f_sw/2 vs the HF pole (277 kHz) | 939 kHz, above the pole → good attenuation | **200 kHz, below the pole → little attenuation** |

So **the loop is less comfortable at 400 kHz than at 1.88 MHz**, which is the opposite of
what I implied. Combined with §3, this means the frequency change you made to chase the
heating traded a loop-margin problem for a switching-loss improvement — and the heating
didn't follow. Another reason to instrument rather than iterate.

Also, per Part II §11: `C_c` is a C0G part (CGA3E2C0G1H562J080AA) ✓ and `C_p` is C0G
(CGA3E2NP01H220J080AA) ✓ — that is correct practice and worth noting as something the
design got right.

---

## 9. Steps 12–13 — enable and protection

| | Procedure says | On the board |
|---|---|---|
| UVLO threshold | real margin below V_in,min | **20.23 V** on a 24 V bus (16 % margin) |
| Hysteresis | must exceed bus sag under load | **155 mV** |
| Capacitor at the pin | yes | **none** |
| Divider at the pin | yes | **20.5 mm away**, ~1.9 kΩ source impedance |
| Hardware enable to supervisor | yes | **none** — I²C `OE` bit only |
| Average inductor limit | ~1.5–2× max operating | **16.5 A**; IC floor is 3.3 A |
| Peak inductor limit | below inductor I_sat | **25 A fixed**, vs 17.5 A I_sat |
| Output current limit | ~1.3–1.5× max load (≈0.9 A) | **5 A** |
| Fuse | ~2× steady input current (≈1 A) | **4 A** |

The IC's average-limit floor of 3.3 A means **you cannot configure this part to protect a
0.6 A load** — another consequence of §2b. The best available compromise is R_ILIM =
100 kΩ (3.3 A) plus a 50 mΩ sense resistor programmed to ~1 A, plus a 1–1.5 A fuse.

---

## 10. Summary — what the procedure would have produced

| Component | Procedure, for *this* spec | V4 as built | Gap |
|---|---|---|---|
| Topology | buck (if bus ≥ ~22 V); buck-boost only if bus can reach 20 V | four-switch buck-boost | **open question** |
| Controller | ~2 A class, programmable output | 16 A / 100 W class | **27× oversized — root cause** |
| f_sw | 400–700 kHz (with ZVS), or ~1 MHz | 1.88 MHz | forced by the IC's L limit; defensible |
| L | 10 µH, ~2–3 A, 4–5 mm | 10 µH, 17.5 A, 11 × 10 × 10 mm | value ✓, 12× oversized |
| C_out | 50–100 µF effective, bulk + ceramic | ~22 µF, ceramic only | **missing bulk** |
| C_in | ~10 µF ceramic + bulk with ESR, 50 V | ~9 µF + 68 µF **35 V** | **derating** |
| Q1/Q2 | ~50 mΩ, 3–5 A class | 4.8 mΩ, 40 A | **~10× oversized** |
| R_g placement | at each gate pad | Q2 ✓, **Q1 12 mm away** | **fix** |
| SW1 return | Kelvin to the IC | 18 mm through 2 vias | **fix** |
| VCC | external 5 V, or ≤ 10 mA of gate charge | internal LDO at 45 mA | **fix via FETs or MODE** |
| R_sense | 50 mΩ | 10 mΩ | **10 % of scale used** |
| Compensation | for the real C_out, verified across the envelope | sized for 82 µF, f_c ~3.7× high | **re-derive + measure** |
| ILIM / I_out limit | 1.5 A / 0.9 A | 16.5 A / 5 A | IC floor is 3.3 A |
| Thermal vias | arrays under PGND and VOUT | 4 × 0.15 mm on PGND, 0 on VOUT | **fix** |
| Layer 3 | VOUT or second GND plane | full-board VCC plane | **fix** |
| Fuse | 1–1.5 A | 4 A | **fix** |

## 11. What I would do next, in order

1. **Read registers 06h and 07h** on the running board. Confirm FPWM (not PFM) and Buck
   (not Buck-Boost). This is five minutes and it either explains the heating or removes
   two hypotheses. Per §3, PFM would account for the entire 14× discrepancy on its own.
2. **Measure V_in·I_in − V_out·I_out** and compare against the model: ~0.32 W at
   400 kHz/12 V, ~1.31 W at 1.88 MHz/12 V.
3. **Scope V_GS(Q1) and V_GS(Q2) differentially at the pads, on one trigger**, plus SW1.
   Look for overlap, and confirm whether the switch node is pre-charged (ZVS) before Q1
   turns on at 400 kHz.
4. **Answer the bus-tolerance question.** If the bus is a firm 24 V, seriously consider a
   plain synchronous buck for V5 — it removes the RHPZ, the mode transitions, half the
   switches, and most of this document's difficulty.
5. **Right-size the switches and, if you stay with buck-boost, the inductor.**
6. **Fix the gate layout** (R7 at Q1's gate, Kelvin SW1 return, symmetric halves).
7. **Re-derive the compensation for the real C_out** and measure the loop.

---

## References

- Texas Instruments, *TPS55288 36-V, 16-A Buck-Boost Converter with I²C Interface*, SLVSF01B
- Texas Instruments, *TPS55288EVM-045 Evaluation Module User's Guide*, SLVUBO4B
- Texas Instruments, *TPS55288 Layout Guideline*, SLVAER0B
- L. Dixon, *Average Current Mode Control of Switching Power Supplies*, Unitrode U-140
- L. Dixon, *Control Loop Cookbook*, TI/Unitrode SLUP113
- Analog Devices, *AN-149: Modeling and Loop Compensation Design of Switching Mode Power Supplies*
- T. Wu, Infineon/IR, *Cdv/dt Induced Turn-On in Synchronous Buck Regulators*
- Infineon, *IPZ40N04S5L-4R8* datasheet
- Coilcraft, *XAL1010 High Current Shielded Power Inductors*
- Analog Devices, *AD5258* datasheet
- DarkNESS instrument paper, arXiv:2505.16981
