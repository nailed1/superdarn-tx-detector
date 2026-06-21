import sys
import os
import pandas as pd
import matplotlib.pyplot as plt

if len(sys.argv) < 2:
    print(f"Use: python scripts/visualize.py <file.csv>")
    sys.exit(1)

file_name = sys.argv[1]
csv_path = os.path.join("csv", file_name)

if not os.path.exists(csv_path):
    print(f"File {csv_path} not found.")
    sys.exit(1)

df = pd.read_csv(csv_path)
df = df.dropna()

try:
    pivot_power = df.pivot_table(index="range", columns="time", values="power", aggfunc="mean")
    pivot_velocity = df.pivot_table(index="range", columns="time", values="velocity", aggfunc="mean")
    pivot_spec = df.pivot_table(index="range", columns="time", values="spec_width", aggfunc="mean")
except Exception as e:
    print(f"Error: {e}")
    print("Structure must be: time,range,power,velocity,spec_width")
    sys.exit(1)

fig, axes = plt.subplots(nrows=3, ncols=1, figsize=(12, 10), sharex=True)

titles = [
    "Power(dB)", 
    "Velocity(m/s)", 
    "Spec.width(m/s)"
]
data_sources = [pivot_power, pivot_velocity, pivot_spec]

for i, ax in enumerate(axes):
    data = data_sources[i]

    mesh = ax.pcolormesh(
        data.columns,
        data.index,
        data.values,
        cmap="plasma",
        shading="auto"
    )
        
    ax.set_title(titles[i], fontsize=12)
    ax.set_ylabel("Range(km)", fontsize=10)
        
    cbar = fig.colorbar(mesh, ax=ax, pad=0.02, aspect=10)
    cbar.ax.tick_params(labelsize=8)

axes[-1].set_xlabel("Time (Hours)", fontsize=10)

plt.tight_layout()
plt.show()