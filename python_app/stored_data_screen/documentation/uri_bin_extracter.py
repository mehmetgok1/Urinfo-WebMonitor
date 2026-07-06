import numpy as np
import cv2
import os
import csv

# 1. STRUCT TANIMI (sizeof = 24633 bytes)
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
    ('rgbFrame', 'u2', (4096,)),  # 64x64
    ('irFrame', 'u2', (192,))     # 16x12
])

PACKET_SIZE = combined_packet_dtype.itemsize # 24633 bytes

# AYARLAR
session_path = "/media/deso/disk/20260706_233206/"
session_id = os.path.basename(session_path)
output_base = os.path.join("./processed_sessions", session_id)

dirs = {
    "rgb": os.path.join(output_base, "colored_image"),
    "ir": os.path.join(output_base, "irimage"),
    "motion_audio": os.path.join(output_base, "accel_mic"),
    "sensors": os.path.join(output_base, "sensordata")
}
for d in dirs.values(): os.makedirs(d, exist_ok=True)

sensor_csv_path = os.path.join(dirs["sensors"], "all_sensors.csv")
motion_csv_path = os.path.join(dirs["motion_audio"], "accel_mic_stream.csv")

print(f"Oturum işleniyor: {session_id}")

bin_files = sorted([f for f in os.listdir(session_path) if f.endswith(".bin")])

# Küresel sequence takibi (Dosyalar arası süreklilik varsa)
last_sequence = None 

with open(sensor_csv_path, 'w', newline='') as f_sensor, \
     open(motion_csv_path, 'w', newline='') as f_motion:
    
    writer_s = csv.writer(f_sensor)
    writer_m = csv.writer(f_motion)

    writer_s.writerow(["timestamp_ms", "sequence", "battery_pct", "ambLight_M", "PIR", "mmWave_dist", "temp", "humi", "ambLight_S"])
    writer_m.writerow(["timestamp_ms", "accelX", "accelY", "accelZ", "mic"])

    for bin_file in bin_files:
        full_path = os.path.join(session_path, bin_file)
        
        # Dosya boyutunu kontrol et
        file_size = os.path.getsize(full_path)
        expected_packets = file_size // PACKET_SIZE
        print(f"\nDosya: {bin_file} | Boyut: {file_size} bytes | Beklenen Paket: {expected_packets}")

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

            # --- SANITY CHECK (GÜVENİLİRLİK VE HİZALAMA KONTROLÜ) ---
            is_valid = True
            if sample_count != 400: is_valid = False
            if not (0.0 <= bat <= 100.0): is_valid = False
            if not (-40.0 <= temp <= 125.0): is_valid = False
            
            if not is_valid:
                print(f"  [KAYIP/BOZULMA] Senkronizasyon bozuldu! (Offset: {pointer}). Kurtarılıyor...")
                recovered = False
                # Byte byte ileri sararak yeni bir geçerli paket başı ara (0x90 0x01 = 400 @ offset 55)
                for scan_ptr in range(pointer + 1, len(file_bytes) - PACKET_SIZE):
                    if file_bytes[scan_ptr+55] == 0x90 and file_bytes[scan_ptr+56] == 0x01:
                        test_packet = np.frombuffer(file_bytes[scan_ptr:scan_ptr+PACKET_SIZE], dtype=combined_packet_dtype)[0]
                        if (0.0 <= test_packet['batteryPercentage'] <= 100.0) and (-40.0 <= test_packet['temperature'] <= 125.0):
                            print(f"  [BAŞARILI] {scan_ptr - pointer} byte atlanarak senkronizasyon sağlandı! Yeni Seq: {test_packet['sequence']}")
                            pointer = scan_ptr
                            recovered = True
                            break
                
                if not recovered:
                    print("  [HATA] Dosyanın geri kalanında geçerli paket bulunamadı. Sonraki dosyaya geçiliyor.")
                    break
                continue
            
            # --- SEQUENCE VE EKSİK PAKET KONTROLÜ ---
            if last_sequence is not None:
                expected_seq = (last_sequence + 1) % 65536
                if seq != expected_seq:
                    print(f"  [BİLGİ] Veri atlaması (Paket düştü). Beklenen Seq: {expected_seq}, Gelen: {seq}")
            
            last_sequence = seq
            packet_idx += 1

            # --- A. SENSOR DATA (CSV) ---
            writer_s.writerow([ts, seq, packet['batteryPercentage'], packet['ambLight'], 
                               packet['PIRValue'], packet['movingDist'], packet['temperature'], 
                               packet['humidity'], packet['ambientLight_slave']])

            # --- B. ACCEL & MIC (CSV) ---
            for j in range(400):
                writer_m.writerow([ts, packet['accelX_samples'][j], packet['accelY_samples'][j], 
                                   packet['accelZ_samples'][j], packet['microphoneSamples'][j]])

            # --- C. RGB IMAGE (PNG) ---
            try:
                rgb_raw = packet['rgbFrame'].view(np.uint8).reshape((64, 64, 2))
                img_bgr = cv2.cvtColor(rgb_raw, cv2.COLOR_BGR5652BGR)
                large_rgb = cv2.resize(img_bgr, (256, 256), interpolation=cv2.INTER_NEAREST)
                cv2.imwrite(os.path.join(dirs["rgb"], f"rgb_{ts}_{seq}.png"), large_rgb)
            except Exception as e:
                print(f"  [HATA] RGB Frame dönüştürülemedi (Seq: {seq}): {e}")

            # --- D. IR IMAGE (CSV) ---
            ir_path = os.path.join(dirs["ir"], f"ir_{ts}_{seq}.csv")
            ir_matrix = packet['irFrame'].reshape((12, 16))
            np.savetxt(ir_path, ir_matrix, delimiter=",", fmt='%u')

            pointer += PACKET_SIZE

        if pointer < len(file_bytes):
            rem_bytes = len(file_bytes) - pointer
            if rem_bytes > 0:
                print(f"  [UYARI] Dosya sonunda {rem_bytes} byte artık veri (dangling bytes) kaldı.")

print(f"\nİşlem Başarıyla Tamamlandı!")
print(f"Çıktı klasörü: {output_base}")
