#!/usr/bin/env python3
"""
CHESS - Convert Half-tone Effects to Smooth Shadows

Converts BMP images with checkerboard shadow patterns to images with 
proper alpha-transparent shadows.

Based on the algorithm by Dan Walma (CC0 license):
http://www.redrecondite.com/dinkhd/even-better-shadows.patch
https://www.dinknetwork.com/forum.cgi?MID=200849

Author: Claude (Anthropic)
License: CC0 (Public Domain)
"""

import sys
import argparse
from PIL import Image
import numpy as np
from pathlib import Path


# Alpha threshold - pixels with alpha < this are considered transparent
ALPHA_LIMIT = 128


def convert_color_to_transparent(image, color_hex=0xffffff, tolerance=0):
    """
    Convert a specific color to transparent (alpha=0).
    
    This is useful for sprites that use a specific color (like white or black)
    as a transparency key, which needs to be converted to actual alpha transparency
    before applying the checkerboard shadow algorithm.
    
    Args:
        image: PIL Image object (will be converted to RGBA if needed)
        color_hex: Color to make transparent as hex (e.g., 0xffffff for white, 0x000000 for black)
        tolerance: Color matching tolerance (0-255), allows for slight color variations
        
    Returns:
        PIL Image object with specified color made transparent
    """
    # Ensure we have an RGBA image
    if image.mode != 'RGBA':
        image = image.convert('RGBA')
    
    # Convert to numpy array
    pixel_array = np.array(image, dtype=np.uint8)
    height, width = pixel_array.shape[:2]
    
    # Extract target RGB values from hex
    target_r = (color_hex >> 16) & 0xFF
    target_g = (color_hex >> 8) & 0xFF
    target_b = color_hex & 0xFF
    
    # Find pixels matching the target color (within tolerance)
    if tolerance == 0:
        # Exact match (faster)
        mask = (pixel_array[:, :, 0] == target_r) & \
               (pixel_array[:, :, 1] == target_g) & \
               (pixel_array[:, :, 2] == target_b)
    else:
        # Match with tolerance
        r_match = np.abs(pixel_array[:, :, 0].astype(int) - target_r) <= tolerance
        g_match = np.abs(pixel_array[:, :, 1].astype(int) - target_g) <= tolerance
        b_match = np.abs(pixel_array[:, :, 2].astype(int) - target_b) <= tolerance
        mask = r_match & g_match & b_match
    
    # Set alpha to 0 for matching pixels
    pixel_array[mask, 3] = 0
    
    # Convert back to PIL Image
    return Image.fromarray(pixel_array, 'RGBA')


def is_checkerboard_alpha_shadow_pixel(pixel_array, x, y, width, height):
    """
    Check if a pixel at (x, y) should be considered a transparent shadow pixel.
    
    Args:
        pixel_array: numpy array of RGBA pixels
        x, y: coordinates to check
        width, height: image dimensions
        
    Returns:
        True if the pixel is transparent or on the edge, False otherwise
    """
    if x < 0 or x >= width or y < 0 or y >= height:
        return True
    return pixel_array[y, x, 3] < ALPHA_LIMIT


def is_checkerboard_solid_shadow_pixel(pixel_array, x, y, width, height):
    """
    Determine if a pixel is part of a checkerboard shadow pattern.
    
    A pixel is considered a checkerboard shadow pixel if:
    1. It's fully opaque (alpha = 255)
    2. It's surrounded by transparent pixels (4 adjacent or 3 with corner checks)
    
    Args:
        pixel_array: numpy array of RGBA pixels
        x, y: coordinates to check
        width, height: image dimensions
        
    Returns:
        True if this is a checkerboard shadow pixel
    """
    # Must be a solid pixel
    if pixel_array[y, x, 3] != 255:
        return False
    
    # Check adjacent pixels
    top_alpha = is_checkerboard_alpha_shadow_pixel(pixel_array, x, y - 1, width, height)
    left_alpha = is_checkerboard_alpha_shadow_pixel(pixel_array, x - 1, y, width, height)
    bottom_alpha = is_checkerboard_alpha_shadow_pixel(pixel_array, x, y + 1, width, height)
    right_alpha = is_checkerboard_alpha_shadow_pixel(pixel_array, x + 1, y, width, height)
    
    adjacent_alpha_count = sum([top_alpha, left_alpha, bottom_alpha, right_alpha])
    
    if adjacent_alpha_count == 4:
        # Surrounded by alpha pixels - definitely a shadow pixel
        return True
    elif adjacent_alpha_count == 3:
        # Need to check diagonal pixels to avoid false positives at sprite edges
        # When a shadow meets a sprite edge, we want shadow pixels but not sprite pixels
        
        def check_corner_alpha(cx, cy):
            """Check if corner pixel is transparent"""
            if cx < 0 or cx >= width or cy < 0 or cy >= height:
                return True
            return pixel_array[cy, cx, 3] != 255
        
        top_left_alpha = check_corner_alpha(x - 1, y - 1)
        top_right_alpha = check_corner_alpha(x + 1, y - 1)
        bottom_left_alpha = check_corner_alpha(x - 1, y + 1)
        bottom_right_alpha = check_corner_alpha(x + 1, y + 1)
        
        # Check each direction - if adjacent pixel is transparent AND 
        # both corners on that side are solid, this is likely a sprite edge, not shadow
        if top_alpha and not top_left_alpha and not top_right_alpha:
            return True
        elif left_alpha and not top_left_alpha and not bottom_left_alpha:
            return True
        elif right_alpha and not top_right_alpha and not bottom_right_alpha:
            return True
        elif bottom_alpha and not bottom_left_alpha and not bottom_right_alpha:
            return True
    
    return False


def fade_checkerboard_alpha_pixel(pixel_array, x, y, source_pixel, width, height):
    """
    Fade a transparent pixel by adding color from adjacent shadow pixel.
    
    Args:
        pixel_array: numpy array of RGBA pixels (will be modified)
        x, y: coordinates of pixel to fade
        source_pixel: RGBA values of the shadow pixel to blend from
        width, height: image dimensions
    """
    if x < 0 or x >= width or y < 0 or y >= height:
        return
    
    dest_pixel = pixel_array[y, x]
    
    # Only fade pixels that are currently transparent
    if dest_pixel[3] < ALPHA_LIMIT:
        # If fully transparent, set to black first
        if dest_pixel[3] == 0:
            dest_pixel[0] = 0
            dest_pixel[1] = 0
            dest_pixel[2] = 0
        
        # Add 1/4 of source color and set alpha to consistent shadow level
        dest_pixel[0] = min(255, dest_pixel[0] + source_pixel[0] // 4)
        dest_pixel[1] = min(255, dest_pixel[1] + source_pixel[1] // 4)
        dest_pixel[2] = min(255, dest_pixel[2] + source_pixel[2] // 4)
        dest_pixel[3] = ALPHA_LIMIT  # Always 128 for shadow pixels, regardless of solid adjacency


def convert_checkerboard_to_alpha(image, transparency_color=0xffffff):
    """
    Convert checkerboard shadow pattern to alpha transparency.
    
    Args:
        image: PIL Image object (will be converted to RGBA if needed)
        transparency_color: Hex color to convert to transparent before processing
                          (default: 0xffffff for white, use 0x000000 for black, None to skip)
        
    Returns:
        PIL Image object with alpha shadows
    """
    # First, convert the transparency color to alpha if specified
    if transparency_color is not None:
        image = convert_color_to_transparent(image, transparency_color)
    else:
        # Ensure we have an RGBA image
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
    
    # Convert to numpy array for easier manipulation
    pixel_array = np.array(image, dtype=np.uint8)
    height, width = pixel_array.shape[:2]
    
    # Find and convert checkerboard shadow pixels
    for y in range(height):
        for x in range(width):
            if is_checkerboard_solid_shadow_pixel(pixel_array, x, y, width, height):
                # This is a shadow pixel - make it semi-transparent
                # and darken it
                pixel_array[y, x, 3] = ALPHA_LIMIT
                pixel_array[y, x, 0] //= 2
                pixel_array[y, x, 1] //= 2
                pixel_array[y, x, 2] //= 2
                
                # Store original color for blending
                source_pixel = pixel_array[y, x].copy()
                
                # Fade adjacent transparent pixels
                fade_checkerboard_alpha_pixel(pixel_array, x, y - 1, source_pixel, width, height)
                fade_checkerboard_alpha_pixel(pixel_array, x - 1, y, source_pixel, width, height)
                fade_checkerboard_alpha_pixel(pixel_array, x, y + 1, source_pixel, width, height)
                fade_checkerboard_alpha_pixel(pixel_array, x + 1, y, source_pixel, width, height)
    
    # Convert back to PIL Image
    return Image.fromarray(pixel_array, 'RGBA')


def convert_file(input_path, output_path=None, transparency_color=0xffffff):
    """
    Convert a BMP file with checkerboard shadows to PNG with alpha shadows.
    
    Args:
        input_path: Path to input BMP file
        output_path: Path to output PNG file (optional, defaults to same name with .png extension)
        transparency_color: Hex color to convert to transparent before processing
                          (default: 0xffffff for white, use 0x000000 for black, None to skip)
        
    Returns:
        PIL Image object with converted shadows
    """
    input_path = Path(input_path)
    
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    # Load the image
    image = Image.open(input_path)
    
    # Convert checkerboard shadows to alpha
    converted_image = convert_checkerboard_to_alpha(image, transparency_color)
    
    # Determine output path
    if output_path is None:
        output_path = input_path.with_suffix('.png')
    else:
        output_path = Path(output_path)
    
    # Save as PNG
    converted_image.save(output_path, 'PNG')
    
    print(f"Converted {input_path} -> {output_path}")
    
    return converted_image


def main():
    """Command-line interface"""
    parser = argparse.ArgumentParser(
        description='CHESS - Convert Half-tone Effects to Smooth Shadows',
        epilog='Converts BMP files with checkerboard shadows to PNG with alpha transparency.'
    )
    
    parser.add_argument('input', help='Input BMP file path')
    parser.add_argument('output', nargs='?', help='Output PNG file path (optional, defaults to input name with .png extension)')
    parser.add_argument('-t', '--transparency-color', 
                        choices=['white', 'black', 'none'],
                        default='white',
                        help='Color to convert to transparent before processing (default: white)')
    
    args = parser.parse_args()
    
    # Convert transparency color argument to hex value
    transparency_map = {
        'white': 0xffffff,
        'black': 0x000000,
        'none': None
    }
    transparency_color = transparency_map[args.transparency_color]
    
    try:
        convert_file(args.input, args.output, transparency_color)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
