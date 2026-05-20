"""Persistence for the mock's app + member Stellar keypairs.

Everything written here is gitignored. The file format is:

  {
    "app":    {"secret": "S...", "public": "G..."},
    "member": {"secret": "S...", "public": "G..."}
  }

In production, neither half exists in plaintext like this — the app key
lives in the OS keystore alongside the app's other secrets, and the
member key is decrypted in-process via Banker + Guardian and discarded
in `try/finally`. This is a mock-only convenience.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from stellar_sdk import Keypair


KEYSTORE_PATH = Path(__file__).parent / ".mock_keystore.json"


@dataclass
class MockKeystore:
    app: Keypair
    member: Keypair

    @property
    def app_address(self) -> str:
        return self.app.public_key

    @property
    def member_address(self) -> str:
        return self.member.public_key


def load_or_create(path: Path = KEYSTORE_PATH) -> MockKeystore:
    """Load mock keypairs from `path`, generating + saving them if absent."""
    if path.exists():
        data = json.loads(path.read_text())
        return MockKeystore(
            app=Keypair.from_secret(data["app"]["secret"]),
            member=Keypair.from_secret(data["member"]["secret"]),
        )

    app = Keypair.random()
    member = Keypair.random()
    payload = {
        "app": {"secret": app.secret, "public": app.public_key},
        "member": {"secret": member.secret, "public": member.public_key},
    }
    path.write_text(json.dumps(payload, indent=2))
    try:
        # Tighten perms where possible (no-op on Windows).
        os.chmod(path, 0o600)
    except OSError:
        pass
    return MockKeystore(app=app, member=member)


def friendbot_fund(public_key: str, timeout_s: int = 30) -> bool:
    """Fund a testnet account via Friendbot. Idempotent — already-funded
    accounts return success quickly."""
    import urllib.request
    import urllib.error

    url = f"https://friendbot.stellar.org/?addr={public_key}"
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        # 400 with "createAccountAlreadyExist" is fine — the account is funded.
        body = e.read().decode("utf-8", errors="replace")
        if "op_already_exists" in body or "createAccountAlreadyExist" in body:
            return True
        return False
    except Exception:
        return False
