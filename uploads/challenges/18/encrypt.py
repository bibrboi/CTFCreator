
# Vigenere Cipher Encryption Script
# Author: Mr. Cipher

def generate_key(string, key):
    key = list(key)
    if len(string) == len(key):
        return(key)
    else:
        for i in range(len(string) -
                       len(key)):
            key.append(key[i % len(key)])
    return("" . join(key))

def cipher_text(string, key):
    cipher_text = []
    for i in range(len(string)):
        x = (ord(string[i]) + ord(key[i])) % 26
        x += ord('A')
        cipher_text.append(chr(x))
    return("" . join(cipher_text))

string = 'CAESARWASAGREATLEADER'
key = 'LEONARDO'
key = generate_key(string, key)
cipher = cipher_text(string, key)

print('Ciphertext:', cipher)

ciphertext = 'RXFKZVLNBPXALXWLP'
