import os
import glob
import cv2
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import heapq
#20260727_172928K428Br20  20260727_173615K436Br60  20260727_174540K426Br100
#20260727_173239K434Br40  20260727_174047K422Br80
# #######################
#########IR CAMERA EXTRACTOR AND PLOTTER#########
#######################
# Define the path to your folder
folder_path = "extracted_sessions/20260727_172928K428Br20/irimage/"
path_parts = os.path.normpath(folder_path).split(os.sep)
session_id = path_parts[-2]  # Grabs '20260724_142142K420Br60'
# Find all CSV files matching the pattern
file_pattern = os.path.join(folder_path, "ir_*_*.csv")
file_list = glob.glob(file_pattern)

def extract_sequence(filepath):
    filename = os.path.basename(filepath)
    seq_str = filename.split('_')[-1].replace('.csv', '')
    return int(seq_str)

file_list.sort(key=extract_sequence)

# Load data into matrices
matrices = []
sequences = []
sequence = 1
for file in file_list:
    data = np.loadtxt(file, delimiter=',')
    matrices.append(data)
    sequences.append(sequence)
    sequence += 1

ir_data_cube = np.array(matrices)
target_w = 256
target_h = 192
results = []
maxtempidx = []
# 1. Get the max value of each matrix across the datacube
matrix_maxes = [np.max(m) for m in ir_data_cube]
# 2. Get the top 3 highest values
top_3 = heapq.nlargest(3, ((np.max(m), idx) for idx, m in enumerate(ir_data_cube)))
for idx, (temp, matrix_idx) in enumerate(top_3, 1):
    print(f"Top {idx}: Max Temp = {temp}, Matrix Index = {matrix_idx+1}")
origx=[]
origy=[]
radius=[]
for idx, (temp, matrix_idx) in enumerate(top_3, 1):
    matrix = ir_data_cube[np.asarray(matrix_idx).item()]
    h, w = matrix.shape

    min_temp = np.min(matrix)
    max_temp = np.max(matrix)
    
    norm = max(max_temp - min_temp, 1e-5)
    gray_normalized = ((matrix - min_temp) / norm * 255).astype(np.uint8)
    
    display_gray = cv2.resize(
        gray_normalized,
        (target_w, target_h),
        interpolation=cv2.INTER_CUBIC      
    )
    _, thresh = cv2.threshold(
        display_gray,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    
    contours, _ = cv2.findContours(
        thresh,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )
    
    if contours:
        largest = max(contours, key=cv2.contourArea)
        (center_x_scaled, center_y_scaled), radius_scaled = cv2.minEnclosingCircle(largest)
    else:
        _, _, _, max_loc = cv2.minMaxLoc(display_gray)
        center_x_scaled = max_loc[0]
        center_y_scaled = max_loc[1]
        radius_scaled = 10.0
        
    scale_x = target_w / w
    scale_y = target_h / h

    orig_x = center_x_scaled / scale_x
    orig_y = center_y_scaled / scale_y
    radius_raw = radius_scaled / scale_x 
    origx.append(orig_x)
    origy.append(orig_y)
    radius.append(radius_raw)
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(
        mask,
        (int(orig_x), int(orig_y)),
        max(1, int(radius_raw)),
        255,
        -1
    )
# 1. Calculate the averaged circle properties ONCE
circle_x = sum(origx) / len(origx)
circle_y = sum(origy) / len(origy)
circle_radius = sum(radius) / len(radius)
circle_radius_80per = circle_radius * 0.8
circle_radius_60per = circle_radius * 0.6
circle_radius_40per = circle_radius * 0.4
circle_radius_20per = circle_radius * 0.2
print(f"found circle is at x={circle_x}, y={circle_y}, radius={circle_radius}")
# 2. Get matrix dimensions from the first frame to pre-build the static mask
h, w = ir_data_cube[0].shape
# 3. Create the fixed mask ONCE outside the loop
fixed_mask = np.zeros((h, w), dtype=np.uint8)
cv2.circle(
    fixed_mask,
    (int(circle_x), int(circle_y)),
    max(1, int(circle_radius)),
    255,
    -1
)
fixed_mask_80per = np.zeros((h, w), dtype=np.uint8)
cv2.circle(
    fixed_mask_80per,
    (int(circle_x), int(circle_y)),
    max(1, int(circle_radius_80per)),
    255,
    -1
)
fixed_mask_60per = np.zeros((h, w), dtype=np.uint8)
cv2.circle(
    fixed_mask_60per,
    (int(circle_x), int(circle_y)),
    max(1, int(circle_radius_60per)),
    255,
    -1
)
fixed_mask_40per = np.zeros((h, w), dtype=np.uint8)
cv2.circle(
    fixed_mask_40per,
    (int(circle_x), int(circle_y)),
    max(1, int(circle_radius_40per)),
    255,    
    -1
)
fixed_mask_20per = np.zeros((h, w), dtype=np.uint8)
cv2.circle(
    fixed_mask_20per,
    (int(circle_x), int(circle_y)),
    max(1, int(circle_radius_20per)),
    255,    
    -1
)
# 4. Loop through frames directly
results = []
for idx, matrix in enumerate(ir_data_cube):
    min_temp = np.min(matrix)
    max_temp = np.max(matrix)
    
    # Calculate average temperature using the pre-built mask directly
    avg_circle_temp = cv2.mean(matrix.astype(np.float32), mask=fixed_mask)[0]
    avg_circle_temp_80per = cv2.mean(matrix.astype(np.float32), mask=fixed_mask_80per)[0]
    avg_circle_temp_60per = cv2.mean(matrix.astype(np.float32), mask=fixed_mask_60per)[0]
    avg_circle_temp_40per = cv2.mean(matrix.astype(np.float32), mask=fixed_mask_40per)[0]
    avg_circle_temp_20per = cv2.mean(matrix.astype(np.float32), mask=fixed_mask_20per)[0]
    results.append({
        'Sequence': sequences[idx],
        'Min_Temp': round(min_temp, 2),
        'Max_Temp': round(max_temp, 2),
        'Avg_Circle_Temp': round(avg_circle_temp, 2),
        'Avg_Circle_Temp_80per': round(avg_circle_temp_80per, 2),
        'Avg_Circle_Temp_60per': round(avg_circle_temp_60per, 2),
        'Avg_Circle_Temp_40per': round(avg_circle_temp_40per, 2),
        'Avg_Circle_Temp_20per': round(avg_circle_temp_20per, 2)
    })

df_results = pd.DataFrame(results)

# --- NEW: Save the raw data to CSV for later comparison ---
csv_filename = f"{session_id}_temperature_data.csv"
csv_path = os.path.join("processed_data/", csv_filename)
df_results.to_csv(csv_path, index=False)
print(f"Data successfully saved to: {csv_path}")

#######################
#########MIC PLOTTER#########
#######################
# --- MIC PLOTTER DATA PREP ---
# 20260724_141650K422Br20  20260724_141927K425Br40  20260724_142142K420Br60

# mic_file = "extracted_sessions/20260724_141650K422Br20/accel_mic/accel_mic_stream.csv"

# # Extract the session_id from the filepath (the "middle guy")
# path_parts = os.path.normpath(mic_file).split(os.sep)
# session_id = path_parts[-3] # Grabs '20260724_142142K420Br60'

# # 1. Load the CSV
# df = pd.read_csv(mic_file)

# # 2. Grab just the 'mic' column as a raw list of numbers
# raw_mic_data = df['mic'].values

# # 3. Chop it into blocks of 2000! 
# # The -1 tells numpy to figure out how many rows to make automatically based on the data length.
# mic_data_matrix = raw_mic_data.reshape(-1, 2000)

# print(f"Matrix created! Shape is: {mic_data_matrix.shape} (Sequences, Mic Samples)")

# # 4. Save this matrix to a clean new CSV with the session ID in the name
# # Create the processed_data directory if it doesn't already exist
# os.makedirs("processed_data", exist_ok=True)

# output_filepath = f"processed_data/{session_id}_processed_mic_matrix.csv"
# processed_df = pd.DataFrame(mic_data_matrix)
# processed_df.to_csv(output_filepath, index=False, header=False)

# print(f"Successfully saved to: {output_filepath}")