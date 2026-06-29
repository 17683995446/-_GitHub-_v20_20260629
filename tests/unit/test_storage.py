"""存储后端单元测试。"""

from __future__ import annotations

import pytest

from services.storage.factory import get_storage_backend, reset_storage_backend
from services.storage.local_backend import LocalStorageBackend


@pytest.fixture
def storage(tmp_path: str, monkeypatch: pytest.MonkeyPatch) -> LocalStorageBackend:
    """使用临时目录的本地存储后端。"""
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path))
    monkeypatch.setenv("STORAGE_BASE_URL", "http://test.local/storage")
    monkeypatch.setenv("STORAGE_TYPE", "local")
    reset_storage_backend()
    # 也需要清除 settings 缓存
    from shared.config import get_settings

    get_settings.cache_clear()
    return get_storage_backend()  # type: ignore[return-value]


class TestLocalStorage:
    """本地存储后端测试。"""

    @pytest.mark.asyncio
    async def test_save_and_get_url(self, storage: LocalStorageBackend) -> None:
        """保存文件并获取 URL。"""
        data = b"fake_audio_data"
        result = await storage.save(data, "audios/test/project.mp3")
        assert result.filename == "audios/test/project.mp3"
        assert result.file_size == len(data)
        assert "test.local" in result.file_url
        assert "project.mp3" in result.file_url

    @pytest.mark.asyncio
    async def test_exists(self, storage: LocalStorageBackend) -> None:
        """检查文件存在性。"""
        assert not await storage.exists("nonexistent.mp3")
        await storage.save(b"data", "test/file.mp3")
        assert await storage.exists("test/file.mp3")

    @pytest.mark.asyncio
    async def test_delete(self, storage: LocalStorageBackend) -> None:
        """删除文件。"""
        await storage.save(b"data", "to_delete.mp3")
        assert await storage.exists("to_delete.mp3")
        await storage.delete("to_delete.mp3")
        assert not await storage.exists("to_delete.mp3")

    @pytest.mark.asyncio
    async def test_get_url(self, storage: LocalStorageBackend) -> None:
        """获取 URL。"""
        url = await storage.get_url("audios/test.mp3")
        assert url == "http://test.local/storage/audios/test.mp3"

    @pytest.mark.asyncio
    async def test_path_traversal_prevented(self, storage: LocalStorageBackend) -> None:
        """路径遍历攻击应被防止。"""
        result = await storage.save(b"data", "../../../etc/passwd")
        # .. 应被移除
        assert ".." not in result.filename

    @pytest.mark.asyncio
    async def test_creates_subdirectories(self, storage: LocalStorageBackend) -> None:
        """保存文件时自动创建子目录。"""
        result = await storage.save(
            b"data",
            "audios/owner/repo/article_id.mp3",
        )
        assert result.filename == "audios/owner/repo/article_id.mp3"
        assert await storage.exists("audios/owner/repo/article_id.mp3")


class TestStorageFactory:
    """存储工厂测试。"""

    def test_get_storage_backend_singleton(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """存储后端应为单例。"""
        import tempfile

        tmpdir = tempfile.mkdtemp()
        monkeypatch.setenv("STORAGE_LOCAL_PATH", tmpdir)
        monkeypatch.setenv("STORAGE_TYPE", "local")
        reset_storage_backend()
        from shared.config import get_settings

        get_settings.cache_clear()

        backend1 = get_storage_backend()
        backend2 = get_storage_backend()
        assert backend1 is backend2

        reset_storage_backend()
        get_settings.cache_clear()
