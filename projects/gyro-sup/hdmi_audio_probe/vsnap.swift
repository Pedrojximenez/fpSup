// vsnap — 抓一張擷取卡的影格，回報尺寸與亮度統計（判斷 HDMI 有沒有訊號）
import Foundation
import AVFoundation
import CoreVideo

let devs = AVCaptureDevice.DiscoverySession(
    deviceTypes: [.external, .builtInWideAngleCamera], mediaType: .video, position: .unspecified).devices
for d in devs { print("video: \(d.localizedName)") }
guard let dev = devs.first(where: { $0.localizedName.lowercased().contains("aver") }) else {
    print("找不到 AVerMedia 影像裝置"); exit(2)
}
print("使用: \(dev.localizedName)")
print("目前 activeFormat: \(dev.activeFormat.formatDescription)")

let sem = DispatchSemaphore(value: 0)
var granted = false
AVCaptureDevice.requestAccess(for: .video) { ok in granted = ok; sem.signal() }
sem.wait()
guard granted else { print("❌ 相機權限被拒"); exit(3) }

final class S: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    var done = false
    let sem: DispatchSemaphore
    init(_ s: DispatchSemaphore) { sem = s }
    func captureOutput(_ o: AVCaptureOutput, didOutput sb: CMSampleBuffer, from c: AVCaptureConnection) {
        if done { return }
        guard let pb = CMSampleBufferGetImageBuffer(sb) else { return }
        CVPixelBufferLockBaseAddress(pb, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pb, .readOnly) }
        let w = CVPixelBufferGetWidth(pb), h = CVPixelBufferGetHeight(pb)
        let bpr = CVPixelBufferGetBytesPerRow(pb)
        let fmt = CVPixelBufferGetPixelFormatType(pb)
        let f4 = String(format: "%c%c%c%c", (fmt>>24)&0xff,(fmt>>16)&0xff,(fmt>>8)&0xff,fmt&0xff)
        guard let base = CVPixelBufferGetBaseAddress(pb) else { return }
        let p = base.assumingMemoryBound(to: UInt8.self)
        var sum = 0.0, sum2 = 0.0, cnt = 0.0, mn = 255.0, mx = 0.0
        for y in stride(from: 0, to: h, by: 4) {
            for x in stride(from: 0, to: min(bpr, w*2), by: 8) {
                let v = Double(p[y*bpr + x])
                sum += v; sum2 += v*v; cnt += 1
                mn = min(mn,v); mx = max(mx,v)
            }
        }
        let mean = sum/cnt, sd = (sum2/cnt - mean*mean).squareRoot()
        print(String(format: "影格 %dx%d  pixfmt=%@  取樣 %.0f 點: mean %.1f  sd %.1f  min %.0f  max %.0f",
                     w, h, f4, cnt, mean, sd, mn, mx))
        done = true; sem.signal()
    }
}
let session = AVCaptureSession()
guard let inp = try? AVCaptureDeviceInput(device: dev), session.canAddInput(inp) else { print("❌ 輸入"); exit(4) }
session.addInput(inp)
let out = AVCaptureVideoDataOutput()
let sem2 = DispatchSemaphore(value: 0)
let s = S(sem2)
out.setSampleBufferDelegate(s, queue: DispatchQueue(label: "v"))
session.addOutput(out)
session.startRunning()
_ = sem2.wait(timeout: .now() + 6)
session.stopRunning()
if !s.done { print("❌ 6 秒內沒有影格 —— HDMI 可能無訊號") }
