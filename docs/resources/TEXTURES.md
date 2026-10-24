# Composite textures

Normal-map resources live directly in `textures/` and are enumerated at startup.
Restart after adding or renaming resources. The PNG compositor consumes the
resolved mapping and lighting defaults described below. For operating its controls,
see [Exporting and printing](../../planner-main/docs/help/export.md).

## Image format

Use **DirectX (DX) normal maps**, preferably lossless **8-bit RGB PNG**.
Other image formats supported by Qt can also load. Images are converted to
8-bit channels and must contain at most **4,194,304 pixels** (2048 × 2048,
for example). Rectangular images and arbitrary dimensions are supported within this limit.

Planner uses red for the horizontal normal component and green for the vertical
component. At angle 0°, low green produces highlights
and high green produces shadows. A flat normal is approximately RGB
**(128, 128, 255)**. Convert grayscale height maps to normal maps before use.
Use seamless images for tiled textures.

## Filename format

Ambient occlusion maps are optional companions named `name_ao.png`, without the
normal map's mapping or lighting suffixes. For example, `linen_ao.png` accompanies
`linen_t2_5_5_333_10.png`. Use grayscale AO with white for unoccluded areas.
After normal lighting, AO multiplies the result with the same tiling or stretch
placement. Its opacity follows the overall Strength slider. AO companions apply
automatically to their matching texture, using their color channels for intensity.
AO resolution may differ from its normal map: it is resampled to the normal's
dimensions before compositing so both maps cover the same area and stay aligned.

```text
name_mapping_strength_highlights_midtones_shadows.png
```

For example:

```text
linen_t2_5_5_333_10.png
```

This displays as **Linen**, tiles at scale **2**, and defaults to strength **0.5**,
highlights **0.5**, midtones **0.333**, and shadows **1.0**. Underscores in the name
become spaces. A name such as `leather_1` can include numbers.

### Mapping

| Suffix | Behavior |
| --- | --- |
| `t2` | Tile at scale 2 |
| `t0.5` | Tile at scale 0.5 |
| `t` or `t1` | Tile at scale 1 |
| `s` | Stretch the image across the entire export |
| No suffix | Tile at scale 1 |

The number after `t` is an ordinary positive decimal. A numeric suffix without `t`, such as `_2`,
also means tile at scale 2; use the explicit `t` form to avoid ambiguity.

### Lighting defaults

The four lighting values are optional **as a complete group**, in this order:
**Strength, Highlights, Midtones, Shadows**. They range from 0 to 1.

Digits imply a leading `0.`, with **`10` reserved for 1.0**:

| Filename value | Slider value |
| --- | --- |
| `0` | 0 |
| `01` | 0.01 |
| `1` | 0.1 |
| `25` | 0.25 |
| `5` | 0.5 |
| `75` | 0.75 |
| `333` | 0.333 |
| `10` | 1.0 |

Examples:

```text
paper_t1.5_10_65_5_10.png
paper_s_5_5_5_3.png
paper_t2.png
paper.png
```

Omitting the four lighting values selects defaults of **0.5, 1, 1, 1**. Angle defaults
to **0°**. These values initialize a texture selection and its reset defaults;
project export overrides store subsequent adjustments.

Decimal notation is supported. If **any of the four lighting values
contains a decimal point**, all four are read as ordinary numbers. For example,
`paper_t2_0.5_0.75_0.5_1.png` uses strength 0.5 and shadows 1.0. Use one notation consistently within a filename.

## Sampling ratio

Tiled sampling uses **source texture pixels per output pixel**. Filename scales
must be positive; zero is reserved for bypassing compositing in an export override.
Sampling filters handle scale changes. For adjusting the control and comparing
tile sizes, see [Exporting and printing](../../planner-main/docs/help/export.md).

The export schema accepts scales from **0 to 4**. Stretch sampling maps one
image to the complete output; tiled sampling uses the ratio above.

For a tile covering a specified distance **in drawing metres**:

```text
scale = texture width in pixels / (tile width in metres × export px/m)
```

For a tile covering a specified distance **on the printed page**:

```text
scale = texture width in pixels × 0.0254 / (tile width in metres × print DPI)
```

For example, a 1024 × 1024 texture covering 25 × 25 cm on paper at 300 DPI
requires a sampling ratio of **0.3468**. Physical paper dimensions and drawing
dimensions differ by the plan's printed scale. The formulas assume the finished
export is reproduced at its recorded physical size.
