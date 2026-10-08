// macOS 標準の Vision / Core Image だけを使用。追加ダウンロードはしない。
import Foundation
import Vision
import CoreImage
import ImageIO
import UniformTypeIdentifiers
import Darwin

struct Failure: Error, CustomStringConvertible {
    let description: String
    init(_ message: String) { description = message }
}

func cutout(_ input: URL, _ output: String) throws -> [String: String] {
    guard let source = CGImageSourceCreateWithURL(input as CFURL, nil),
          let raw = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        throw Failure("入力画像を読めません")
    }
    guard raw.width * raw.height <= 40_000_000 else {
        throw Failure("画像は4000万画素以内にしてください")
    }
    let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
    let orientation = (properties?[kCGImagePropertyOrientation] as? NSNumber)?.int32Value ?? 1
    // Intel / GPU 計算なし。EXIF の向きを先にそろえ、マスクにも同じ向きを使う。
    let context = CIContext(options: [.useSoftwareRenderer: true])
    let oriented = CIImage(cgImage: raw).oriented(forExifOrientation: orientation)
    let image = oriented.transformed(by: CGAffineTransform(
        translationX: -oriented.extent.minX, y: -oriented.extent.minY))
    guard let cgImage = context.createCGImage(image, from: image.extent) else {
        throw Failure("入力画像の向きをそろえられません")
    }
    let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    var mask: CIImage?
    var method = "foreground"
    var note = ""
    if #available(macOS 14.0, *) {
        do {
            let request = VNGenerateForegroundInstanceMaskRequest()
            request.usesCPUOnly = true
            try handler.perform([request])
            guard let observation = request.results?.first,
                  !observation.allInstances.isEmpty else {
                throw Failure("前景の人物・物・動物が見つかりません")
            }
            let buffer = try observation.generateScaledMaskForImage(
                forInstances: observation.allInstances, from: handler)
            mask = CIImage(cvPixelBuffer: buffer)
        } catch {
            note = "前景マスクが使えません: \(error)"
        }
    } else {
        note = "前景マスクにはmacOS 14以上が必要です"
    }
    if mask == nil {
        // 注目領域は精密な輪郭切り抜きではない。結果にも近似と明記する。
        method = "saliency"
        let request = VNGenerateObjectnessBasedSaliencyImageRequest()
        request.usesCPUOnly = true
        do {
            try handler.perform([request])
            guard let observation = request.results?.first,
                  !(observation.salientObjects ?? []).isEmpty else {
                throw Failure("注目領域も見つかりません")
            }
            mask = CIImage(cvPixelBuffer: observation.pixelBuffer)
        } catch {
            throw Failure("\(note) / 注目領域も使えません: \(error)")
        }
        note += "。注目領域による近似の切り抜きです（輪郭は不正確な場合があります）"
    }
    guard let low = mask else { throw Failure("マスクがありません") }
    let scaled = low.transformed(by: CGAffineTransform(
        scaleX: image.extent.width / low.extent.width,
        y: image.extent.height / low.extent.height)).cropped(to: image.extent)
    let transparent = CIImage(color: CIColor(red: 0, green: 0, blue: 0, alpha: 0))
        .cropped(to: image.extent)
    let cut = image.applyingFilter("CIBlendWithMask", parameters: [
        kCIInputBackgroundImageKey: transparent, kCIInputMaskImageKey: scaled])
    guard let final = context.createCGImage(cut, from: image.extent) else {
        throw Failure("PNG画像を作れません")
    }
    // データを完成させてから O_EXCL で開く。既存ファイル・リンクは上書きしない。
    let data = NSMutableData()
    guard let writer = CGImageDestinationCreateWithData(
        data, UTType.png.identifier as CFString, 1, nil) else {
        throw Failure("PNGの保存先を作れません")
    }
    CGImageDestinationAddImage(writer, final, nil)
    guard CGImageDestinationFinalize(writer) else { throw Failure("PNGの変換に失敗しました") }
    let fd = open(output, O_WRONLY | O_CREAT | O_EXCL, mode_t(0o600))
    guard fd >= 0 else { throw Failure("出力先を新規作成できません（上書き禁止）: \(errno)") }
    defer { close(fd) }
    var offset = 0
    while offset < data.length {
        let count = write(fd, data.bytes.advanced(by: offset), data.length - offset)
        if count < 0 && errno == EINTR { continue }
        guard count > 0 else { throw Failure("PNGの書き込みに失敗しました: \(errno)") }
        offset += count
    }
    return ["method": method, "note": note]
}

do {
    guard CommandLine.arguments.count == 3 else {
        throw Failure("使い方: haikei 入力画像 出力.png")
    }
    let info = try cutout(URL(fileURLWithPath: CommandLine.arguments[1]), CommandLine.arguments[2])
    let data = try JSONSerialization.data(withJSONObject: info, options: [.sortedKeys])
    print(String(decoding: data, as: UTF8.self))
} catch {
    FileHandle.standardError.write(Data("背景除去に失敗: \(error)\n".utf8))
    exit(1)
}
