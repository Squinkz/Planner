# Optimized PNG encoder

Bundled UPNG.js (Photopea, MIT) and pako 1.0.11 (MIT and Zlib) run in
PySide6's QtQml QJSEngine. Include this directory when packaging Planner.
Node.js, Python quantizer packages and network access are not required.

UPNG.js is the upstream master snapshot tested against flat_5.png on 2026-10-17:
https://github.com/photopea/UPNG.js

pako 1.0.11: https://github.com/nodeca/pako/tree/1.0.11

Local compatibility changes move the declarations of pako's loader variable
`u` and UPNG's `inflateRaw` and `M4` ahead of functions that reference them.
Their initialization order and encoding behaviour are unchanged; this avoids
Qt's `qt.qml.usedbeforedeclared` warnings without disabling logging.
Licence notices are in UPNG-LICENSE,
PAKO-LICENSE and the source headers. encode.js is Planner's transfer bridge.
Encoding uses a 256-colour target and preserves image print density.
The bridge transfers pixels in 192 KiB binary ArrayBuffer chunks through Qt's
QByteArray conversion and returns encoded bytes through the same binary bridge.
No base64 strings are used. Temporary chunk buffers are collected between calls.
Planner replaces pako's deflate entry point with Python's native zlib at the same
compression level. PNG filtering and palette decisions remain in UPNG.

Local UPNG performance changes accumulate the same statistics in scalar locals
before building the result arrays, and bulk-copy 8-bit palette indices using
TypedArray.set. Sample order, floating-point arithmetic order, palette size and
quantization decisions are unchanged. Frozen seeded comparisons check palette,
alpha, filtered pixels, decoded pixels and print density. Deflate streams can
differ, while their decompressed PNG data stays identical.
