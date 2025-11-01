# CHESS - Quick Start Guide

**Convert Half-tone Effects to Smooth Shadows**

## Installation

1. Ensure Python 3.6+ is installed
2. Install Pillow:
   ```bash
   pip install Pillow
   ```

## Command-Line Usage

**Convert a single file (white background → transparent by default):**
```bash
python chess.py sprite.bmp
# Creates: sprite.png
```

**Use black as transparency color:**
```bash
python chess.py sprite.bmp sprite.png --transparency-color black
```

**Skip transparency conversion:**
```bash
python chess.py sprite.bmp sprite.png --transparency-color none
```

**Specify output filename:**
```bash
python chess.py input.bmp output.png
```

**Show help:**
```bash
python chess.py --help
```

## Python Module Usage

**Basic conversion (white → transparent):**
```python
from checkerboard_to_alpha import convert_file

# Convert BMP to PNG (white becomes transparent by default)
converted_image = convert_file('sprite.bmp', 'sprite_alpha.png')
```

**Use black as transparency color:**
```python
from checkerboard_to_alpha import convert_file

converted_image = convert_file('sprite.bmp', 'sprite_alpha.png', 
                               transparency_color=0x000000)
```

**Work with image objects:**
```python
from PIL import Image
from checkerboard_to_alpha import convert_checkerboard_to_alpha

# Load image
img = Image.open('sprite.bmp')

# Convert (white → transparent by default)
result = convert_checkerboard_to_alpha(img)

# Or use black as transparency
result = convert_checkerboard_to_alpha(img, transparency_color=0x000000)

# Save
result.save('output.png')
```

**Batch process directory:**
```python
from pathlib import Path
from checkerboard_to_alpha import convert_file

for bmp_file in Path('sprites').glob('*.bmp'):
    convert_file(bmp_file, f'output/{bmp_file.stem}.png')
```

## What it Does

**Before:** Checkerboard shadow pattern
```
█░█░█░█░   (alternating solid/transparent pixels)
░█░█░█░█
█░█░█░█░
```

**After:** Smooth alpha transparency
```
▓▓▓▓▓▓▓▓   (all pixels semi-transparent at alpha=128)
▓▓▓▓▓▓▓▓
▓▓▓▓▓▓▓▓
```

## Test Examples

Run the demo to see it in action:
```bash
python demo_usage.py
```

This creates:
- `test_checkerboard.bmp` - Original with checkerboard
- `test_output.png` - Converted with alpha
- `example3_before.png` - Before conversion
- `example3_after.png` - After conversion

## Verification

The conversion successfully transforms:
- Checkerboard pixels (alternating 255/0 alpha) → Smooth shadow (128 alpha)
- Adds anti-aliasing to shadow edges
- Preserves sprite colors while creating proper transparency

Confirmed working with visual inspection and pixel-level verification!
