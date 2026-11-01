"""Zero-copy stored-channel comparisons; callers retain the owning QImages."""
from planner_app.numpy_runtime import LoadNumPy


def ImageChannels(image):
    if image.depth() != 32:
        raise ValueError("Stored-channel comparisons require a 32-bit image")
    np = LoadNumPy()
    # Respect row padding, including images backed by externally supplied data.
    return np.ndarray((image.height(), image.width(), 4), dtype = np.uint8,
        buffer = image.constBits(), strides = (image.bytesPerLine(), 4, 1))


def ChangedPixels(first, second):
    if first.size() != second.size() or first.format() != second.format():
        raise ValueError("Compared images must have matching sizes and formats")
    np = LoadNumPy()
    left, right = ImageChannels(first), ImageChannels(second)
    changed = np.flatnonzero(left.view(np.uint32)[:, :, 0] != right.view(np.uint32)[:, :, 0])
    rows, columns = changed // first.width(), changed % first.width()
    # Widen before subtraction to avoid unsigned wraparound. Gather only changed
    # pixels rather than creating two full-image signed copies for sparse errors.
    differences = np.abs(left[rows, columns].astype(np.int16) - right[rows, columns])
    return changed, differences.max(axis = 1, initial = 0)
