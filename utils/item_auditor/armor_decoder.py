import struct


def decode_armor_blob(hex_data, label):
    data = bytes.fromhex(hex_data)
    print(f"\nAnálise de Armadura: {label}\n" + "=" * 50)

    # Template ID: 91335 -> C7 64 01 00 (Little Endian)
    offset = 40
    found = False
    while offset < len(data) - 8:
        val1 = struct.unpack("<I", data[offset : offset + 4])[0]
        val2 = struct.unpack("<I", data[offset + 4 : offset + 8])[0]
        if val1 == 91335 and 0 < val2 < 20:
            found = True
            print(f"Bloco Principal encontrado no offset {offset} (Props: {val2})")
            offset += 8
            for _ in range(val2):
                p_id = struct.unpack("<I", data[offset : offset + 4])[0]
                p_val = struct.unpack("<I", data[offset + 4 : offset + 8])[0]
                print(f"  - ID {p_id:<3} : {p_val}")
                offset += 8
            break
        offset += 1

    # Bloco Secundário
    while offset < len(data) - 4:
        count = struct.unpack("<I", data[offset : offset + 4])[0]
        if 0 < count < 10:
            print(f"\nBloco Secundário no offset {offset} ({count} propriedades):")
            offset += 4
            for _ in range(count):
                p_id = struct.unpack("<I", data[offset : offset + 4])[0]
                p_hex = data[offset + 4 : offset + 8]
                p_float = struct.unpack("<f", p_hex)[0]
                p_int = struct.unpack("<I", p_hex)[0]

                # Exibe Float se parecer um número real, senão exibe Int
                if 0.001 < abs(p_float) < 100000:
                    val_str = f"{p_float:.4f} (Float)"
                else:
                    val_str = f"{p_int} (Int)"
                print(f"  - ID {p_id:<3} : {val_str}")
                offset += 8
            break
        offset += 1


blob_jhil = "01000000EFBEADDE0FCAFEBACAFBCFABCDAB21430000000000000000440000002F47616D652F4974656D732F425047616D654974656D41726D6F725F4A68696C476C6F7665732E425047616D654974656D41726D6F725F4A68696C476C6F7665735F430020000000425047616D654974656D41726D6F725F4A68696C476C6F7665735F435F260000C76401000600000016000000EEE45C69280000001F6801003F0000000F00000041000000000000004200000004000000430000004300000004000000040000000000904205000000022B8B4007000000CD4CB74408000000CD0CAF44"
decode_armor_blob(blob_jhil, "Luvas de Jhil")
