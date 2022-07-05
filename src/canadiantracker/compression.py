import pyzstd
from importlib import resources

# Prepare the dictionary used for compression/decompression.  The
# dictionary is itself zst-compressed (but without a dictionary).
_zstd_dict = pyzstd.ZstdDict(
    dict_content=pyzstd.ZstdDecompressor().decompress(
        resources.read_binary("canadiantracker", "compress_dict.zst")
    )
)

_zstd_compressor = pyzstd.ZstdCompressor(
    level_or_option={
        # Save a few bytes by not writing the dictionary id and the uncompressed
        # data length.
        pyzstd.CParameter.contentSizeFlag: 0,
        pyzstd.CParameter.dictIDFlag: 0,
    },
    zstd_dict=_zstd_dict,
)

_zstd_decompressor = pyzstd.EndlessZstdDecompressor(
    zstd_dict=_zstd_dict,
)


def zstd_compress(data: bytes) -> bytes:
    return _zstd_compressor.compress(data, mode=pyzstd.ZstdCompressor.FLUSH_FRAME)


def zstd_decompress(data: bytes) -> bytes:
    return _zstd_decompressor.decompress(data)
