# fpshell 時代的 IMU / 鏡頭程式實驗(2026-10-06 從 usb-shell-sup/fpshell_tool/camera 搬來)

- `accel_fast.S` / `accel_odr.S` —— MMA8452Q 切 100 Hz
- `gyro_block_hook.S` —— SD 寫入延遲 692 ms 的量測(research/storage/notes/SD_WRITE_LATENCY_MEASURED.md)
- `gyro_stream_task.S` / `gyro_task_probe.S` —— ⚠ OBSOLETE,任務描述元錯誤,不要上機
- `lens_program_shell.S` / `lens_write_shell.S` —— 鏡頭名稱寫成卡上文字檔

IMU snapshot 的現行版在 `fpSup/gyro/imu_snapshot.S`。
