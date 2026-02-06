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


# BLOB da Rip and Tear (Agilidade)
blob_agility = "01000000EFBEADDE0FCAFEBACAFBCFABCDAB21430000000000000000570000002F47616D652F4974656D732F4E7063576561706F6E732F425047616D654974656D576561706F6E5F47656E6572696353756E6465722E425047616D654974656D576561706F6E5F47656E6572696353756E6465725F430024000000425047616D654974656D576561706F6E5F47656E6572696353756E6465725F435F38390000455E00000700000006000000330000000700000038000000160000007D8B2F693F0000000C000000410000000000000047000000110000004800000013000000040000000800000000705F450B0000003D0A573E1D000000CDCCCC3D1E0000000000803F"
decode_generic_blob(blob_agility, 24133)
