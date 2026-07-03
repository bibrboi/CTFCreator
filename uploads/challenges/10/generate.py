import numpy as np
from PIL import Image

# Load the image
img = Image.open('image.png')

# Convert image to RGB
rgb_img = img.convert('RGB')

# Define the hidden message
hidden_message = 'This is a secret message'

# Convert the message to binary
binary_message = ''.join(format(ord(i), '08b') for i in hidden_message)

# Define the LSB substitution function
def lsb_substitution(pixel, bit):
    # Get the RGB values of the pixel
    r, g, b = pixel
    
    # Substitute the LSB of the red channel with the bit
    r = (r & ~1) | int(bit)
    
    # Return the modified pixel
    return (r, g, b)

# Apply the LSB substitution to the image pixels
for i in range(len(binary_message)):
    # Calculate the pixel coordinates
    x = i % img.width
    y = i // img.width
    
    # Get the pixel at the coordinates
    pixel = rgb_img.getpixel((x, y))
    
    # Substitute the LSB with the binary message bit
    modified_pixel = lsb_substitution(pixel, binary_message[i])
    
    # Put the modified pixel back into the image
    rgb_img.putpixel((x, y), modified_pixel)

# Save the modified image
rgb_img.save('modified_image.png')

print('Hidden message encoded into the image')
