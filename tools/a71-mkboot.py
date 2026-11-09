#!/usr/bin/env python3
"""Pack a raw shim Image into a boot.img v2 for the Galaxy A71 (SM-A715F).

Samsung ABL has no `fastboot boot`, so the shim is flashed to BOOT (with a
verification-disabled VBMETA). The header fields, cmdline and DTB are copied
from the phone's own boot image so ABL sees a familiar layout.

Usage: a71-mkboot.py template-boot.img Image out-boot.img [ramdisk]
"""
import gzip
import hashlib
import struct
import sys


def pg(n, page):
    return (n + page - 1) // page * page


def empty_cpio_gz():
    # newc archive containing only the TRAILER!!! entry
    name = b'TRAILER!!!\0'
    hdr = b'070701' + b'%08X' * 13 % (0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, len(name), 0)
    rec = hdr + name
    rec += b'\0' * ((4 - len(rec) % 4) % 4)
    rec += b'\0' * ((512 - len(rec) % 512) % 512)
    return gzip.compress(rec, 9)


def main():
    tpl, image, out = sys.argv[1], sys.argv[2], sys.argv[3]
    rd = open(sys.argv[4], 'rb').read() if len(sys.argv) > 4 else empty_cpio_gz()
    t = open(tpl, 'rb').read()
    assert t[:8] == b'ANDROID!', 'template is not a boot image'
    ksz, kaddr, rsz, raddr, ssz, saddr, tags, page, hver, osver = struct.unpack_from('<10I', t, 8)
    assert hver == 2, 'expected boot header v2, got %d' % hver
    rdtbo_sz, = struct.unpack_from('<I', t, 1632)
    dtb_sz, = struct.unpack_from('<I', t, 1648)
    off = page + pg(ksz, page) + pg(rsz, page) + pg(ssz, page) + pg(rdtbo_sz, page)
    dtb = t[off:off + dtb_sz]
    assert dtb[:4] == b'\xd0\x0d\xfe\xed', 'DTB not found in template'

    kernel = open(image, 'rb').read()
    hdr = bytearray(t[:page])
    struct.pack_into('<I', hdr, 8, len(kernel))
    struct.pack_into('<I', hdr, 16, len(rd))
    struct.pack_into('<I', hdr, 24, 0)          # second size
    struct.pack_into('<I', hdr, 1632, 0)        # recovery dtbo size
    struct.pack_into('<Q', hdr, 1636, 0)        # recovery dtbo offset
    h = hashlib.sha1()
    for blob in (kernel, rd, b'', b'', dtb):
        h.update(blob)
        h.update(struct.pack('<I', len(blob)))
    hdr[576:608] = h.digest() + b'\0' * 12

    img = bytearray(hdr)
    for blob in (kernel, rd, dtb):
        img += blob + b'\0' * (pg(len(blob), page) - len(blob))
    assert len(img) <= 64 * 1024 * 1024, 'image larger than BOOT partition'
    open(out, 'wb').write(img)
    print('kernel=%d ramdisk=%d dtb=%d page=%d kaddr=0x%x -> %s (%d bytes)'
          % (len(kernel), len(rd), len(dtb), page, kaddr, out, len(img)))


if __name__ == '__main__':
    main()
