// Planner's bridge for Qt QJSEngine. No browser, Node or network access required.
var window = {};

function EncodePng(pixels, width, height, dotsPerMeterX, dotsPerMeterY) {
    var alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    var padding = pixels.endsWith("==") ? 2 : pixels.endsWith("=") ? 1 : 0;
    var rgba = new Uint8Array(pixels.length / 4 * 3 - padding);
    var position = 0;
    for (var index = 0; index < pixels.length; index += 4) {
        var value = (alphabet.indexOf(pixels[index]) << 18) |
                    (alphabet.indexOf(pixels[index + 1]) << 12) |
                    (Math.max(0, alphabet.indexOf(pixels[index + 2])) << 6) |
                    Math.max(0, alphabet.indexOf(pixels[index + 3]));
        rgba[position++] = value >> 16;
        if (position < rgba.length) rgba[position++] = value >> 8;
        if (position < rgba.length) rgba[position++] = value;
    }
    var png = new Uint8Array(UPNG.encode([rgba.buffer], width, height, 256, null,
                                       { pHYs: [dotsPerMeterX, dotsPerMeterY, 1] }));
    // Bound temporary string size while transferring the encoded bytes to Python.
    var chunks = [], chunk = "";
    for (var index = 0; index < png.length; index += 3) {
        var value = (png[index] << 16) | ((png[index + 1] || 0) << 8) | (png[index + 2] || 0);
        chunk += alphabet[(value >>> 18) & 63] + alphabet[(value >>> 12) & 63] +
                 (index + 1 < png.length ? alphabet[(value >>> 6) & 63] : "=") +
                 (index + 2 < png.length ? alphabet[value & 63] : "=");
        if (chunk.length >= 16384) { chunks.push(chunk); chunk = ""; }
    }
    chunks.push(chunk);
    return chunks.join("");
}
