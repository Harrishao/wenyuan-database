from io import BytesIO

import pytest

from app.adapters.local_file_storage import InvalidStorageKeyError, LocalFileStorage


@pytest.mark.asyncio
async def test_local_storage_round_trip(tmp_path) -> None:
    storage = LocalFileStorage(tmp_path)
    stored = await storage.save("users/1/sample.txt", BytesIO(b"wenyuan"))

    assert stored.size == 7
    assert storage.resolve(stored.key).read_bytes() == b"wenyuan"

    await storage.delete(stored.key)
    assert not storage.resolve(stored.key).exists()


def test_local_storage_rejects_path_traversal(tmp_path) -> None:
    storage = LocalFileStorage(tmp_path)

    with pytest.raises(InvalidStorageKeyError):
        storage.resolve("../outside.txt")
