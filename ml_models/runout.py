"""
runout.py
Debris-flow runout propagation: where material goes once a slope fails.

Replaces the D8 + fixed-buffer approach in generate_runout_and_fuse.py, which was built
on the mislabelled rasters. That script fed `DEM_filled_75.tif` in as elevation - a file
that actually holds slope in degrees - so it routed debris downhill across a slope
surface. Its deposition rule (`slope < 20` degrees) read `slope75.tif`, which never
drops below 83 degrees, so deposition could never trigger at all. Transit and deposition
extents were fixed pixel buffers (5 and 6 cells) rather than anything physical.

Two ideas replace all of that.

**Angle of reach (Fahrboeschung).** A debris flow travels until the straight line from
its source down to the flow front falls below a critical angle - equivalently, until it
has spent its potential energy against friction. Tracking an *energy height* per cell
makes this a single pass: energy gained by descending, spent at a constant rate per
metre travelled, and the flow stops where it reaches zero. Reach then follows from
terrain and friction rather than from a buffer radius chosen by eye.

**Multiple flow direction spreading.** D8 sends all material to one of eight neighbours,
which produces single-pixel threads that neither look nor behave like debris flows.
Distributing flux across all downslope neighbours, weighted by slope steepness
(Holmgren 1994), reproduces the bifurcation around spurs and the spreading on exit that
real flows show.

Both are evaluated in one descending-elevation sweep, the same ordering trick that makes
D8 accumulation exact: when a cell is processed, everything upslope of it is already
done.
"""

import numpy as np

# D8 neighbour offsets, clockwise from east, with centre-to-centre distances in cells.
NEIGHBOURS = [(0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1)]
NEIGHBOUR_DIST = np.array([1.0, np.sqrt(2), 1.0, np.sqrt(2),
                           1.0, np.sqrt(2), 1.0, np.sqrt(2)])

GRAVITY = 9.81


def propagate(dem, sources, source_strength=None, res=30.0,
              reach_angle_deg=22.0, spread_exponent=4.0, max_velocity=30.0,
              drag_length=70.0, nodata_mask=None):
    """Route debris downslope from source cells.

    Parameters
    ----------
    dem : 2-D float array
        Filled elevation in metres, on a grid of `res` metre cells.
    sources : 2-D bool array
        Cells where failure initiates.
    source_strength : 2-D float array, optional
        Relative contribution of each source, typically its susceptibility. Defaults
        to 1.0 everywhere a source exists.
    reach_angle_deg : float
        Angle of reach. Debris-flow observations cluster around 20-30 degrees for
        channelised flows; lower values travel further. 22 degrees is a common
        regional default.
    spread_exponent : float
        Holmgren exponent. 1 spreads broadly and diffusely, large values converge
        toward single-direction D8. 4 is the usual compromise for debris flows.
    drag_length : float
        Turbulent drag scale in metres: the flow sheds energy at a rate `e / drag_length`
        per metre travelled, on top of basal friction.

        Basal friction alone does not bound speed. On any slope steeper than the reach
        angle the energy line keeps gaining, and over a long descent it reaches hundreds
        of metres - implying velocities near 90 m/s, which no debris flow attains. Real
        flows lose energy to turbulence, internal deformation and bed entrainment at a
        rate that grows with speed, until that loss balances the gravitational gain.

        A hard ceiling on energy would also bound the speed, but it flattens the result:
        on Western Ghats terrain almost every cell saturates within a step or two, and
        the velocity field becomes one constant value carrying no information. The drag
        term instead gives a slope-dependent terminal energy,

            e_terminal = drag_length * (local_slope - friction_slope)

        so speed keeps varying with steepness. At 70 m a 30-degree slope settles near
        15 m/s and a 40-degree slope near 24 m/s, which brackets observed debris-flow
        velocities.
    max_velocity : float
        Hard ceiling on velocity, m/s. A guard, not the operative limit - the drag term
        should bind first.

    Returns
    -------
    dict with 'flux', 'energy_height', 'velocity', 'transit', 'deposition'.
    """
    h, w = dem.shape
    if nodata_mask is None:
        nodata_mask = ~np.isfinite(dem)
    if source_strength is None:
        source_strength = np.ones_like(dem, dtype=np.float32)

    # tan of the reach angle: metres of energy height lost per metre travelled.
    friction_slope = np.tan(np.radians(reach_angle_deg))
    # Hard ceiling on stored energy, as a last-resort guard.
    max_energy = max_velocity ** 2 / (2.0 * GRAVITY)

    z = np.where(nodata_mask, -np.inf, dem).astype(np.float64)

    flux = np.zeros((h, w), dtype=np.float64)
    energy = np.full((h, w), -1.0, dtype=np.float64)   # -1 marks "not reached"

    src_idx = sources & ~nodata_mask
    flux[src_idx] = source_strength[src_idx]
    # A failure starts at rest: its energy height is zero and grows as it descends.
    energy[src_idx] = 0.0

    # Descending elevation guarantees every upslope contributor is settled first.
    order = np.argsort(z.ravel(), kind="stable")[::-1]
    rows, cols = np.divmod(order, w)

    for i in range(len(order)):
        r, c = rows[i], cols[i]
        if energy[r, c] < 0.0 or flux[r, c] <= 0.0 or nodata_mask[r, c]:
            continue

        zc = z[r, c]
        ec = energy[r, c]
        fc = flux[r, c]

        # Collect downslope neighbours and their Holmgren weights.
        targets, weights = [], []
        for k, (dr, dc) in enumerate(NEIGHBOURS):
            nr, nc = r + dr, c + dc
            if nr < 0 or nr >= h or nc < 0 or nc >= w or nodata_mask[nr, nc]:
                continue
            drop = zc - z[nr, nc]
            if drop <= 0.0:
                continue
            travel = NEIGHBOUR_DIST[k] * res
            # Gain the drop, pay basal friction, then pay turbulent drag in proportion
            # to the energy already carried. That last term is what makes the flow
            # approach a terminal speed instead of accelerating without limit, and it
            # leaves speed varying with local steepness rather than pinned at one value:
            #     e_terminal = drag_length * (local_slope - friction_slope)
            e_next = (ec + drop - travel * friction_slope
                      - travel * ec / drag_length)
            if e_next <= 0.0:
                continue   # the flow runs out of energy before arriving
            e_next = min(e_next, max_energy)
            targets.append((nr, nc, e_next))
            weights.append((drop / travel) ** spread_exponent)

        if not targets:
            continue   # nowhere left to go: this cell is a deposition point

        total = float(sum(weights))
        if total <= 0.0:
            continue
        for (nr, nc, e_next), weight in zip(targets, weights):
            flux[nr, nc] += fc * (weight / total)
            # Keep the most energetic arrival: it sets how much further debris can go.
            if e_next > energy[nr, nc]:
                energy[nr, nc] = e_next

    reached = energy > 0.0
    # Energy height converts straight to velocity: v = sqrt(2 g h_energy).
    velocity = np.zeros((h, w), dtype=np.float32)
    velocity[reached] = np.sqrt(2.0 * GRAVITY * energy[reached])
    velocity = np.clip(velocity, 0.0, max_velocity)

    transit = reached & ~sources
    # Deposition: reached, but with no onward downslope neighbour that keeps energy.
    deposition = _deposition_cells(z, energy, nodata_mask, res, friction_slope,
                                   drag_length)
    out_energy = np.where(reached, energy, 0.0)

    out = {
        "flux": flux.astype(np.float32),
        "energy_height": out_energy.astype(np.float32),
        "velocity": velocity,
        "transit": transit,
        "deposition": deposition & reached,
    }
    for key in ("flux", "energy_height", "velocity"):
        out[key][nodata_mask] = np.nan
    return out


def _deposition_cells(z, energy, nodata_mask, res, friction_slope, drag_length):
    """Cells the flow reaches but cannot leave - where the debris comes to rest."""
    h, w = z.shape
    can_continue = np.zeros((h, w), dtype=bool)

    for k, (dr, dc) in enumerate(NEIGHBOURS):
        rs = slice(max(0, -dr), h - max(0, dr))
        cs = slice(max(0, -dc), w - max(0, dc))
        rd = slice(max(0, dr), h - max(0, -dr))
        cd = slice(max(0, dc), w - max(0, -dc))

        drop = np.full((h, w), -np.inf)
        drop[rs, cs] = z[rs, cs] - z[rd, cd]
        travel = NEIGHBOUR_DIST[k] * res

        onward = np.zeros((h, w), dtype=bool)
        with np.errstate(invalid="ignore"):
            # Same energy budget the propagation uses, drag included, so the two
            # cannot disagree about where the flow stops.
            onward[rs, cs] = (
                (drop[rs, cs] > 0)
                & (energy[rs, cs] + drop[rs, cs] - travel * friction_slope
                   - travel * energy[rs, cs] / drag_length > 0)
            )
        can_continue |= onward

    return (energy > 0.0) & ~can_continue & ~nodata_mask


def source_cells(susceptibility, threshold, slope=None, min_slope_deg=15.0):
    """Pick failure initiation cells.

    A minimum slope is applied as well as a susceptibility threshold: a flat cell with
    a high model score has nothing to shed, and seeding one produces a runout path that
    starts nowhere.
    """
    src = np.isfinite(susceptibility) & (susceptibility >= threshold)
    if slope is not None:
        src &= np.isfinite(slope) & (slope >= min_slope_deg)
    return src


def trace_paths(dem, flux, sources, energy=None, res=30.0, min_flux=0.05,
                max_steps=3000, max_paths=400, nodata_mask=None):
    """Trace representative centreline paths for vector display.

    The raster fields carry the full spreading behaviour; these lines exist so the map
    can show discrete corridors. Each follows the highest-flux downslope neighbour from
    a source, which picks out the dominant branch of the fan.

    `energy` must be supplied for the lines to agree with the physics. Following flux
    alone walks past the point where the flow has run out of energy, because flux is
    still non-zero downstream of it; corridors traced that way report reach angles
    shallower than the friction angle, which cannot happen.
    """
    h, w = dem.shape
    if nodata_mask is None:
        nodata_mask = ~np.isfinite(dem)

    srcs = np.argwhere(sources)
    if len(srcs) > max_paths:
        # Strongest sources first, so the displayed corridors are the ones that matter.
        strength = flux[sources]
        keep = np.argsort(strength)[::-1][:max_paths]
        srcs = srcs[keep]

    paths = []
    for r0, c0 in srcs:
        r, c = int(r0), int(c0)
        pts = [(r, c)]
        seen = {(r, c)}
        for _ in range(max_steps):
            best, best_flux = None, 0.0
            for k, (dr, dc) in enumerate(NEIGHBOURS):
                nr, nc = r + dr, c + dc
                if (nr < 0 or nr >= h or nc < 0 or nc >= w
                        or nodata_mask[nr, nc] or (nr, nc) in seen):
                    continue
                if dem[nr, nc] >= dem[r, c]:
                    continue
                if energy is not None and energy[nr, nc] <= 0.0:
                    continue   # the flow has come to rest; the corridor ends here
                f = flux[nr, nc]
                if f > best_flux:
                    best, best_flux = (nr, nc), f
            if best is None or best_flux < min_flux:
                break
            r, c = best
            pts.append((r, c))
            seen.add((r, c))
        if len(pts) > 2:
            paths.append(pts)
    return paths
