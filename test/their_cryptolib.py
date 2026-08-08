# crypto algorithms & params used for server-client 之间的所有密码传递

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
import base64

def encrypt(t: str, r="base64") -> str:
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

    match r:
        case "ciphertext":
            return ciphertext
        case "hex":
            return ciphertext.hex()
        case "base64":
            return base64.b64encode(ciphertext).decode('utf-8')

def decrypt(encrypted_text: str) -> str:
    # 固定密钥和IV（必须与加密时一致）
    key = b"7Fpu9FSkjayCeqaE"
    iv = b"0123456789ABCDEF"
    
    # Base64解码得到密文字节
    ciphertext = base64.b64decode(encrypted_text)
    
    # 创建AES-CBC解密器
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    
    # 解密
    padded_data = decryptor.update(ciphertext) + decryptor.finalize()
    
    # 去除PKCS7填充（AES块大小128位）
    unpadder = padding.PKCS7(128).unpadder()
    raw_data = unpadder.update(padded_data) + unpadder.finalize()
    
    # 将字节解码为UTF-8字符串
    return raw_data.decode('utf-8')


if __name__ == "__main__":
    print(encrypt('{"password":"qjy7990","newpwd":"qjy7990"}'))
