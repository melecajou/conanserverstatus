import struct


def decode_generic_blob(hex_data, tid_target):
    data = bytes.fromhex(hex_data)
    print(f"\nAnálise de Item (TID: {tid_target})\n" + "=" * 50)

    offset = 40
    found = False
    while offset < len(data) - 8:
        val1 = struct.unpack("<I", data[offset : offset + 4])[0]
        val2 = struct.unpack("<I", data[offset + 4 : offset + 8])[0]
        if val1 == tid_target and 0 < val2 < 20:
            found = True
            print(f"Bloco Principal (Props: {val2})")
            offset += 8
            for _ in range(val2):
                p_id = struct.unpack("<I", data[offset : offset + 4])[0]
                p_val = struct.unpack("<I", data[offset + 4 : offset + 8])[0]
                print(f"  - ID {p_id:<3} : {p_val}")
                offset += 8
            break
        offset += 1

    if not found:
        return

    while offset < len(data) - 4:
        count = struct.unpack("<I", data[offset : offset + 4])[0]
        if 0 < count < 10:
            print(f"\nBloco Secundário ({count} propriedades):")
            offset += 4
            for _ in range(count):
                p_id = struct.unpack("<I", data[offset : offset + 4])[0]
                p_hex = data[offset + 4 : offset + 8]
                p_float = struct.unpack("<f", p_hex)[0]
                p_int = struct.unpack("<I", p_hex)[0]
                if 0.001 < abs(p_float) < 100000:
                    val_str = f"{p_float:.4f} (Float)"
                else:
                    val_str = f"{p_int} (Int)"
                print(f"  - ID {p_id:<3} : {val_str}")
                offset += 8
            break
        offset += 1


blob_weapon_3 = "01000000EFBEADDE0FCAFEBACAFBCFABCDAB21430000000000000000520000002F47616D652F4974656D732F425047616D654974656D576561706F6E5F4C6F774865616C74684D6F7265446D672E425047616D654974656D576561706F6E5F4C6F774865616C74684D6F7265446D675F430027000000425047616D654974656D576561706F6E5F4C6F774865616C74684D6F7265446D675F435F39380000435E0000080000000600000039000000070000003F00000016000000949CC76728000000000000003F0000000C000000410000000000000047000000110000004800000013000000030000000B0000003E0A573E1D000000CDCCCC3D1E0000000000803F"
decode_generic_blob(blob_weapon_3, 24131)
