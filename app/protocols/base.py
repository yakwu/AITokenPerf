#!/usr/bin/env python3
"""协议适配器基类"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiohttp
    from app.client import RequestMetrics


class ProtocolAdapter(ABC):
    """API 协议适配器基类"""

    @abstractmethod
    def build_url(self, config: dict) -> str:
        """构建请求 URL"""
        ...

    @abstractmethod
    def build_headers(self, config: dict) -> dict:
        """构建请求头"""
        ...

    @abstractmethod
    def build_payload(self, config: dict) -> dict:
        """构建请求体"""
        ...

    @abstractmethod
    async def parse_sse_stream(
        self, resp: "aiohttp.ClientResponse", metrics: "RequestMetrics"
    ) -> None:
        """解析 SSE 流，填充 metrics"""
        ...
