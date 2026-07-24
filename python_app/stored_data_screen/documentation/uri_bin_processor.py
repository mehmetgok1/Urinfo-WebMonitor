import os
import glob
import cv2
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
# 20260724_141650K422Br20  20260724_141927K425Br40  20260724_142142K420Br60

#######################
#########IR CAMERA EXTRACTOR AND PLOTTER#########
#######################
# Define the path to your folder
folder_path = "extracted_sessions/20260724_142142K420Br60/irimage/"
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
print(f"Successfully loaded {ir_data_cube.shape[0]} files.")

target_w = 256
target_h = 192
results = []

for idx, matrix in enumerate(ir_data_cube):
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
    
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(
        mask,
        (int(orig_x), int(orig_y)),
        max(1, int(radius_raw)),
        255,
        -1
    )
    
    avg_circle_temp = cv2.mean(matrix.astype(np.float32), mask=mask)[0]
    
    results.append({
        'Sequence': sequences[idx],
        'Min_Temp': round(min_temp, 2),
        'Max_Temp': round(max_temp, 2),
        'Avg_Circle_Temp': round(avg_circle_temp, 2)
    })

df_results = pd.DataFrame(results)
print("\nProcessing Results (Head):")
print(df_results.head(10))

# --- Plotting the Results ---

fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 10), sharex=True)

# 1. Highest Temperature Plot
ax1.plot(df_results['Sequence'], df_results['Max_Temp'], color='red', label='Highest Temp')
ax1.set_ylabel('Temperature (°C)')
ax1.set_title(f'Highest Temperature per Frame ({session_id})')
ax1.grid(True, linestyle='--', alpha=0.7)
ax1.legend(loc='upper right')

# 2. Lowest Temperature Plot
ax2.plot(df_results['Sequence'], df_results['Min_Temp'], color='blue', label='Lowest Temp')
ax2.set_ylabel('Temperature (°C)')
ax2.set_title(f'Lowest Temperature per Frame ({session_id})')
ax2.grid(True, linestyle='--', alpha=0.7)
ax2.legend(loc='upper right')

# 3. Average Circle Temperature Plot
ax3.plot(df_results['Sequence'], df_results['Avg_Circle_Temp'], color='green', label='Avg Circle Temp')
ax3.set_xlabel('Frame Sequence')
ax3.set_ylabel('Temperature (°C)')
ax3.set_title(f'Average Hotspot (Circle) Temperature per Frame ({session_id})')
ax3.grid(True, linestyle='--', alpha=0.7)
ax3.legend(loc='upper right')

plt.tight_layout()


save_filename = f"{session_id}_temperature_plot.png"
save_path = os.path.join("processed_data/", save_filename)

# Save the plot
plt.savefig(save_path, dpi=300, bbox_inches='tight')
print(f"\nPlot successfully saved to: {save_path}")


# --- NEW: Save the raw data to CSV for later comparison ---
csv_filename = f"{session_id}_temperature_data.csv"
csv_path = os.path.join("processed_data/", csv_filename)
df_results.to_csv(csv_path, index=False)
print(f"Data successfully saved to: {csv_path}")

# --- Existing: Save the plot image ---
save_filename = f"{session_id}_temperature_plot.png"
save_path = os.path.join("processed_data/", save_filename)

plt.savefig(save_path, dpi=300, bbox_inches='tight')
print(f"Plot successfully saved to: {save_path}")

#plt.show()


#######################
#########MIC PLOTTER#########
#######################
# --- MIC PLOTTER DATA PREP ---
# 20260724_141650K422Br20  20260724_141927K425Br40  20260724_142142K420Br60

mic_file = "extracted_sessions/20260724_141650K422Br20/accel_mic/accel_mic_stream.csv"

# Extract the session_id from the filepath (the "middle guy")
path_parts = os.path.normpath(mic_file).split(os.sep)
session_id = path_parts[-3] # Grabs '20260724_142142K420Br60'

# 1. Load the CSV
df = pd.read_csv(mic_file)

# 2. Grab just the 'mic' column as a raw list of numbers
raw_mic_data = df['mic'].values

# 3. Chop it into blocks of 2000! 
# The -1 tells numpy to figure out how many rows to make automatically based on the data length.
mic_data_matrix = raw_mic_data.reshape(-1, 2000)

print(f"Matrix created! Shape is: {mic_data_matrix.shape} (Sequences, Mic Samples)")

# 4. Save this matrix to a clean new CSV with the session ID in the name
# Create the processed_data directory if it doesn't already exist
os.makedirs("processed_data", exist_ok=True)

output_filepath = f"processed_data/{session_id}_processed_mic_matrix.csv"
processed_df = pd.DataFrame(mic_data_matrix)
processed_df.to_csv(output_filepath, index=False, header=False)

print(f"Successfully saved to: {output_filepath}")