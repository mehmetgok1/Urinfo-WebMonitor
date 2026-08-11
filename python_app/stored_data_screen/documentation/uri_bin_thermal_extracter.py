import numpy as np
import cv2
import os
import csv
import shutil

# 1. STRUCT definition (sizeof = 15033 bytes)
combined_packet_dtype = np.dtype([
    ('batteryLevel', 'f4'),
    ('batteryPercentage', 'f4'),
    ('ambLight', 'f4'),
    ('ambLight_Int', 'u2'),
    ('PIRValue', 'f4'),
    ('movingDist', 'u2'),
    ('movingEnergy', 'u1'),
    ('staticDist', 'u2'),
    ('staticEnergy', 'u1'),
    ('detectionDist', 'u2'),
    ('sequence', 'u2'),
    ('ambientLight_slave', 'u2'),
    ('temperature', 'f4'),
    ('humidity', 'f4'),
    ('accelX', 'i2'), ('accelY', 'i2'), ('accelZ', 'i2'),
    ('gyroX', 'i2'), ('gyroY', 'i2'), ('gyroZ', 'i2'),
    ('timestamp_ms', 'u4'),
    ('status', 'u1'),
    ('accelSampleCount', 'u2'),
    ('accelX_samples', 'i2', (400,)), 
    ('accelY_samples', 'i2', (400,)),
    ('accelZ_samples', 'i2', (400,)),
    ('microphoneSamples', 'u2', (2000,)),
    ('rgbFrame', 'u2', (4096,)),  # 64x64
    ('irFrame', 'u2', (192,))     # 16x12
])

PACKET_SIZE = combined_packet_dtype.itemsize # 15033 bytes
#20260727_172928K428Br20  20260727_173615K436Br60  20260727_174540K426Br100
#20260727_173239K434Br40  20260727_174047K422Br80

#### USER EDIT
session_path = "/home/deso/delete/Urinfo-WebMonitor/python_app/stored_data_screen/documentation/denem_data/BaseWater100mL_HotWaterfrom20to100mL/20260727_174540K426Br100/"
### USER EDIT END

items = session_path.split('/')
if items[-1] == "": 
    items.pop(-1)

session_path = "/" + "/".join(items)
session_id = os.path.basename(session_path)
output_base = os.path.join("./thermal_images", session_id)

# Remove existing folder if present
if os.path.exists(output_base):
    print("Removing existing output folder...")
    shutil.rmtree(output_base)

# Recreate an empty folder to start fresh
os.makedirs(output_base, exist_ok=True)


thermal_csv_path = os.path.join(output_base, f"{session_id}.csv")

print(f"session is processing: {session_id}")

# sort according to suffix (part_0, part_50, part_100) 
bin_files = sorted(
    [f for f in os.listdir(session_path) if f.endswith(".bin")],
    key=lambda f: int(f.split('_part_')[1].split('.')[0])
)

# sequence continuity check variable
first_sequence = None
first_sequence_bool = True
last_sequence = None 

with open(thermal_csv_path, 'w', newline='') as f_thermal:

    for bin_file in bin_files:
        full_path = os.path.join(session_path, bin_file)
        
        file_size = os.path.getsize(full_path)
        expected_packets = file_size // PACKET_SIZE
        print(f"\nProcessing file: {bin_file} | Size: {file_size} bytes | Expected Packets: {expected_packets}")

        with open(full_path, 'rb') as bin_f:
            file_bytes = bin_f.read()
            
        pointer = 0
        packet_idx = 0
        
        while pointer <= len(file_bytes) - PACKET_SIZE:
            raw_bytes = file_bytes[pointer:pointer+PACKET_SIZE]
            packet = np.frombuffer(raw_bytes, dtype=combined_packet_dtype)[0]
            
            ts = packet['timestamp_ms']
            seq = packet['sequence']
            bat = packet['batteryPercentage']
            temp = packet['temperature']
            sample_count = packet['accelSampleCount']
            if first_sequence_bool:
                first_sequence = seq
                first_sequence_bool = False

            # --- SANITY CHECKS ---
            is_valid = True
            if sample_count != 400: is_valid = False
            if not (0.0 <= bat <= 100.0): is_valid = False
            if not (-40.0 <= temp <= 125.0): is_valid = False
            
            if not is_valid:
                print(f"  [Corruption/Loss] Sync lost! (Offset: {pointer}). trying to rescue...")
                recovered = False
                # go forward Byte by byte to find a valid packet header (0x90 0x01 = 400 @ offset 55)
                for scan_ptr in range(pointer + 1, len(file_bytes) - PACKET_SIZE):
                    if file_bytes[scan_ptr+55] == 0x90 and file_bytes[scan_ptr+56] == 0x01:
                        test_packet = np.frombuffer(file_bytes[scan_ptr:scan_ptr+PACKET_SIZE], dtype=combined_packet_dtype)[0]
                        if (0.0 <= test_packet['batteryPercentage'] <= 100.0) and (-40.0 <= test_packet['temperature'] <= 125.0):
                            print(f"  [SUCCESS] {scan_ptr - pointer} sequence synchronized! new Seq: {test_packet['sequence']}")
                            pointer = scan_ptr
                            recovered = True
                            break
                
                if not recovered:
                    print("[Error] No valid packet found. Moving to the next file.")
                    break
                continue
            
            # --- sequence and lost packet control ---
            if last_sequence is not None:
                expected_seq = (int(last_sequence) + 1) % 65536
                if seq != expected_seq:
                    print(f"  [INFO] Data loss (Packet dropped). Expected Seq: {expected_seq}, Received: {seq}")
            
            last_sequence = seq
            packet_idx += 1
            # --- D. IR IMAGE (CSV) ---
            ir_matrix = packet['irFrame'].reshape((12, 16))
            ir_matrix_processed = (ir_matrix / 100) - 40  # Convert to temperature in Celsius
            with open(thermal_csv_path, "a") as f:
                np.savetxt(f, ir_matrix_processed, delimiter=",", fmt="%.2f")

            pointer += PACKET_SIZE

        if pointer < len(file_bytes):
            rem_bytes = len(file_bytes) - pointer
            if rem_bytes > 0:
                print(f"  [WARNING] {rem_bytes} bytes of leftover data (dangling bytes) found at the end of the file.")

print(f"\nProcessing completed!")
print(f"Output folder: {output_base}")
