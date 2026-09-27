"""
Decrypt SPSS Password-Protected Encrypted File Wrappers (SPSS 21+).
Uses AES-256 in ECB mode with CMAC key derivation.
Requires: cryptography (pip install cryptography)
"""
import argparse
import struct
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# The mandatory 73-byte constant specified in the PSPP documentation
CMAC_CONSTANT = bytes([
    0x00, 0x00, 0x00, 0x01, 0x35, 0x27, 0x13, 0xcc,
    0xd6, 0x5b, 0x31, 0x58, 0xdc, 0xfe, 0x2e, 0x7e,
    0x0a, 0x6c, 0x63, 0x53, 0x00, 0x38, 0xc3, 0x38,
    0x3f, 0xb8, 0x07, 0x4c, 0x4e, 0x2b, 0x77, 0xc7,
    0xe1, 0x83, 0x07, 0xd8, 0x0d, 0x00, 0x00, 0x01,
    0x53, 0xa7, 0x78, 0x89, 0x87, 0x53, 0x22, 0x11,
    0x94, 0xd4, 0x2f, 0x00, 0xcc, 0x15, 0x71, 0x80,
    0xac, 0x22, 0xf3, 0x63, 0x62, 0x0e, 0xce, 0x85,
    0x21, 0xf5, 0x1a, 0x80, 0x1d, 0x67, 0xfb, 0xe1,
    0x00
])

def left_shift_block(block: bytes) -> bytes:
    """Left shifts a 16-byte block by 1 bit for CMAC subkey generation."""
    val = int.from_bytes(block, 'big') << 1
    if block[0] & 0x80:
        val ^= 0x1b  # R_128 constant for AES
    return val.to_bytes(16, 'big')

def aes_encrypt_block(key: bytes, block: bytes) -> bytes:
    """Encrypts a single 16-byte block using AES-256 ECB."""
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    encryptor = cipher.encryptor()
    return encryptor.update(block) + encryptor.finalize()

def compute_cmac(password_32: bytes, message: bytes) -> bytes:
    """
    Computes CMAC-AES-256. 
    Note: For the SPSS key derivation, message is always the 73-byte constant.
    """
    # 1. Derive subkeys K1 and K2 from zero block encryption
    zero_block = b'\x00' * 16
    l_block = aes_encrypt_block(password_32, zero_block)
    k1 = left_shift_block(l_block)
    k2 = left_shift_block(k1)

    # 2. Padding the message for CMAC (PKCS#7 style block padding)
    block_size = 16
    if len(message) == 0:
        padded = b'\x80' + b'\x00' * (block_size - 1)
        padded = bytes(a ^ b for a, b in zip(padded, k2))
    else:
        # Check if message length is a multiple of block size
        if len(message) % block_size == 0:
            last_block = message[-block_size:]
            padded_last = bytes(a ^ b for a, b in zip(last_block, k1))
            padded = message[:-block_size] + padded_last
        else:
            padding_len = block_size - (len(message) % block_size)
            last_block = message[-(len(message) % block_size):] + b'\x80' + b'\x00' * (padding_len - 1)
            padded_last = bytes(a ^ b for a, b in zip(last_block, k2))
            padded = message[:-(len(message) % block_size)] + padded_last

    # 3. CBC-MAC chaining over blocks
    chained = b'\x00' * 16
    for i in range(0, len(padded), block_size):
        block = padded[i:i+block_size]
        xored = bytes(a ^ b for a, b in zip(chained, block))
        chained = aes_encrypt_block(password_32, xored)
        
    return chained

def derive_aes_key(password: str) -> bytes:
    """
    Derives the 32-byte AES key from a user password according to SPSS specs:
    1. Truncate to 10 bytes, pad with null bytes to 32 bytes.
    2. Compute CMAC-AES-256(password, 73-byte constant).
    3. Return cmac || cmac (32 bytes).
    """
    trunc = password.encode('utf-8')[:10]
    pwd_32 = trunc + b'\x00' * (32 - len(trunc))
    
    cmac = compute_cmac(pwd_32, CMAC_CONSTANT)
    return cmac + cmac

def remove_pkcs7_padding(data: bytes) -> bytes:
    """Removes PKCS #7 padding from decrypted payload."""
    if not data:
        return data
    padding_len = data[-1]
    if padding_len < 1 or padding_len > 16:
        raise ValueError("Invalid PKCS#7 padding length.")
    # Validate all padding bytes match the length
    for b in data[-padding_len:]:
        if b != padding_len:
            raise ValueError("Invalid PKCS#7 padding bytes.")
    return data[:-padding_len]

def decrypt_wrapper(file_path: Path, password: str, output_path: Path = None) -> bytes:
    """
    Decrypts an SPSS encrypted wrapper file (.spv, .sav, .sps).
    """
    raw_data = file_path.read_bytes()

    # 1. Validate wrapper header
    if len(raw_data) < 36:
        raise ValueError("File is too short to be an SPSS encrypted wrapper.")
    
    magic = raw_data[8:18]
    if magic != b'ENCRYPTED':
        raise ValueError(f"File is not encrypted with the SPSS wrapper (found magic: {magic})")
    
    file_type = raw_data[18:21].decode('ascii', errors='ignore')
    print(f"Detected encrypted SPSS container type: {file_type}")

    # 2. Derive Key and Setup AES-256 ECB Decryptor
    aes_key = derive_aes_key(password)
    ciphertext = raw_data[36:]

    if len(ciphertext) % 16 != 0:
        raise ValueError("Encrypted payload length is not a multiple of 16 bytes.")

    cipher = Cipher(algorithms.AES(aes_key), modes.ECB())
    decryptor = cipher.decryptor()
    plaintext_padded = decryptor.update(ciphertext) + decryptor.finalize()

    # 3. Strip Padding
    plaintext = remove_pkcs7_padding(plaintext_padded)

    # 4. Optional Validation Check via Magic Numbers
    if file_type == 'SPV':
        if not plaintext.startswith(b'PK\x03\x04'):
            raise ValueError("Decryption failed: Incorrect password (SPV magic PKZIP header missing).")
    elif file_type == 'SAV':
        if not (plaintext.startswith(b'$FL2') or plaintext.startswith(b'$FL3')):
            raise ValueError("Decryption failed: Incorrect password (SAV header missing).")

    if output_path:
        output_path.write_bytes(plaintext)
        print(f"Successfully decrypted and saved to {output_path}")

    return plaintext

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Decrypt SPSS Encrypted Wrappers (.spv/.sav/.sps)")
    parser.add_argument('input_file', type=Path, help="Path to encrypted SPSS file")
    parser.add_argument('password', type=str, help="Decryption password")
    parser.add_argument('-o', '--output', type=Path, default=None, help="Optional output decrypted file path")
    args = parser.parse_args()

    try:
        decrypt_wrapper(args.input_file, args.password, args.output)
    except Exception as e:
        print(f"Decryption Error: {e}")
