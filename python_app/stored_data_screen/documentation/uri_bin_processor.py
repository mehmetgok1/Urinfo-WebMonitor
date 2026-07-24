import os
import glob
import numpy as np
# Define the path to your folder
folder_path = "processed_sessions/20260724_141650K422Br20/irimage/"
# Find all CSV files matching the pattern
file_pattern = os.path.join(folder_path, "ir_*_*.csv")
file_list = glob.glob(file_pattern)
# Function to extract the sequence number for sorting
def extract_sequence(filepath):
    # Example filename: ir_602966_105.csv
    filename = os.path.basename(filepath)
    # Split by '_' to get '105.csv', then strip the '.csv' to convert to an integer
    seq_str = filename.split('_')[-1].replace('.csv', '')
    return int(seq_str)


file_list.sort(key=extract_sequence)
# Load data into a list of matrices
matrices = []
sequences = []
sequence=1
for file in file_list:
    # Read the CSV into a 12x16 NumPy array
    data = np.loadtxt(file, delimiter=',')
    matrices.append(data)
    sequences.append(sequence)
    sequence += 1
# Convert the list of matrices into a single 3D NumPy array
ir_data_cube = np.array(matrices)
# Print a summary to verify
print(f"Successfully loaded {ir_data_cube.shape[0]} files.")
print(f"Overall Data Cube Shape: {ir_data_cube.shape} (Frames, Rows, Columns)")
#print(ir_data_cube[sequences.index(1)])  # Optional: Print the sequence 1 matrix to verify the first frame

