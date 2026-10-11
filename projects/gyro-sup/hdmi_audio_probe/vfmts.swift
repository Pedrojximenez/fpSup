import Foundation
import AVFoundation
import CoreMedia
let devs = AVCaptureDevice.DiscoverySession(deviceTypes: [.external], mediaType: .video, position: .unspecified).devices
guard let d = devs.first(where: { $0.localizedName.lowercased().contains("aver") }) else { print("no dev"); exit(2) }
print("裝置: \(d.localizedName)  共 \(d.formats.count) 種格式")
func f4(_ c: FourCharCode) -> String {
    String(format:"%c%c%c%c",(c>>24)&0xff,(c>>16)&0xff,(c>>8)&0xff,c&0xff)
}
var seen = Set<String>()
for f in d.formats {
    let fd = f.formatDescription
    let dim = CMVideoFormatDescriptionGetDimensions(fd)
    let st = CMFormatDescriptionGetMediaSubType(fd)
    let fr = f.videoSupportedFrameRateRanges.map { String(format:"%.2f-%.2f",$0.minFrameRate,$0.maxFrameRate) }.joined(separator:",")
    let key = "\(f4(st)) \(dim.width)x\(dim.height) \(fr)"
    if seen.contains(key) { continue }
    seen.insert(key)
    print("  \(f4(st))  \(dim.width)x\(dim.height)   fps \(fr)")
}
