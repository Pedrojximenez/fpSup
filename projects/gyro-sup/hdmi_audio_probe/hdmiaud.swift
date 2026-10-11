// hdmiaud — 從 HDMI 擷取卡的音訊端錄下原始取樣（給 fpSup-Gyro-HDMI 驗證用）
// 用法:  hdmiaud list
//        hdmiaud rec <裝置名子字串> <秒數> <輸出.raw>
// 輸出為 32-bit float、interleaved、48 kHz、2ch 的裸資料（無標頭）。
import Foundation
import AVFoundation

func listDevices() {
    let ds = AVCaptureDevice.DiscoverySession(
        deviceTypes: [.microphone, .external],
        mediaType: .audio, position: .unspecified).devices
    if ds.isEmpty { print("（找不到音訊裝置）") }
    for d in ds { print("  \(d.localizedName)   [uid \(d.uniqueID)]") }
}

final class Sink: NSObject, AVCaptureAudioDataOutputSampleBufferDelegate {
    let fh: FileHandle
    var bytes = 0
    var fmtPrinted = false
    init(_ fh: FileHandle) { self.fh = fh }
    func captureOutput(_ o: AVCaptureOutput, didOutput sb: CMSampleBuffer,
                       from c: AVCaptureConnection) {
        if !fmtPrinted, let f = CMSampleBufferGetFormatDescription(sb),
           let a = CMAudioFormatDescriptionGetStreamBasicDescription(f)?.pointee {
            print(String(format: "  串流格式: %.0f Hz, %u ch, %u bit, flags 0x%x",
                         a.mSampleRate, a.mChannelsPerFrame, a.mBitsPerChannel, a.mFormatFlags))
            fmtPrinted = true
        }
        guard let bb = CMSampleBufferGetDataBuffer(sb) else { return }
        var len = 0; var ptr: UnsafeMutablePointer<Int8>?
        guard CMBlockBufferGetDataPointer(bb, atOffset: 0, lengthAtOffsetOut: nil,
                                          totalLengthOut: &len, dataPointerOut: &ptr) == noErr,
              let p = ptr else { return }
        fh.write(Data(bytes: p, count: len)); bytes += len
    }
}

let av = CommandLine.arguments
guard av.count >= 2 else { print("用法: hdmiaud list | rec <名稱> <秒> <out.raw>"); exit(1) }

if av[1] == "list" { listDevices(); exit(0) }

guard av[1] == "rec", av.count == 5, let secs = Double(av[3]) else {
    print("用法: hdmiaud rec <名稱子字串> <秒> <out.raw>"); exit(1)
}
let needle = av[2], outPath = av[4]

let devs = AVCaptureDevice.DiscoverySession(
    deviceTypes: [.microphone, .external], mediaType: .audio,
    position: .unspecified).devices
guard let dev = devs.first(where: { $0.localizedName.lowercased().contains(needle.lowercased()) }) else {
    print("找不到符合 '\(needle)' 的裝置。可用:"); listDevices(); exit(2)
}
print("裝置: \(dev.localizedName)")

let sem = DispatchSemaphore(value: 0)
var granted = false
AVCaptureDevice.requestAccess(for: .audio) { ok in granted = ok; sem.signal() }
sem.wait()
guard granted else { print("❌ 麥克風權限被拒 —— 系統設定 → 隱私權 → 麥克風，允許終端機"); exit(3) }

FileManager.default.createFile(atPath: outPath, contents: nil)
guard let fh = FileHandle(forWritingAtPath: outPath) else { print("開不了 \(outPath)"); exit(4) }

let session = AVCaptureSession()
guard let input = try? AVCaptureDeviceInput(device: dev), session.canAddInput(input) else {
    print("❌ 無法加入輸入"); exit(5)
}
session.addInput(input)
let out = AVCaptureAudioDataOutput()
out.audioSettings = [
    AVFormatIDKey: kAudioFormatLinearPCM,
    AVLinearPCMBitDepthKey: 32,
    AVLinearPCMIsFloatKey: true,
    AVLinearPCMIsNonInterleaved: false,
]
let sink = Sink(fh)
out.setSampleBufferDelegate(sink, queue: DispatchQueue(label: "cap"))
guard session.canAddOutput(out) else { print("❌ 無法加入輸出"); exit(6) }
session.addOutput(out)

session.startRunning()
print("錄製 \(secs) 秒…")
Thread.sleep(forTimeInterval: secs)
session.stopRunning()
try? fh.close()
print("寫入 \(outPath)：\(sink.bytes) bytes")
