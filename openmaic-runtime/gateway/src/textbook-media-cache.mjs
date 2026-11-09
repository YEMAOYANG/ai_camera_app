const MAX_BYTES = 64 * 1024 * 1024;
const MAX_ENTRIES = 512;
const MAX_READS = 8;

export function createTextbookMediaCache() {
  const cached = new Map();
  const pending = new Map();
  const waiting = [];
  let size = 0;
  let active = 0;

  async function read(load) {
    if (active < MAX_READS) active++;
    else await new Promise(resolve => waiting.push(resolve));
    try {
      return await load();
    } finally {
      const next = waiting.shift();
      if (next) next();
      else active--;
    }
  }

  return function verifiedMedia(key, load) {
    if (!key) return read(load);
    const hit = cached.get(key);
    if (hit) {
      cached.delete(key);
      cached.set(key, hit);
      return hit;
    }
    const loading = pending.get(key);
    if (loading) return loading;

    const result = read(load).then(bytes => {
      cached.set(key, bytes);
      size += bytes.length;
      while (size > MAX_BYTES || cached.size > MAX_ENTRIES) {
        const [oldest, previous] = cached.entries().next().value;
        cached.delete(oldest);
        size -= previous.length;
      }
      return bytes;
    }).finally(() => pending.delete(key));
    pending.set(key, result);
    return result;
  };
}
