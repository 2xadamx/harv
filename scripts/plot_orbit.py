"""Create a dependency-free SVG audit figure from HARV's orbit CSV."""
import csv
import math
import sys
from pathlib import Path


def make_figure(source: Path, destination: Path) -> None:
    with source.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        raise ValueError("orbit trajectory needs at least two samples")

    mu = float(rows[0]["mu"])
    x0, y0 = float(rows[0]["x"]), float(rows[0]["y"])
    radius0 = math.hypot(x0, y0)
    mean_motion = math.sqrt(mu / radius0**3)
    period = 2 * math.pi / mean_motion
    energy0 = 0.5 * (float(rows[0]["vx"])**2 + float(rows[0]["vy"])**2) - mu / radius0
    h0 = x0 * float(rows[0]["vy"]) - y0 * float(rows[0]["vx"])
    position_errors = []
    max_energy_drift = 0.0
    for row in rows:
        t, x, y = float(row["t"]), float(row["x"]), float(row["y"])
        vx, vy = float(row["vx"]), float(row["vy"])
        expected_x = radius0 * math.cos(mean_motion * t)
        expected_y = radius0 * math.sin(mean_motion * t)
        position_errors.append((t / 3600, math.hypot(x - expected_x, y - expected_y) * 1000))
        energy = 0.5 * (vx * vx + vy * vy) - mu / math.hypot(x, y)
        max_energy_drift = max(max_energy_drift, abs((energy - energy0) / energy0))

    width, height = 1100, 780
    cx, cy, scale = 315, 380, 225 / 8000  # equal x/y scale; coordinates are km
    orbit_points = []
    for row in rows:
        px = cx + float(row["x"]) / 1000 * scale
        py = cy - float(row["y"]) / 1000 * scale
        orbit_points.append(f"{px:.2f},{py:.2f}")

    chart_left, chart_right = 690, 1030
    chart_top, chart_bottom = 220, 505
    max_error = max(error for _, error in position_errors)
    y_limit = max_error * 1.15 or 1.0
    time_max = position_errors[-1][0]
    error_points = []
    for time_h, error_mm in position_errors:
        px = chart_left + time_h / time_max * (chart_right - chart_left)
        py = chart_bottom - error_mm / y_limit * (chart_bottom - chart_top)
        error_points.append(f"{px:.2f},{py:.2f}")

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Órbita de HARV comparada con Kepler</title>',
        '<desc id="desc">La trayectoria calculada por HARV coincide con la órbita circular analítica; un panel muestra el error de posición durante la simulación.</desc>',
        '<rect width="100%" height="100%" fill="#fff"/>',
        '<g font-family="Segoe UI, Arial, sans-serif" fill="#17212b">',
        '<text x="52" y="48" font-size="26" font-weight="700">Una órbita que podemos auditar</text>',
        '<text x="52" y="76" font-size="14" fill="#536273">HARV + RK4 frente a la solución analítica de Kepler · modelo newtoniano de dos cuerpos</text>',
        '<text x="315" y="132" font-size="16" font-weight="600" text-anchor="middle">Trayectoria (misma escala en ambos ejes)</text>',
    ]

    # Cartesian grid and labels in the orbit panel.
    for tick in (-8000, -4000, 0, 4000, 8000):
        px = cx + tick * scale
        py = cy - tick * scale
        parts.append(f'<line x1="{px:.1f}" y1="{cy-225}" x2="{px:.1f}" y2="{cy+225}" stroke="#e6ebef"/>')
        parts.append(f'<line x1="{cx-225}" y1="{py:.1f}" x2="{cx+225}" y2="{py:.1f}" stroke="#e6ebef"/>')
        parts.append(f'<text x="{px:.1f}" y="{cy+249}" font-size="12" text-anchor="middle" fill="#536273">{tick}</text>')
        parts.append(f'<text x="{cx-239}" y="{py+4:.1f}" font-size="12" text-anchor="end" fill="#536273">{tick}</text>')
    parts.extend([
        f'<circle cx="{cx}" cy="{cy}" r="{radius0/1000*scale:.2f}" fill="none" stroke="#d8752b" stroke-width="2.5" stroke-dasharray="8 6"/>',
        f'<polyline points="{" ".join(orbit_points)}" fill="none" stroke="#1269a8" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>',
        f'<circle cx="{cx}" cy="{cy}" r="5" fill="#d8752b"/>',
        f'<circle cx="{cx+float(rows[0]["x"])/1000*scale:.2f}" cy="{cy-float(rows[0]["y"])/1000*scale:.2f}" r="6" fill="#16845b" stroke="#fff" stroke-width="2"/>',
        f'<text x="{cx}" y="{cy+273}" font-size="12" text-anchor="middle" fill="#536273">x (km)</text>',
        f'<text x="{cx-275}" y="{cy}" font-size="12" text-anchor="middle" transform="rotate(-90 {cx-275} {cy})" fill="#536273">y (km)</text>',
        '<line x1="85" y1="710" x2="120" y2="710" stroke="#1269a8" stroke-width="3"/><text x="130" y="715" font-size="13">HARV RK4</text>',
        '<line x1="245" y1="710" x2="280" y2="710" stroke="#d8752b" stroke-width="2.5" stroke-dasharray="8 6"/><text x="290" y="715" font-size="13">Kepler analítica</text>',
        '<circle cx="455" cy="710" r="5" fill="#d8752b"/><text x="467" y="715" font-size="13">Tierra (punto; no a escala)</text>',
        '<text x="860" y="132" font-size="16" font-weight="600" text-anchor="middle">Error de posición vs. Kepler</text>',
    ])

    for fraction in (0, 0.5, 1):
        y_val = y_limit * fraction
        py = chart_bottom - fraction * (chart_bottom - chart_top)
        parts.append(f'<line x1="{chart_left}" y1="{py:.1f}" x2="{chart_right}" y2="{py:.1f}" stroke="#e6ebef"/>')
        parts.append(f'<text x="{chart_left-10}" y="{py+4:.1f}" font-size="12" text-anchor="end" fill="#536273">{y_val:.3f}</text>')
    for fraction in (0, 0.5, 1):
        px = chart_left + fraction * (chart_right - chart_left)
        parts.append(f'<line x1="{px:.1f}" y1="{chart_top}" x2="{px:.1f}" y2="{chart_bottom}" stroke="#f0f2f4"/>')
        parts.append(f'<text x="{px:.1f}" y="{chart_bottom+22}" font-size="12" text-anchor="middle" fill="#536273">{time_max*fraction:.2f}</text>')
    parts.extend([
        f'<path d="M {chart_left} {chart_top} V {chart_bottom} H {chart_right}" fill="none" stroke="#647383" stroke-width="1.2"/>',
        f'<polyline points="{" ".join(error_points)}" fill="none" stroke="#7251a1" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>',
        f'<text x="{(chart_left+chart_right)/2}" y="{chart_bottom+48}" font-size="12" text-anchor="middle">Tiempo (h)</text>',
        f'<text x="{chart_left-51}" y="{(chart_top+chart_bottom)/2}" font-size="12" text-anchor="middle" transform="rotate(-90 {chart_left-51} {(chart_top+chart_bottom)/2})">Error (mm)</text>',
        f'<text x="860" y="565" font-size="14" text-anchor="middle" font-weight="600">Máximo observado: {max_error:.5f} mm</text>',
        f'<text x="860" y="593" font-size="13" text-anchor="middle" fill="#536273">Período teórico: {period:.3f} s</text>',
        f'<text x="860" y="618" font-size="13" text-anchor="middle" fill="#536273">Deriva relativa de energía: {max_energy_drift:.2e}</text>',
        '<text x="550" y="762" font-size="11" text-anchor="middle" fill="#536273">Órbita ideal: se omiten atmósfera, achatamiento terrestre, Luna y relatividad. Un benchmark, no una efeméride.</text>',
        '</g></svg>',
    ])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(parts) + "\n", encoding="utf-8")


if __name__ == "__main__":
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs/orbit_trajectory.csv")
    svg_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("docs/assets/orbit_result.svg")
    make_figure(csv_path, svg_path)
    print(f"Wrote {svg_path}")
