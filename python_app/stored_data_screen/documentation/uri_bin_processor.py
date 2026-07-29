import os
import glob
import cv2
import numpy as np
import pandas as pd
import heapq

#20260727_172928K428Br20 20260727_173615K436Br60 20260727_174540K426Br100

#20260727_173239K434Br40 20260727_174047K422Br80
# Define the path to your folder
folder_path = "extracted_sessions/20260727_173239K434Br40/irimage/"
path_parts = os.path.normpath(folder_path).split(os.sep)
session_id = path_parts[-2]

file_pattern = os.path.join(folder_path, "ir_*_*.csv")
file_list = glob.glob(file_pattern)

def extract_sequence(filepath):
    filename = os.path.basename(filepath)
    seq_str = filename.split('_')[-1].replace('.csv', '')
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

ir_data_cube = np.array(matrices)

# Target high-resolution dimensions
target_w = 256
target_h = 192

# 1. Upscale all IR frames in the datacube upfront
upscaled_cube = np.array([
    cv2.resize(m, (target_w, target_h), interpolation=cv2.INTER_CUBIC)
    for m in ir_data_cube
])

# 2. Get top 3 highest peak frames from the raw data
top_3 = heapq.nlargest(3, ((np.max(m), idx) for idx, m in enumerate(ir_data_cube)))

origx_scaled = []
origy_scaled = []
radius_scaled_list = []

# 3. Find center and radius in HIGH-RES (256x192) space directly
for idx, (temp, matrix_idx) in enumerate(top_3, 1):
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

# 4. Averaged center and radius (all in 256x192 space!)
circle_x = sum(origx_scaled) / len(origx_scaled)
circle_y = sum(origy_scaled) / len(origy_scaled)
circle_radius = sum(radius_scaled_list) / len(radius_scaled_list)

r20  = circle_radius * 0.2
r40  = circle_radius * 0.4
r60  = circle_radius * 0.6
r80  = circle_radius * 0.8
r100 = circle_radius

print(f"High-res circle at x={circle_x:.2f}, y={circle_y:.2f}, radius={circle_radius:.2f}px")

# 5. Continuous float distance matrix on the 256x192 grid
y_grid, x_grid = np.ogrid[:target_h, :target_w]
dist_map = np.sqrt((x_grid - circle_x)**2 + (y_grid - circle_y)**2)

# Build floating-point donut masks directly (no integer truncation!)
mask_0_20   = dist_map <= r20
mask_20_40  = (dist_map > r20) & (dist_map <= r40)
mask_40_60  = (dist_map > r40) & (dist_map <= r60)
mask_60_80  = (dist_map > r60) & (dist_map <= r80)
mask_80_100 = (dist_map > r80) & (dist_map <= r100)

# 6. Extract temperature statistics across upscaled frames
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

os.makedirs("processed_data", exist_ok=True)
csv_filename = f"{session_id}_temperature_data.csv"
csv_path = os.path.join("processed_data/", csv_filename)
df_results.to_csv(csv_path, index=False)
print(f"Data successfully saved to: {csv_path}")