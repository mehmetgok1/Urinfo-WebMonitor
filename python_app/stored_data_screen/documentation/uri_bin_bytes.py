import numpy as np
import os

# Your exact struct definition
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
    ('microphoneSamples', 'u2', (400,)),
    ('rgbFrame', 'u2', (4096,)),  
    ('irFrame', 'u2', (192,))     
])

PACKET_SIZE = combined_packet_dtype.itemsize # 24633 bytes

# Calculate internal byte offsets for the report header
offsets = {name: combined_packet_dtype.fields[name][1] for name in combined_packet_dtype.names}

session_path = "/media/deso/disk/20260706_233206/"
report_path = "./packet_boundary_report.txt"

bin_files = sorted([f for f in os.listdir(session_path) if f.endswith(".bin")])

print(f"Analyzing binaries to generate boundary text report...")

with open(report_path, 'w', encoding='utf-8') as report:
    report.write("==================================================================\n")
    report.write("                 BINARY STRUCT BOUNDARY REPORT                   \n")
    report.write(f"  Target Struct Size: {PACKET_SIZE} bytes\n")
    report.write("==================================================================\n\n")

    for bin_file in bin_files:
        full_path = os.path.join(session_path, bin_file)
        file_size = os.path.getsize(full_path)
        
        report.write(f"\nFILE: {bin_file} (Total Size: {file_size} bytes)\n")
        report.write("-" * 80 + "\n")
        
        with open(full_path, 'rb') as f:
            file_bytes = f.read()
            
        pointer = 0
        packet_count = 0
        
        while pointer <= (len(file_bytes) - PACKET_SIZE):
            packet_bytes = file_bytes[pointer:pointer + PACKET_SIZE]
            packet = np.frombuffer(packet_bytes, dtype=combined_packet_dtype)[0]
            
            # Sanity Checks
            seq = packet['sequence']
            ts = packet['timestamp_ms']
            bat = packet['batteryPercentage']
            temp = packet['temperature']
            sample_count = packet['accelSampleCount']
            
            is_valid = True
            if sample_count != 400: is_valid = False
            if not (0.0 <= bat <= 100.0): is_valid = False
            if not (-40.0 <= temp <= 125.0): is_valid = False

            if not is_valid:
                report.write(f"[⚠️ CORRUPTION DETECTED] Lost sync at offset {pointer}.\n")
                report.write(f"  Scanning byte-by-byte for next valid sequence frame...\n")
                
                recovered = False
                for scan_ptr in range(pointer + 1, len(file_bytes) - PACKET_SIZE):
                    if file_bytes[scan_ptr+55] == 0x90 and file_bytes[scan_ptr+56] == 0x01:
                        t_packet = np.frombuffer(file_bytes[scan_ptr:scan_ptr+PACKET_SIZE], dtype=combined_packet_dtype)[0]
                        if (0.0 <= t_packet['batteryPercentage'] <= 100.0) and (-40.0 <= t_packet['temperature'] <= 125.0):
                            report.write(f"  [✅ RECOVERED] Skipped {scan_ptr - pointer} broken bytes. Found valid packet at offset {scan_ptr} (Seq: {t_packet['sequence']}).\n")
                            report.write("  " + "." * 60 + "\n")
                            pointer = scan_ptr
                            recovered = True
                            break
                
                if not recovered:
                    report.write("  [❌ FATAL] Could not find any more continuous sequences. End of scan.\n")
                    break
                continue
            
            # Print a clean, readable overview block for this packet boundary
            report.write(f"[PACKET {packet_count:03d}] Valid Alignment at File Offset: {pointer} to {pointer + PACKET_SIZE} bytes\n")
            report.write(f"  ├── [Offset {offsets['sequence']:4d}] sequence:      {seq}\n")
            report.write(f"  ├── [Offset {offsets['timestamp_ms']:4d}] timestamp_ms:  {ts} ms\n")
            report.write(f"  ├── [Offset {offsets['batteryPercentage']:4d}] battery_pct:  {bat:.2f}%\n")
            report.write(f"  ├── [Offset {offsets['temperature']:4d}] temperature:  {temp:.2f} °C\n")
            report.write(f"  ├── [Offset {offsets['humidity']:4d}] humidity:     {packet['humidity']:.2f}%\n")
            report.write(f"  ├── [Offset {offsets['accelX_samples']:4d}] Accel Arrays:  Starts here (400 samples x 3 axes)\n")
            report.write(f"  ├── [Offset {offsets['microphoneSamples']:4d}] Mic Array:    Starts here (400 samples)\n")
            report.write(f"  ├── [Offset {offsets['rgbFrame']:4d}] RGB Frame:    Starts here (4096 samples)\n")
            report.write(f"  └── [Offset {offsets['irFrame']:4d}] IR Frame:     Starts here (192 samples)\n")
            
            # Optional: Peek at the first 3 elements of arrays to ensure they aren't zeroed/garbage
            report.write(f"  🔬 Array Peek -> AccelX[0..2]: {packet['accelX_samples'][:3].tolist()} | Mic[0..2]: {packet['microphoneSamples'][:3].tolist()}\n")
            report.write("  " + "." * 60 + "\n")
            
            # Move forward by full packet
            pointer += PACKET_SIZE
            packet_count += 1
            
        # Catch remaining dangling bytes that couldn't form a full packet
        if pointer < len(file_bytes):
            rem_bytes = len(file_bytes) - pointer
            report.write(f"\n⚠️  CRITICAL: Found {rem_bytes} dangling bytes at the end of {bin_file} (Offset {pointer} to {len(file_bytes)}).\n")
            report.write(f"  This indicates an incomplete packet or mid-stream corruption slice!\n")
            report.write(f"  Raw Hex snippet of corrupt tail: {file_bytes[pointer:pointer+32].hex().upper()}\n")

print(f"Report successfully saved to: {report_path}")
