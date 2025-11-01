#!/usr/bin/env python3
"""
Demo script for CHESS (Convert Half-tone Effects to Smooth Shadows)
Shows how to use the checkerboard_to_alpha module.
"""

from PIL import Image
import numpy as np
from checkerboard_to_alpha import convert_checkerboard_to_alpha, convert_file


def create_test_checkerboard_bmp():
    """
    Create a test BMP image with a checkerboard shadow pattern.
    
    This simulates the type of image that would come from Dink Smallwood,
    where shadows are represented as a checkerboard pattern.
    """
    # Create a 100x100 image
    width, height = 100, 100
    
    # Create RGBA array
    img_array = np.zeros((height, width, 4), dtype=np.uint8)
    
    # Fill with transparent background
    img_array[:, :, 3] = 0
    
    # Create a "sprite" - a red circle in the upper portion
    center_y, center_x = 30, 50
    for y in range(height):
        for x in range(width):
            dist = np.sqrt((x - center_x)**2 + (y - center_y)**2)
            if dist < 20:
                img_array[y, x] = [200, 50, 50, 255]  # Red sprite
    
    # Create a checkerboard shadow pattern below the sprite
    # Shadows in Dink are black checkerboard patterns
    shadow_start_y = 50
    shadow_end_y = 80
    shadow_start_x = 30
    shadow_end_x = 70
    
    for y in range(shadow_start_y, shadow_end_y):
        for x in range(shadow_start_x, shadow_end_x):
            # Checkerboard pattern: alternate pixels
            if (x + y) % 2 == 0:
                img_array[y, x] = [0, 0, 0, 255]  # Black solid pixel
            else:
                img_array[y, x] = [0, 0, 0, 0]  # Transparent pixel
    
    # Create PIL Image
    img = Image.fromarray(img_array, 'RGBA')
    
    # Save as BMP
    img.save('test_checkerboard.bmp', 'BMP')
    print("Created test_checkerboard.bmp with checkerboard shadow pattern")
    
    return img


def example_1_command_line_usage():
    """Example 1: Using from command line"""
    print("\n" + "="*60)
    print("Example 1: Command-line usage")
    print("="*60)
    print("\nTo convert a BMP file from command line:")
    print("  python chess.py input.bmp")
    print("  python chess.py input.bmp output.png")
    print("\nThis will create a PNG file with alpha transparency.")


def example_2_import_as_module():
    """Example 2: Using as an imported module"""
    print("\n" + "="*60)
    print("Example 2: Import as module - convert_file function")
    print("="*60)
    
    # Create test image
    create_test_checkerboard_bmp()
    
    # Use the module to convert it
    print("\nConverting using convert_file()...")
    converted_image = convert_file('test_checkerboard.bmp', 'test_output.png')
    print("✓ Conversion complete!")
    print(f"  Input:  test_checkerboard.bmp")
    print(f"  Output: test_output.png")


def example_3_raw_image_data():
    """Example 3: Working with raw image data in memory"""
    print("\n" + "="*60)
    print("Example 3: Import as module - convert_checkerboard_to_alpha function")
    print("="*60)
    
    # Create a test image
    print("\nCreating test image in memory...")
    width, height = 50, 50
    img_array = np.zeros((height, width, 4), dtype=np.uint8)
    
    # Add a simple checkerboard shadow in the middle
    for y in range(20, 40):
        for x in range(15, 35):
            if (x + y) % 2 == 0:
                img_array[y, x] = [0, 0, 0, 255]  # Black solid
            else:
                img_array[y, x] = [0, 0, 0, 0]    # Transparent
    
    original_image = Image.fromarray(img_array, 'RGBA')
    
    # Convert using the function
    print("Converting checkerboard to alpha...")
    converted_image = convert_checkerboard_to_alpha(original_image)
    
    # Save for comparison
    original_image.save('example3_before.png')
    converted_image.save('example3_after.png')
    
    print("✓ Conversion complete!")
    print("  Before: example3_before.png (checkerboard pattern)")
    print("  After:  example3_after.png (alpha transparency)")


def example_4_transparency_colors():
    """Example 4: Using different transparency colors"""
    print("\n" + "="*60)
    print("Example 4: Transparency color options")
    print("="*60)
    
    print("\nCHESS supports converting a specific color to transparent")
    print("before applying the checkerboard algorithm.")
    print("\nSupported options:")
    print("  - white (0xffffff) - Default, most common")
    print("  - black (0x000000) - Alternative")
    print("  - none - Skip transparency conversion")
    
    print("\n--- White background example ---")
    print("Creating sprite with white background and black shadows...")
    
    # Create image with white background
    width, height = 60, 60
    img_array = np.zeros((height, width, 4), dtype=np.uint8)
    img_array[:, :] = [255, 255, 255, 255]  # White background
    
    # Add sprite
    for y in range(20, 30):
        for x in range(25, 35):
            img_array[y, x] = [200, 50, 50, 255]  # Red sprite
    
    # Add black checkerboard shadow
    for y in range(35, 50):
        for x in range(20, 40):
            if (x + y) % 2 == 0:
                img_array[y, x] = [0, 0, 0, 255]
            else:
                img_array[y, x] = [255, 255, 255, 255]
    
    white_bg_img = Image.fromarray(img_array, 'RGBA')
    white_bg_img.save('demo_white_bg.bmp', 'BMP')
    
    # Convert with white transparency (default)
    converted = convert_checkerboard_to_alpha(white_bg_img, transparency_color=0xffffff)
    converted.save('demo_white_bg_converted.png', 'PNG')
    
    print("✓ Created demo_white_bg.bmp and demo_white_bg_converted.png")
    print("  White background → transparent, black checkerboard → smooth shadow")
    
    print("\n--- Black background example ---")
    print("Creating sprite with black background and white shadows...")
    
    # Create image with black background
    img_array[:, :] = [0, 0, 0, 255]  # Black background
    
    # Add sprite
    for y in range(20, 30):
        for x in range(25, 35):
            img_array[y, x] = [50, 100, 200, 255]  # Blue sprite
    
    # Add white checkerboard shadow
    for y in range(35, 50):
        for x in range(20, 40):
            if (x + y) % 2 == 0:
                img_array[y, x] = [255, 255, 255, 255]
            else:
                img_array[y, x] = [0, 0, 0, 255]
    
    black_bg_img = Image.fromarray(img_array, 'RGBA')
    black_bg_img.save('demo_black_bg.bmp', 'BMP')
    
    # Convert with black transparency
    converted = convert_checkerboard_to_alpha(black_bg_img, transparency_color=0x000000)
    converted.save('demo_black_bg_converted.png', 'PNG')
    
    print("✓ Created demo_black_bg.bmp and demo_black_bg_converted.png")
    print("  Black background → transparent, white checkerboard → smooth shadow")
    
    print("\nCommand-line usage:")
    print("  python chess.py sprite.bmp  # white transparency (default)")
    print("  python chess.py sprite.bmp -t black  # black transparency")
    print("  python chess.py sprite.bmp -t none   # no transparency conversion")


def example_5_batch_processing():
    """Example 5: Batch processing multiple files"""
    print("\n" + "="*60)
    print("Example 5: Batch processing")
    print("="*60)
    
    print("\nExample code for batch processing:")
    print("""
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
""")


def main():
    """Run all examples"""
    print("\n" + "="*70)
    print(" CHESS: Convert Half-tone Effects to Smooth Shadows")
    print(" Usage Examples")
    print("="*70)
    
    example_1_command_line_usage()
    example_2_import_as_module()
    example_3_raw_image_data()
    example_4_transparency_colors()
    example_5_batch_processing()
    
    print("\n" + "="*70)
    print(" Examples complete!")
    print("="*70)
    print("\nCheck the created files:")
    print("  - test_checkerboard.bmp (original with checkerboard)")
    print("  - test_output.png (converted with alpha)")
    print("  - example3_before.png (before conversion)")
    print("  - example3_after.png (after conversion)")
    print("  - demo_white_bg.bmp & demo_white_bg_converted.png")
    print("  - demo_black_bg.bmp & demo_black_bg_converted.png")
    print()


if __name__ == '__main__':
    main()
