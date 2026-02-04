import struct

def decode_weapon_blob(hex_data):
    data = bytes.fromhex(hex_data)
    print(f"Análise de Arma (Template 10097)\n" + "="*40)
    
    # Mapeamento descoberto
    ID_MAP = {
        6: "Dano Leve (Int)",
        7: "Dano Pesado (Int)",
        63: "Bônus Kit Pen. (Int)",
        8: "Durabilidade (Float)",
        11: "Penetração Total (Float)",
        29: "Modificador 29 (Float)",
        30: "Modificador 30 (Float)"
    }

    offset = 122 # Início do bloco de propriedades para este item
    if data[offset:offset+4] == b'\x71\x27\x00\x00':
        offset += 4
        prop_count = struct.unpack('<I', data[offset:offset+4])[0]
        offset += 4
        print(f"Bloco Principal ({prop_count} propriedades):")
        for _ in range(prop_count):
            p_id = struct.unpack('<I', data[offset:offset+4])[0]
            p_val = struct.unpack('<I', data[offset+4:offset+8])[0]
            name = ID_MAP.get(p_id, f"ID {p_id}")
            print(f"  - {name:<20}: {p_val}")
            offset += 8

    # Segundo Bloco (Offset 186)
    if offset + 4 <= len(data):
        count2 = struct.unpack('<I', data[offset:offset+4])[0]
        offset += 4
        print(f"\nBloco Secundário ({count2} propriedades):")
        for _ in range(count2):
            p_id = struct.unpack('<I', data[offset:offset+4])[0]
            p_hex = data[offset+4:offset+8]
            p_float = struct.unpack('<f', p_hex)[0]
            name = ID_MAP.get(p_id, f"ID {p_id}")
            print(f"  - {name:<20}: {p_float:.4f}")
            offset += 8

blob_hex = "01000000EFBEADDE0FCAFEBACAFBCFABCDAB214300000000000000003F0000002F47616D652F4974656D732F576561706F6E732F4D61756C32682F42505F4974656D5F4D61756C426173652E42505F4974656D5F4D61756C426173655F43001600000042505F4974656D5F4D61756C426173655F435F3839000071270000070000000600000057000000070000006700000016000000610D6D693F0000000C000000410000000000000047000000110000004800000013000000040000000800000000D081450B00000014AE173F1D0000000000803F1E000000CDCCCC3D"
decode_weapon_blob(blob_hex)
