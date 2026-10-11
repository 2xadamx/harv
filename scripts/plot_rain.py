"""Render the HARV rain example CSV as a dependency-free SVG figure."""
import csv
import sys
from pathlib import Path


def render(source: Path, destination: Path) -> None:
    with source.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        raise ValueError("rain trajectory needs at least two samples")

    # Convert solver SI output to reader-friendly hours and millimetres.
    data = [
        (
            float(row["t"]) / 3600,
            float(row["rain_rate"]) * 3_600_000,
            float(row["soil_water"]) * 1000,
            float(row["runoff_depth"]) * 1000,
        )
        for row in rows
    ]
    panels = [
        ("Rain intensity", "mm/h", 1, 0, 20, 5, "#1677b8"),
        ("Soil water", "mm", 2, 0, 40, 10, "#16845b"),
        ("Accumulated runoff", "mm", 3, 0, 4, 1, "#bd5a18"),
    ]
    width, height = 960, 760
    left, right, plot_h = 105, 875, 142
    x_max = data[-1][0]
    chunks = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">HARV: respuesta de lluvia y suelo</title>',
        '<desc id="desc">Simulación de dos horas: disminuye la intensidad de lluvia, baja el agua almacenada en el suelo y se acumula escorrentía.</desc>',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<g font-family="Segoe UI, Arial, sans-serif" fill="#202a35">',
        '<text x="70" y="40" font-size="24" font-weight="700">Lluvia, suelo y escorrentía</text>',
        '<text x="70" y="64" font-size="13" fill="#536273">HARV scalar ODE · RK4 · 10 s por paso · modelo concentrado</text>',
    ]
    x_ticks = [0, 0.5, 1, 1.5, 2]
    for panel_index, (label, unit, column, y_min, y_max, y_step, color) in enumerate(panels):
        top = 92 + panel_index * 208
        bottom = top + plot_h
        chunks.append(f'<text x="{left}" y="{top - 12}" font-size="16" font-weight="600">{label}</text>')
        chunks.append(f'<text x="{left - 58}" y="{top + plot_h / 2}" font-size="12" text-anchor="middle" transform="rotate(-90 {left - 58} {top + plot_h / 2})">{unit}</text>')
        for tick in range(y_min, y_max + 1, y_step):
            py = bottom - (tick - y_min) / (y_max - y_min) * plot_h
            chunks.append(f'<line x1="{left}" y1="{py:.1f}" x2="{right}" y2="{py:.1f}" stroke="#dbe2e8" stroke-width="1"/>')
            chunks.append(f'<text x="{left - 12}" y="{py + 4:.1f}" font-size="12" text-anchor="end" fill="#536273">{tick}</text>')
        for tick in x_ticks:
            px = left + tick / x_max * (right - left)
            chunks.append(f'<line x1="{px:.1f}" y1="{top}" x2="{px:.1f}" y2="{bottom}" stroke="#edf0f3" stroke-width="1"/>')
            if panel_index == 2:
                chunks.append(f'<text x="{px:.1f}" y="{bottom + 21}" font-size="12" text-anchor="middle" fill="#536273">{tick:g}</text>')
        chunks.append(f'<path d="M {left} {top} V {bottom} H {right}" fill="none" stroke="#647383" stroke-width="1.2"/>')
        points = []
        for row in data:
            x = left + row[0] / x_max * (right - left)
            y = bottom - (row[column] - y_min) / (y_max - y_min) * plot_h
            points.append(f'{x:.1f},{y:.1f}')
        chunks.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>')
        final = data[-1][column]
        chunks.append(f'<circle cx="{right}" cy="{bottom - (final-y_min)/(y_max-y_min)*plot_h:.1f}" r="4" fill="{color}"/>')
        chunks.append(f'<text x="{right - 7}" y="{top + 17}" font-size="12" text-anchor="end" fill="{color}" font-weight="600">final: {final:.2f} {unit}</text>')
    chunks.extend([
        f'<text x="{(left + right) / 2}" y="{height - 20}" font-size="12" text-anchor="middle">Tiempo (h)</text>',
        f'<text x="70" y="{height - 4}" font-size="10" fill="#536273">Tasas y cantidades derivadas del ejemplo examples/rain.harv; no es un pronóstico.</text>',
        '</g></svg>',
    ])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(chunks) + "\n", encoding="utf-8")


if __name__ == "__main__":
    input_csv = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs/rain_trajectory.csv")
    output_svg = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("docs/assets/rain_response.svg")
    render(input_csv, output_svg)
    print(f"Wrote {output_svg}")
