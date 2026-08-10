import struct
import time
import os

def setup_benchmark_data(prop_count, qty_idx):
    template_id = 12345
    packed_id = struct.pack("<I", template_id)
    props = []
    for i in range(prop_count):
        if i == qty_idx:
            props.extend([1, 999])
        else:
            props.extend([i + 2, 0])

    props_data = struct.pack(f"<{prop_count * 2}I", *props)
    data = packed_id + struct.pack("<I", prop_count) + props_data
    data = os.urandom(100) + data + os.urandom(100)
    return data, template_id, packed_id

def benchmark_old(data, packed_id):
    quantity = 1
    offset = data.find(packed_id)
    while offset != -1:
        cursor_pos = offset + 4
        if cursor_pos + 4 <= len(data):
            prop_count = struct.unpack_from("<I", data, cursor_pos)[0]
            cursor_pos += 4
            if prop_count < 100:
                if cursor_pos + (prop_count * 8) <= len(data):
                    props = struct.unpack_from(
                        f"<{prop_count * 2}I", data, cursor_pos
                    )
                    for i in range(0, prop_count * 2, 2):
                        if props[i] == 1:  # 1 is Quantity
                            quantity = props[i + 1]
                            break
            offset = data.find(packed_id, offset + 1)
    return quantity

_STRUCT_CACHE = {}

def benchmark_fast(data, packed_id):
    quantity = 1
    offset = data.find(packed_id)
    while offset != -1:
        cursor_pos = offset + 4
        if cursor_pos + 4 <= len(data):
            prop_count = struct.unpack_from("<I", data, cursor_pos)[0]
            cursor_pos += 4
            if prop_count < 100:
                if cursor_pos + (prop_count * 8) <= len(data):
                    fmt = _STRUCT_CACHE.get(prop_count)
                    if fmt is None:
                        fmt = struct.Struct(f"<{prop_count * 2}I")
                        _STRUCT_CACHE[prop_count] = fmt
                    props = fmt.unpack_from(data, cursor_pos)
                    try:
                        # Slice to get just the property IDs (even indices).
                        # This creates a tuple copy but is very fast in C.
                        idx = props[::2].index(1)
                        quantity = props[idx * 2 + 1]
                    except ValueError:
                        pass
            offset = data.find(packed_id, offset + 1)
    return quantity

if __name__ == "__main__":
    for count, qty_idx in [(5, 4), (20, 19), (50, 49), (10, 5), (10, -1), (90, 89)]:
        data, template_id, packed_id = setup_benchmark_data(count, qty_idx)
        iterations = 100000

        print(f"\nProperties: {count}, Quantity at: {qty_idx}")

        start = time.perf_counter()
        for _ in range(iterations):
            benchmark_old(data, packed_id)
        old_time = time.perf_counter() - start

        start = time.perf_counter()
        for _ in range(iterations):
            benchmark_fast(data, packed_id)
        fast_time = time.perf_counter() - start

        print(f"Old: {old_time:.4f}s")
        print(f"Fast: {fast_time:.4f}s")
        if old_time > fast_time:
            print(f"Improvement: {(old_time - fast_time) / old_time * 100:.2f}%")
        else:
            print(f"Regression: {(fast_time - old_time) / old_time * 100:.2f}%")
