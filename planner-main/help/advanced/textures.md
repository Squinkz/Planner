# Adding custom textures

To add your own textures to Planner, stick a normal map and optionally
a companion ambient occlusion map into the `textures/` folder. You need to restart Planner
to see the new texture.

The name of the texture seen in Planner is taken from the filename. Names are
automatically formatted with capitals, so "old_paper" becomes "Old Paper" inside Planner.

You can specify how Planner should read the texture by appending characters to the filename.

## Filename

### Mapping

After the texture's name and an underscore, use a `t` or an `s` to specify whether the texture
should **tile** or **stretch** across the canvas. If set to tile, you can add a number to specify the
tiling ratio. A tiling ratio of `1` means each source pixel of the normal map by default occupies
one pixel of the exported canvas. Keep ratios above `1` to maintain texture clarity.

Example:

| Filename | Name | Mapping (normal map px : canvas pixels) |
|---|---|---|
| `smooth_card_t1` | **Smooth Card** | Tiles at 1:1 |
| `wrinkled_paper_t1.35` | **Wrinkled Paper** | Tiles at 1.35:1 |
| `linen_t2` | **Linen** | Tiles at 2:1 |

### Lighting

The four lighting values are optional as a complete group, in this order:
**Strength**, **Highlights**, **Midtones**,
**Shadows**. They range from 0 to 1 and represent the default strength of each
lighting component, with **Strength** being an overall multiplier.

Decimal points are assumed, so `5` is read as `0.5` and `33` is read as `0.33`. To specify `1`, use `10`.

Example:

| Filename | Strength | Highlights | Midtones | Shadows |
|---|:---:|:---:|:---:|:---:|
| `smooth_card_t1_6_5_5_10` | 0.6 | 0.5 | 0.5 | 1.0 |
| `print_paper_t1.5_10_65_5_10` | 1.0 | 0.65 | 0.5 | 1.0 |

If lighting values are omitted, **Strength** defaults to `0.5`, and **Highlights**, **Midtones** and **Shadows** default to `1`.

## Format

Planner expects **DirectX** encoded normal maps. That means the green channel should represent `y-`. If your normal map
looks inverted when Planner reads it, you may need to invert the green channel in an image editor.

Planner converts normal maps to **8-bit**, so while higher color depths can be read, you will not see a benefit. Lossless
formats like **PNG** are preferred.

Normal and AO maps are limited to 4,194,304 pixels each, equivalent to a `2048x2048` image.
Rectangular images and arbitrary dimensions are supported within this limit.

## Ambient occlusion

Optional ambient occlusion maps can be supplied alongside the normal map. Ambient occlusion maps are multiplied onto the
canvas after lighting. AO maps just have the suffix `_ao` appended to their name. Their name should match the corresponding
normal map, and both the normal map and the accompaning AO map need to be the same filetype.

Example:

| AO Map | Corresponding Normal | Name |
|---|---|---|
| `cardboard_ao` | `cardboard_t1_75_25_5_5` | **"Cardboard"** |
| `leather_1_ao` | `leather_1_t2_6_45_5_75` | **"Leather 1"** |

Lossless files are recommended, like **PNG**, but other common formats are supported too, such as
**JPG**, **TIFF**, **BMP**, **TGA** and other formats supported by Qt.

> **Note:** *AO maps normally use grayscale, with white for unoccluded areas and darker values for stronger occlusion. Planner reads each RGB channel independently, so coloured maps can also produce tinting effects.*

[<< Back to Help](../README.md)