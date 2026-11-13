# utils/bencode.py

def decode_bencode(data):
    """Декодирует bencode-данные с автоматическим декодированием ключей и текста в UTF-8."""
    if isinstance(data, str):
        data = data.encode('latin1')

    def decode_first(idx):
        char = data[idx:idx + 1]
        if char == b'i':
            end = data.index(b'e', idx + 1)
            return int(data[idx + 1:end]), end + 1
        elif char == b'l':
            idx += 1
            res = []
            while data[idx:idx + 1] != b'e':
                val, idx = decode_first(idx)
                res.append(val)
            return res, idx + 1
        elif char == b'd':
            idx += 1
            res = {}
            while data[idx:idx + 1] != b'e':
                raw_key, idx = decode_first(idx)
                # Ключи словаря всегда декодируем в строковый вид (str)
                if isinstance(raw_key, bytes):
                    try:
                        key = raw_key.decode('utf-8')
                    except UnicodeDecodeError:
                        key = raw_key.decode('latin1', errors='replace')
                else:
                    key = str(raw_key)

                val, idx = decode_first(idx)
                res[key] = val
            return res, idx + 1
        elif char.isdigit():
            colon = data.index(b':', idx)
            length = int(data[idx:colon])
            start = colon + 1
            end = start + length
            raw_bytes = data[start:end]

            # Текстовые строки декодируем в str, бинарные данные (куски, хэши) оставляем в bytes
            try:
                val = raw_bytes.decode('utf-8')
            except UnicodeDecodeError:
                val = raw_bytes
            return val, end
        raise ValueError(f"Неизвестный токен bencode на позиции {idx}: {char}")

    val, _ = decode_first(0)
    return val


def encode_bencode(val):
    """Безопасное кодирование обратно в bencode с корректной сортировкой ключей."""
    if isinstance(val, int):
        return b'i' + str(val).encode('ascii') + b'e'
    elif isinstance(val, (bytes, bytearray)):
        return str(len(val)).encode('ascii') + b':' + bytes(val)
    elif isinstance(val, str):
        b = val.encode('utf-8')
        return str(len(b)).encode('ascii') + b':' + b
    elif isinstance(val, (list, tuple)):
        return b'l' + b''.join(encode_bencode(x) for x in val) + b'e'
    elif isinstance(val, dict):
        def to_bytes(k):
            return k if isinstance(k, (bytes, bytearray)) else str(k).encode('utf-8')

        sorted_keys = sorted(val.keys(), key=to_bytes)
        out = [b'd']
        for k in sorted_keys:
            out.append(encode_bencode(to_bytes(k)))
            out.append(encode_bencode(val[k]))
        out.append(b'e')
        return b''.join(out)
    raise TypeError(f"Невозможно закодировать тип в bencode: {type(val)}")