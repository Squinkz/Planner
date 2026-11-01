"""Keep the complete activity sequence with a bounded cache of decoded rows."""
from collections import OrderedDict
from collections.abc import Sequence
import json
import operator
from pathlib import Path
import sqlite3
import tempfile
import weakref
import zlib


class ActivityEntries(Sequence):
    def __init__(self):
        self.entryLimit = 512
        self.byteLimit = 1024 * 1024
        self.cache = OrderedDict()
        self.cachedPayloads = {}
        self.cacheBytes = self.count = 0
        self.connection = self.cleanup = None
        self.encodingPrefix = None

    def __len__(self):
        return self.count

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self[position] for position in range(*index.indices(self.count))]
        index = operator.index(index)
        if index < 0:
            index += self.count
        if not 0 <= index < self.count:
            raise IndexError(index)
        cached = self.cache.get(index)
        if cached is not None:
            self.cache.move_to_end(index)
            return cached[0]
        row = self.connection.execute("SELECT payload FROM entries WHERE position = ?", (index,)).fetchone()
        entry = json.loads(row[0])
        self.Cache(index, entry, storedPayload = row[0])
        return entry

    def __iter__(self):
        return self.IterFrom(0)

    def IterFrom(self, start):
        if self.connection is None:
            for position in range(start, self.count):
                yield self.cache[position][0]
            return
        # Publish mutations without rewriting rows that were only browsed.
        for position, (entry, size) in self.cache.items():
            self.WriteRow(position, entry)
        cursor = self.connection.execute("SELECT position, payload FROM entries WHERE position >= ? ORDER BY position", (start,))
        try:
            for position, payload in cursor:
                cached = self.cache.get(position)
                yield cached[0] if cached is not None else json.loads(payload)
        finally:
            cursor.close()

    def EncodingPrefix(self, byteLimit):
        """Reuse compression of archived rows; only the mutable tail is replayed.

        Cached rows are checked against their persisted JSON before reuse.
        Browsing old rows does not invalidate compression; changing one does.
        No live database connection or mutable row crosses a thread boundary.
        """
        if self.connection is not None:
            for position, (entry, size) in self.cache.items():
                self.WriteRow(position, entry)
        # Keep the current/coalescing entry outside the prefix. Older cached
        # rows are safe to include after WriteRow has validated their contents.
        cutoff = max(0, self.count - 1) if self.connection is not None else 0
        prefix = self.encodingPrefix
        if prefix is None:
            compressor = zlib.compressobj()
            header = b'{"entries":['
            prefix = [0, len(header), compressor, [compressor.compress(header)]]
            self.encodingPrefix = prefix
        if prefix[1] > byteLimit:
            raise ValueError("The activity log exceeds the 64 MiB limit. Clear the log before saving.")
        if prefix[0] < cutoff:
            cursor = self.connection.execute("SELECT position, payload FROM entries WHERE position >= ? AND position < ? ORDER BY position",
                                             (prefix[0], cutoff))
            try:
                for position, payload in cursor:
                    chunk = (("," if position else "") + payload).encode("utf-8")
                    if prefix[1] + len(chunk) > byteLimit:
                        raise ValueError("The activity log exceeds the 64 MiB limit. Clear the log before saving.")
                    prefix[3].append(prefix[2].compress(chunk))
                    prefix[1] += len(chunk)
                    prefix[0] = position + 1
            finally:
                cursor.close()
            # Consolidate emitted blocks without retaining empty results per row.
            prefix[3] = [chunk for chunk in prefix[3] if chunk]
            if len(prefix[3]) > 64:
                prefix[3] = [b"".join(prefix[3])]
        return prefix[2].copy(), list(prefix[3]), prefix[1], prefix[0]

    def __reversed__(self):
        for position in range(self.count - 1, -1, -1):
            yield self[position]

    def __eq__(self, other):
        if not isinstance(other, Sequence) or len(self) != len(other):
            return False
        return all(first == second for first, second in zip(self, other))

    def __deepcopy__(self, memo):
        from copy import deepcopy
        return [deepcopy(entry, memo) for entry in self]

    def append(self, entry):
        self.Cache(self.count, entry)
        self.count += 1

    def Find(self, entryId):
        if entryId is None:
            return None
        for entry, size in self.cache.values():
            if entry["id"] == entryId:
                return entry
        if self.connection is not None:
            row = self.connection.execute("SELECT position FROM entries WHERE entryId = ?", (entryId,)).fetchone()
            if row is not None:
                return self[row[0]]
        return None

    def Update(self, entry):
        for position, (cached, size) in self.cache.items():
            if cached["id"] == entry["id"]:
                break
        else:
            row = (self.connection.execute("SELECT position FROM entries WHERE entryId = ?", (entry["id"],)).fetchone()
                   if self.connection is not None else None)
            if row is None:
                raise KeyError(entry["id"])
            position = row[0]
        self.Cache(position, entry)

    def WriteRow(self, position, entry):
        """Persist a changed cached row and invalidate only affected prefix data."""
        payload = json.dumps(entry, ensure_ascii = False, separators = (",", ":"), allow_nan = False)
        if payload == self.cachedPayloads.get(position):
            return
        if self.encodingPrefix is not None and position < self.encodingPrefix[0]:
            self.encodingPrefix = None
        self.connection.execute("INSERT OR REPLACE INTO entries VALUES (?, ?, ?)", (position, entry["id"], payload))
        self.cachedPayloads[position] = payload

    def Cache(self, position, entry, storedPayload = None):
        payload = json.dumps(entry, ensure_ascii = False, separators = (",", ":"), allow_nan = False)
        size = len(payload.encode("utf-8")) * 2 + 512
        previous = self.cache.pop(position, None)
        previousPayload = self.cachedPayloads.get(position)
        if previous is None:
            self.cachedPayloads[position] = storedPayload
        if previous is not None:
            self.cacheBytes -= previous[1]
        self.cache[position] = entry, size
        self.cacheBytes += size
        try:
            # Keep the most recently returned mutable entry until its caller has
            # attached its history anchor. One unusually large row can exceed the
            # cache budget; a growing sequence cannot.
            while len(self.cache) > 1 and (len(self.cache) > self.entryLimit or self.cacheBytes > self.byteLimit):
                index, (retired, retiredSize) = next(iter(self.cache.items()))
                if self.connection is None:
                    temporary = tempfile.TemporaryDirectory(prefix = "planner-activity-")
                    connection = None
                    try:
                        connection = sqlite3.connect(str(Path(temporary.name) / "entries.sqlite"), isolation_level = None)
                        connection.execute("PRAGMA journal_mode = OFF")
                        connection.execute("PRAGMA synchronous = OFF")
                        connection.execute("PRAGMA cache_size = -256")
                        connection.execute("CREATE TABLE entries (position INTEGER PRIMARY KEY, entryId INTEGER UNIQUE NOT NULL, payload TEXT NOT NULL)")
                    except Exception:
                        if connection is not None:
                            connection.close()
                        temporary.cleanup()
                        raise

                    def Cleanup():
                        connection.close()
                        temporary.cleanup()

                    self.connection = connection
                    self.cleanup = weakref.finalize(self, Cleanup)
                self.WriteRow(index, retired)
                del self.cache[index]
                self.cachedPayloads.pop(index, None)
                self.cacheBytes -= retiredSize
        except Exception:
            # A failed spill must leave a valid sequence. Keep the existing
            # bounded rows and reject this new/update operation atomically.
            self.cache.pop(position, None)
            self.cachedPayloads.pop(position, None)
            if previous is not None:
                self.cache[position] = (previous[0], size if previous[0] is entry else previous[1])
                self.cachedPayloads[position] = previousPayload
            self.cacheBytes = sum(size for cached, size in self.cache.values())
            raise


    def Reset(self, entries = ()):
        self.Close()
        for entry in entries:
            self.append(entry)

    def Close(self):
        if self.cleanup is not None:
            self.cleanup()
        self.connection = self.cleanup = None
        self.cache.clear()
        self.cachedPayloads.clear()
        self.cacheBytes = self.count = 0
        self.encodingPrefix = None
