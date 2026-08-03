import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend

def encrypt(t: str) -> str:
    # Keys and initialization vectors must be bytes
    key = b"7Fpu9FSkjayCeqaE"
    iv = b"0123456789ABCDEF"
    
    # The input text needs to be bytes
    raw_data = t.encode('utf-8')
    
    # Apply PKCS7 padding (AES block size is 128 bits / 16 bytes)
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(raw_data) + padder.finalize()
    
    # Set up the AES cipher in CBC mode
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    
    # Encrypt the data
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()
    
    # CryptoJS toString() by default returns a Base64 encoded string
    return base64.b64encode(ciphertext).decode('utf-8')

# Example usage:
if __name__ == '__main__':
    text = '{"userno":"2241112","pwd":"xxx"}'
    encrypted_text = encrypt(text)
    print(f"Encrypted: {encrypted_text}")