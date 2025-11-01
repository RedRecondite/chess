# CHESS - Convert Half-tone Effects to Smooth Shadows

A Python module to convert BMP images with checkerboard shadow patterns into PNG images with proper alpha-transparent shadows.

## Background

This tool is designed for converting sprite graphics from games like Dink Smallwood, which used checkerboard (dithered) patterns to simulate transparency before widespread alpha channel support. The checkerboard pattern alternates between solid black pixels and transparent pixels to create the illusion of a semi-transparent shadow.

## Algorithm

Based on the work by Dan Walma (CC0 license), this implementation:
- **Source**: http://www.redrecondite.com/dinkhd/even-better-shadows.patch
- **Discussion**: https://www.dinknetwork.com/forum.cgi?MID=200849

The algorithm:
1. Identifies solid pixels that are part of a checkerboard shadow pattern
2. Converts these pixels to semi-transparent (alpha = 128)
3. Darkens the shadow pixels by 50%
4. Applies anti-aliasing by blending colors into adjacent transparent pixels

## Requirements

- Python 3.6+
- Pillow (PIL fork)

Install dependencies:
```bash
pip install Pillow
```

## Usage

### Command-Line Usage

Convert a single BMP file (white background converted to transparent by default):
```bash
python chess.py input.bmp
```

Specify output filename:
```bash
python chess.py input.bmp output.png
```

Use black as the transparency color instead of white:
```bash
python chess.py input.bmp output.png --transparency-color black
```

Skip transparency color conversion (use when image already has proper alpha channel):
```bash
python chess.py input.bmp output.png --transparency-color none
```

Show help:
```bash
python chess.py --help
```

### As a Python Module

#### Example 1: Convert a file (default: white transparency)
```python
from checkerboard_to_alpha import convert_file

# Convert BMP to PNG with alpha shadows (white becomes transparent)
converted_image = convert_file('sprite.bmp', 'sprite_alpha.png')
```

#### Example 2: Use black as transparency color
```python
from checkerboard_to_alpha import convert_file

# Convert with black background to transparent
converted_image = convert_file('sprite.bmp', 'sprite_alpha.png', transparency_color=0x000000)
```

#### Example 3: Skip transparency conversion
```python
from checkerboard_to_alpha import convert_file

# Skip color-to-transparent conversion (image already has alpha)
converted_image = convert_file('sprite.bmp', 'sprite_alpha.png', transparency_color=None)
```

#### Example 4: Work with image data in memory
```python
from PIL import Image
from checkerboard_to_alpha import convert_checkerboard_to_alpha

# Load an image
image = Image.open('sprite.bmp')

# Convert checkerboard shadows to alpha (white -> transparent by default)
converted_image = convert_checkerboard_to_alpha(image)

# Or specify black as transparency color
converted_image = convert_checkerboard_to_alpha(image, transparency_color=0x000000)

# Save or use the converted image
converted_image.save('output.png')
```

#### Example 5: Batch processing
```python
from pathlib import Path
from checkerboard_to_alpha import convert_file

# Process all BMP files in a directory
input_dir = Path('input_sprites')
output_dir = Path('output_sprites')
output_dir.mkdir(exist_ok=True)

for bmp_file in input_dir.glob('*.bmp'):
    output_file = output_dir / bmp_file.with_suffix('.png').name
    convert_file(bmp_file, output_file)
    print(f"Converted {bmp_file.name}")
```

## How It Works

### Transparency Color Conversion

Many old sprite systems used a specific color (like white `0xffffff` or black `0x000000`) as a "transparency key" instead of proper alpha channels. CHESS first converts this color to actual transparency before detecting checkerboard patterns.

**Supported transparency colors:**
- **White** (`0xffffff`) - Default, most common for Dink Smallwood sprites
- **Black** (`0x000000`) - Alternative used in some sprite sets
- **None** - Skip this step if your image already has proper alpha channel

### Checkerboard Detection

The algorithm identifies shadow pixels by checking if a solid pixel (alpha = 255) is surrounded by transparent pixels. It uses two detection patterns:

1. **Fully surrounded**: Pixel has transparent neighbors on all 4 sides (top, left, bottom, right)
2. **3-sided with corner check**: Pixel has 3 transparent neighbors and passes diagonal checks to avoid false positives at sprite edges

### Shadow Conversion

When a checkerboard shadow pixel is found:
1. The pixel's alpha is set to 128 (semi-transparent)
2. RGB values are halved to darken the shadow
3. Adjacent transparent pixels are "faded":
   - If fully transparent, they're set to black first
   - 1/4 of the shadow pixel's color is added
   - Alpha is increased by 32

This creates smooth anti-aliased shadow edges.

## Example Results

**Before (Checkerboard):**
- Dithered black/transparent pattern
- Looks jagged or pixelated
- Can flicker when shadows overlap

**After (Alpha):**
- Smooth semi-transparent shadow
- Anti-aliased edges
- No flickering

## API Reference

### `convert_color_to_transparent(image, color_hex=0xffffff, tolerance=0)`
Convert a specific color to transparent (alpha=0).

**Parameters:**
- `image` (PIL.Image): Input image (will be converted to RGBA if needed)
- `color_hex` (int): Color to make transparent as hex (e.g., 0xffffff for white, 0x000000 for black)
- `tolerance` (int): Color matching tolerance (0-255), allows for slight color variations

**Returns:**
- PIL.Image: Image with specified color made transparent

### `convert_checkerboard_to_alpha(image, transparency_color=0xffffff)`
Convert an image with checkerboard shadows to alpha transparency.

**Parameters:**
- `image` (PIL.Image): Input image (will be converted to RGBA if needed)
- `transparency_color` (int or None): Hex color to convert to transparent before processing (default: 0xffffff for white, use 0x000000 for black, None to skip)

**Returns:**
- PIL.Image: Converted image with alpha shadows

### `convert_file(input_path, output_path=None, transparency_color=0xffffff)`
Convert a BMP file to PNG with alpha shadows.

**Parameters:**
- `input_path` (str or Path): Path to input BMP file
- `output_path` (str or Path, optional): Path to output PNG file. If not specified, uses same name with .png extension
- `transparency_color` (int or None): Hex color to convert to transparent before processing (default: 0xffffff for white, use 0x000000 for black, None to skip)

**Returns:**
- PIL.Image: Converted image

**Raises:**
- FileNotFoundError: If input file doesn't exist

## Technical Details

- **Alpha limit**: 128 (threshold between transparent and solid)
- **Shadow pixel alpha**: 128 (50% transparent)
- **Shadow darkening**: RGB values divided by 2
- **Edge fade**: Adjacent pixels gain 32 alpha and 1/4 of RGB values

## Testing

Run the included demo script to see examples:
```bash
python demo_usage.py
```

This creates several test images demonstrating the conversion.

## License

This implementation is released under CC0 (Public Domain). Based on the algorithm by Dan Walma, also released under CC0.

## Credits

- Algorithm: Dan Walma
- Original discussion: Dink Network forums
- Python implementation: Claude (Anthropic)
