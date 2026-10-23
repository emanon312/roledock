"""Read-only SiYuan adapter skeleton (not connected to any private workspace)."""
import httpx


class SiYuanClient:
    def __init__(self, base_url: str, token: str):
        if not base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise ValueError("SiYuan demo only permits loopback addresses; configure proxy explicitly later")
        self.base_url = base_url.rstrip("/")
        self.token = token

    def get_block_kramdown(self, block_id: str) -> str:
        if not block_id or len(block_id) > 100 or not all(c.isalnum() or c in "-_" for c in block_id):
            raise ValueError("invalid_block_id")
        with httpx.Client(timeout=10, trust_env=False) as client:
            resp = client.post(
                self.base_url + "/api/block/getBlockKramdown",
                json={"id": block_id},
                headers={"Authorization": f"Token {self.token}"},
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError("siyuan_api_error")
            return str(data["data"]["kramdown"])
