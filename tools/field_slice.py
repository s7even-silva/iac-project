"""Precompute the z = 0 field slices drawn by the storyboard (iron filings) and embed them in
public/storyboard/index.html, so the page does not run Biot-Savart on the fly.

Each CREW HaT coil is an ellipse (semi-axes 4 m along the ship, 2 m in its plane) on the 8 m ring,
1e7 A-turns spread over 3 x 2 filaments across the winding pack (~0.67 x 0.32 m), core 0.1 m.
"niac": current senses theta = 90 deg - phi (assumed, D9); "k1": first-sweep layout theta = 2 phi.
Grid 81 x 81, step 0.45 m (+-18 m). Stored as little-endian int16 (bx, by interleaved) in mT, base64.

    python3 tools/field_slice.py && python3 tools/build_rooms.py
"""
import base64, json, re
from pathlib import Path
import numpy as np

N_GRID, STEP = 81, 0.45
X0 = -(N_GRID - 1) / 2 * STEP
THETA = {"niac": lambda ph: np.pi / 2 - ph, "k1": lambda ph: 2 * ph}


def segments(layout):
    segs = []
    for k in range(8):
        ph = k * np.pi / 4
        th = THETA[layout](ph)
        c = np.array([8 * np.cos(ph), 8 * np.sin(ph), 0])
        v = np.array([np.sin(th), -np.cos(th), 0])
        u = np.array([np.cos(th), np.sin(th), 0])
        for dr in (-0.22, 0, 0.22):
            for dn in (-0.08, 0.08):
                t = np.linspace(0, 2 * np.pi, 73)
                P = c + (2 + dr) * np.sin(t)[:, None] * v + dn * u + (4 + dr) * np.cos(t)[:, None] * np.array([0, 0, 1])
                segs.append(np.hstack([(P[:-1] + P[1:]) / 2, P[1:] - P[:-1]]))
    return np.vstack(segs)


def slice_mT(layout):
    S = segments(layout)
    xs = X0 + np.arange(N_GRID) * STEP
    X, Y = np.meshgrid(xs, xs)  # row j = y, column i = x
    out = np.zeros((N_GRID, N_GRID, 2))
    I, core2 = 1e7 / 6, 0.1 ** 2
    for mx, my, mz, lx, ly, lz in S:
        rx, ry, rz = X - mx, Y - my, -mz
        q = (rx * rx + ry * ry + rz * rz + core2) ** -1.5
        out[..., 0] += (ly * rz - lz * ry) * q
        out[..., 1] += (lz * rx - lx * rz) * q
    out *= 1e-7 * I * 1e3  # T -> mT
    assert np.abs(out).max() < 32767
    return np.round(out).astype("<i2")


if __name__ == "__main__":
    page = Path(__file__).resolve().parent.parent / "public" / "storyboard" / "index.html"
    s = page.read_text()
    m = re.search(r'(<script type="application/json" id="data">)(.*?)(</script>)', s, re.S)
    data = json.loads(m.group(2))
    data["field"] = {"n": N_GRID, "x0": X0, "d": STEP}
    for layout in THETA:
        arr = slice_mT(layout)
        data["field"][layout] = base64.b64encode(arr.tobytes()).decode()
        print(layout, "|B| at centre", np.hypot(*arr[N_GRID // 2, N_GRID // 2]) / 1e3, "T")
    page.write_text(s[:m.start(2)] + json.dumps(data, separators=(",", ":")) + s[m.end(2):])
    print("wrote", page)
