"""
main/services/plc_service.py

"""

import struct
import logging
import snap7

log = logging.getLogger(__name__)


class PlcService:
    def __init__(self):
        self.client = snap7.client.Client()
        self._connected = False

    # ──────────────────────────────────────────────────────────────
    # CONNECTION
    # ──────────────────────────────────────────────────────────────
    def connect(self, ip_address: str):
        try:
            if self.client.get_connected():
                print("🧹 Cleaning up stale PLC socket...")
                self.client.disconnect()

            print(f"🔄 Connecting to {ip_address} (Rack=0, Slot=1)...")
            self.client.connect(ip_address, rack=0, slot=1)

            if self.client.get_connected():
                self._connected = True
                print("✅ PLC connected successfully!")
                return True, "Connected successfully"

            self._connected = False
            return False, "Connection failed — handshake not confirmed"

        except Exception as e:
            self._connected = False
            print(f"❌ Connection failure: {e}")
            return False, str(e)

    def disconnect(self):
        try:
            self.client.disconnect()
        except Exception:
            pass
        self._connected = False

    @property
    def is_connected(self) -> bool:
        try:
            return self._connected and self.client.get_connected()
        except Exception:
            self._connected = False
            return False

    # ──────────────────────────────────────────────────────────────
    # LOW-LEVEL DB READ  ← DB tags only, NOT for I/Q areas
    # ──────────────────────────────────────────────────────────────
    def _db_read_bytes(self, db: int, byte_offset: int, byte_count: int) -> bytes:
        """
        Read raw bytes from a Data Block.
        Enforces even byte_count — PLCSim rejects odd-length PDUs with 0x81/0x04.
        """
        safe_count = byte_count if byte_count % 2 == 0 else byte_count + 1
        return bytes(self.client.db_read(db, byte_offset, safe_count))

    # ──────────────────────────────────────────────────────────────
    # TYPED DB READS
    # ──────────────────────────────────────────────────────────────
    def read_real(self, db: int, offset) -> float:
        """Read 4-byte IEEE-754 REAL from a DB. offset may be '4.0' or 4."""
        byte_idx = int(str(offset).split('.')[0])
        raw = self._db_read_bytes(db, byte_idx, 4)
        return struct.unpack('>f', raw[:4])[0]

    def read_bit(self, db: int, offset) -> bool:
        """Read a BOOL from a DB. offset format: 'byte.bit' e.g. '0.3'"""
        parts = str(offset).split('.')
        byte_idx = int(parts[0])
        bit_idx  = int(parts[1]) if len(parts) > 1 else 0
        raw = self._db_read_bytes(db, byte_idx, 2)
        return bool((raw[0] >> bit_idx) & 0x01)

    def read_int(self, db: int, offset) -> int:
        """Read a 2-byte signed INT from a DB."""
        byte_idx = int(str(offset).split('.')[0])
        raw = self._db_read_bytes(db, byte_idx, 2)
        return struct.unpack('>h', raw[:2])[0]

    def read_dint(self, db: int, offset) -> int:
        """Read a 4-byte signed DINT from a DB."""
        byte_idx = int(str(offset).split('.')[0])
        raw = self._db_read_bytes(db, byte_idx, 4)
        return struct.unpack('>i', raw[:4])[0]

    def read_word(self, db: int, offset) -> int:
        """Read a 2-byte unsigned WORD from a DB."""
        byte_idx = int(str(offset).split('.')[0])
        raw = self._db_read_bytes(db, byte_idx, 2)
        return struct.unpack('>H', raw[:2])[0]

    # ──────────────────────────────────────────────────────────────
    # TYPED DB WRITES
    # ──────────────────────────────────────────────────────────────
    def write_bit(self, db: int, offset, value: bool):
        """Write a BOOL bit to a DB (read-modify-write)."""
        parts = str(offset).split('.')
        byte_idx = int(parts[0])
        bit_idx  = int(parts[1]) if len(parts) > 1 else 0
        raw = bytearray(self._db_read_bytes(db, byte_idx, 2))
        if value:
            raw[0] |= (1 << bit_idx)
        else:
            raw[0] &= ~(1 << bit_idx)
        self.client.db_write(db, byte_idx, bytes(raw[:2]))

    def write_real(self, db: int, offset, value: float):
        """Write 4-byte IEEE-754 REAL to a DB."""
        byte_idx = int(str(offset).split('.')[0])
        self.client.db_write(db, byte_idx, struct.pack('>f', float(value)))

    def write_int(self, db: int, offset, value: int):
        """Write a 2-byte signed INT to a DB."""
        byte_idx = int(str(offset).split('.')[0])
        self.client.db_write(db, byte_idx, struct.pack('>h', int(value)))

    # ──────────────────────────────────────────────────────────────
    # BULK DB BLOCK READ  (diagnostic / dev use — keep reads ≤ 16 bytes)
    # ──────────────────────────────────────────────────────────────
    def read_db_block(self, db: int, start: int, length: int) -> bytes:
        """
        Read a contiguous slice of a DB in one PDU.
        Enforces even byte count for PLCSim safety.
        Caller should cap length at 16 for NetToPLCSim compatibility.
        """
        safe_len = length if length % 2 == 0 else length + 1
        return bytes(self.client.db_read(db, start, safe_len))


# Singleton instance used by all routes
plc_service = PlcService()