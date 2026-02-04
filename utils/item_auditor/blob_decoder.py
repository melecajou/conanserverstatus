import struct

def decode_blob(hex_data):
    data = bytes.fromhex(hex_data)
    print(f"Tamanho total do BLOB: {len(data)} bytes")
    
    # Header e Strings Iniciais
    print("\n--- HEADER ---")
    header = data[:16]
    print(f"Magic: {header.hex(' ')}")
    
    offset = 16
    while offset < len(data):
        # Tenta encontrar strings (UE4: [tamanho][string])
        if offset + 4 <= len(data):
            length = struct.unpack('<I', data[offset:offset+4])[0]
            if 0 < length < 255 and offset + 4 + length <= len(data):
                try:
                    potential_string = data[offset+4:offset+4+length].decode('ascii').strip('\x00')
                    if all(32 <= ord(c) <= 126 for c in potential_string) and len(potential_string) > 3:
                        print(f"String encontrada no offset {offset}: {potential_string}")
                        offset += 4 + length
                        continue
                except:
                    pass
        
        # Procura por contadores de propriedades ou TemplateID
        # Vamos tentar identificar o padrão: [ID/Template] [Count] [Prop1_ID] [Prop1_Val]
        if offset + 8 <= len(data):
            val1 = struct.unpack('<I', data[offset:offset+4])[0]
            val2 = struct.unpack('<I', data[offset+4:offset+8])[0]
            
            # Se val2 parece um contador razoável (1-20 propriedades)
            if 0 < val2 < 20:
                print(f"\n--- BLOCO DETECTADO (ID/Type: {val1}) no offset {offset} ---")
                print(f"Quantidade de Propriedades: {val2}")
                offset += 8
                for i in range(val2):
                    if offset + 8 <= len(data):
                        p_id = struct.unpack('<I', data[offset:offset+4])[0]
                        p_hex = data[offset+4:offset+8]
                        p_int = struct.unpack('<I', p_hex)[0]
                        p_float = struct.unpack('<f', p_hex)[0]
                        
                        # Heurística simples para decidir se mostra como float
                        if 0.0001 < abs(p_float) < 1000000:
                            val_str = f"Float={p_float:.4f}"
                        else:
                            val_str = f"Int={p_int}"
                            
                        print(f"  Prop {i+1}: ID={p_id:<3} | {val_str:<15} | Hex={p_hex.hex()}")
                        offset += 8
                continue

        offset += 1

blob_hex = "01000000EFBEADDE0FCAFEBACAFBCFABCDAB214300000000000000003F0000002F47616D652F4974656D732F576561706F6E732F4D61756C32682F42505F4974656D5F4D61756C426173652E42505F4974656D5F4D61756C426173655F43001600000042505F4974656D5F4D61756C426173655F435F3839000071270000070000000600000057000000070000006700000016000000610D6D693F0000000C000000410000000000000047000000110000004800000013000000040000000800000000D081450B00000014AE173F1D0000000000803F1E000000CDCCCC3D"
decode_blob(blob_hex)
