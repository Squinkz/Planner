// Planner's binary bridge for Qt QJSEngine. No browser, Node or network access.
var window = {};
var plannerRgba;

// PNG deflation is lossless. Use Python's native zlib at pako's same level,
// while UPNG still chooses the palette, PNG filters and metadata.
pako.deflate = function(data, options) {
    var level = options && options.level !== undefined ? options.level : 6;
    var buffer = data.byteOffset === 0 && data.byteLength === data.buffer.byteLength
        ? data.buffer : data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
    return new Uint8Array(plannerCompression.Deflate(buffer, level));
};

function BeginPngPixels(length) {
    plannerRgba = new Uint8Array(length);
}

function AppendPngPixels(buffer, offset) {
    plannerRgba.set(new Uint8Array(buffer), offset);
}

function EncodePng(width, height, dotsPerMeterX, dotsPerMeterY) {
    var png = UPNG.encode([plannerRgba.buffer], width, height, 256, null,
                          { pHYs: [dotsPerMeterX, dotsPerMeterY, 1] });
    plannerRgba = null;
    return png;
}
