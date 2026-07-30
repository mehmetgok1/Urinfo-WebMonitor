import cv2
import numpy as np
import pandas as pd
import heapq
from pathlib import Path

# 1. Use Path to handle OS-specific slashes automatically
folder_path = Path("extracted_sessions/20260727_174540K426Br100/irimage")
# e.g., parent is "20260727_174540K426Br100", name is the string.
session_id = folder_path.parent.name
file_list = list(folder_path.glob("ir_*_*.csv"))

def extract_sequence(filepath):
    seq_str = filepath.stem.split('_')[-1] #list according to sequence number last portion after _
    return int(seq_str)

file_list.sort(key=extract_sequence)

matrices = []
sequences = []
sequence = 1
for file in file_list:
    data = np.loadtxt(file, delimiter=',')
    matrices.append(data)
    sequences.append(sequence)
    sequence += 1

ir_data_cube = np.array(matrices) ##make matrices 3d 

target_w = 256
target_h = 192

# Upscale all IR frames in the datacube upfront
upscaled_cube = np.array([
    cv2.resize(m, (target_w, target_h), interpolation=cv2.INTER_CUBIC)
    for m in ir_data_cube
])

# Get top 3 highest peak frames from the raw data
top_3 = heapq.nlargest(3, ((np.max(m), idx) for idx, m in enumerate(ir_data_cube)))

origx_scaled = []
origy_scaled = []
radius_scaled_list = []

for temp, matrix_idx in top_3:
    display_gray = upscaled_cube[matrix_idx]
    
    min_temp = np.min(display_gray)
    max_temp = np.max(display_gray)
    norm = max(max_temp - min_temp, 1e-5)
    gray_normalized = ((display_gray - min_temp) / norm * 255).astype(np.uint8)
    
    _, thresh = cv2.threshold(
        gray_normalized,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if contours:
        largest = max(contours, key=cv2.contourArea)
        (cx, cy), r = cv2.minEnclosingCircle(largest)
    else:
        _, _, _, max_loc = cv2.minMaxLoc(gray_normalized)
        cx, cy = max_loc[0], max_loc[1]
        r = 50.0  # fallback radius in 256x192 space
        
    origx_scaled.append(cx)
    origy_scaled.append(cy)
    radius_scaled_list.append(r)

# Averaged center and radius (all in 256x192 space!)
circle_x = sum(origx_scaled) / len(origx_scaled)
circle_y = sum(origy_scaled) / len(origy_scaled)
circle_radius = sum(radius_scaled_list) / len(radius_scaled_list)

r20  = circle_radius * 0.2
r40  = circle_radius * 0.4
r60  = circle_radius * 0.6
r80  = circle_radius * 0.8
r100 = circle_radius

print(f"High-res circle at x={circle_x:.2f}, y={circle_y:.2f}, radius={circle_radius:.2f}px")

# Continuous float distance matrix on the 256x192 grid
y_grid, x_grid = np.ogrid[:target_h, :target_w]
distance_map = np.sqrt((x_grid - circle_x)**2 + (y_grid - circle_y)**2) ##calculate all points distance from center of circle of 192*256 array

# Build floating-point donut masks directly
mask_0_20   = distance_map <= r20
mask_20_40  = (distance_map > r20) & (distance_map <= r40)
mask_40_60  = (distance_map > r40) & (distance_map <= r60)
mask_60_80  = (distance_map > r60) & (distance_map <= r80)
mask_80_100 = (distance_map > r80) & (distance_map <= r100)

# Extract temperature statistics across upscaled frames
results = []
for idx in range(len(ir_data_cube)):
    raw_matrix = ir_data_cube[idx]
    upscaled_matrix = upscaled_cube[idx]
    
    results.append({
        'Sequence': sequences[idx],
        'Min_Temp': round(float(np.min(raw_matrix)), 2),
        'Max_Temp': round(float(np.max(raw_matrix)), 2),
        'Avg_Core_0_20':   round(float(np.mean(upscaled_matrix[mask_0_20])), 2),
        'Avg_Ring_20_40': round(float(np.mean(upscaled_matrix[mask_20_40])), 2),
        'Avg_Ring_40_60': round(float(np.mean(upscaled_matrix[mask_40_60])), 2),
        'Avg_Ring_60_80': round(float(np.mean(upscaled_matrix[mask_60_80])), 2),
        'Avg_Ring_80_100':round(float(np.mean(upscaled_matrix[mask_80_100])), 2)
    })

df_results = pd.DataFrame(results)

# 2. OS-Safe directory creation and Windows file-lock handling
out_dir = Path("processed_data")
out_dir.mkdir(exist_ok=True)
csv_path = out_dir / f"{session_id}_temperature_data.csv"

try:
    df_results.to_csv(csv_path, index=False)
    print(f"Data successfully saved to: {csv_path}")
except PermissionError:
    print(f"ERROR: Permission denied. If you are on Windows, ensure '{csv_path.name}' is not open in Excel.")