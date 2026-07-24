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


session_path = "/home/deso/delete/Urinfo-WebMonitor/python_app/stored_data_screen/documentation/denem_data/HotWaterVolume/20260724_141650K422Br20/"
items = session_path.split('/')
if items[-1] == "": 
    items.pop(-1)

session_path = "/" + "/".join(items)
session_id = os.path.basename(session_path)
output_base = os.path.join("./processed_sessions", session_id)

# Remove existing folder if present
if os.path.exists(output_base):
    print("Removing existing output folder...")
    shutil.rmtree(output_base)

# Recreate an empty folder to start fresh
os.makedirs(output_base, exist_ok=True)

dirs = {
    "rgb": os.path.join(output_base, "colored_image"),
    "ir": os.path.join(output_base, "irimage"),
    "motion_audio": os.path.join(output_base, "accel_mic"),
    "sensors": os.path.join(output_base, "sensordata")
}
for d in dirs.values(): os.makedirs(d, exist_ok=True)

sensor_csv_path = os.path.join(dirs["sensors"], "all_sensors.csv")
motion_csv_path = os.path.join(dirs["motion_audio"], "accel_mic_stream.csv")

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

with open(sensor_csv_path, 'w', newline='') as f_sensor, \
     open(motion_csv_path, 'w', newline='') as f_motion:
    
    writer_s = csv.writer(f_sensor)
    writer_m = csv.writer(f_motion)

    writer_s.writerow(["timestamp_ms", "sequence", "battery_pct", "ambLight_M", "PIR", "mmWave_dist", "temp", "humi", "ambLight_S"])
    writer_m.writerow(["timestamp_ms","sequence", "accelX", "accelY", "accelZ", "mic"])

    for bin_file in bin_files:
        full_path = os.path.join(session_path, bin_file)
        
        # Dosya boyutunu kontrol et
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

            # --- A. SENSOR DATA (CSV) ---
            writer_s.writerow([ts, seq-first_sequence+1, packet['batteryPercentage'], packet['ambLight'], 
                               packet['PIRValue'], packet['movingDist'], packet['temperature'], 
                               packet['humidity'], packet['ambientLight_slave']])

            # --- B. ACCEL & MIC (CSV) ---
            for j in range(2000):
                if j < 400:
                    writer_m.writerow([ts,seq-first_sequence+1, packet['accelX_samples'][j], packet['accelY_samples'][j], 
                                       packet['accelZ_samples'][j], packet['microphoneSamples'][j]])
                else:
                    writer_m.writerow([ts, seq-first_sequence+1,0, 0, packet['microphoneSamples'][j]])  # 400 accel sample + 1600 mic sample

            # --- C. RGB IMAGE (PNG) ---
            try:
                rgb_raw = packet['rgbFrame'].view(np.uint8).reshape((64, 64, 2))
                img_bgr = cv2.cvtColor(rgb_raw, cv2.COLOR_BGR5652BGR)
                large_rgb = cv2.resize(img_bgr, (256, 256), interpolation=cv2.INTER_NEAREST)
                cv2.imwrite(os.path.join(dirs["rgb"], f"rgb_{ts}_{seq-first_sequence+1}.png"), large_rgb)
            except Exception as e:
                print(f"[Error] RGB Frame can't be converted to image(Seq: {seq}): {e}")

            # --- D. IR IMAGE (CSV) ---
            ir_path = os.path.join(dirs["ir"], f"ir_{ts}_{seq-first_sequence+1}.csv")
            ir_matrix = packet['irFrame'].reshape((12, 16))
            ir_matrix_processed = (ir_matrix / 100) - 40  # Convert to temperature in Celsius
            np.savetxt(ir_path, ir_matrix_processed, delimiter=",", fmt='%.2f')

            pointer += PACKET_SIZE

        if pointer < len(file_bytes):
            rem_bytes = len(file_bytes) - pointer
            if rem_bytes > 0:
                print(f"  [WARNING] {rem_bytes} bytes of leftover data (dangling bytes) found at the end of the file.")

print(f"\nProcessing completed!")
print(f"Output folder: {output_base}")
