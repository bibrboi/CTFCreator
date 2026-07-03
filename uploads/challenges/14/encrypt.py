import random

def caesar_encrypt(plaintext, shift):
    ciphertext = ''
    for char in plaintext:
        if char.isalpha():
            ascii_offset = 97 if char.islower() else 65
            ciphertext += chr((ord(char) - ascii_offset + shift) % 26 + ascii_offset)
        else:
            ciphertext += char
    return ciphertext

def main():
    flag = 'CTF{caesar_shifted_secrets}'
    shift = 3  # Maybe this is the shift value?
    encrypted_flag = caesar_encrypt(flag, shift)
    print(f'Encrypted flag: {encrypted_flag}')
    return encrypted_flag

encrypted_flag = main()
print(f'Ciphertext: {encrypted_flag}')