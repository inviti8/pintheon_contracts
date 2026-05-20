"""Soroban-side submission of register / rotate / revoke + read-back views.

Uses stellar-sdk's `scval` helpers directly so we don't need generated
Python bindings for `hvym_cert_registry`. Once the contract is deployed
and `python generate_bindings.py --contract hvym_cert_registry` has run,
the bindings package can be substituted here.

For Andromica drop-in: this module IS what the desktop app does on first
run, after the user pastes the Portal-minted token back. The function
signatures are stable enough to lift directly into glasswing — the only
glasswing-side concern is wiring its existing Stellar key access path.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from stellar_sdk import (
    Keypair,
    Network,
    SorobanServer,
    TransactionBuilder,
    scval,
    xdr as stellar_xdr,
)


TESTNET_PASSPHRASE = Network.TESTNET_NETWORK_PASSPHRASE
TESTNET_RPC = "https://soroban-testnet.stellar.org"


@dataclass
class SubmitResult:
    success: bool
    hash: str
    status: str
    error: Optional[str] = None


def _wait_for_tx(server: SorobanServer, tx_hash: str, timeout_s: int = 30) -> SubmitResult:
    for _ in range(timeout_s):
        time.sleep(1)
        get = server.get_transaction(tx_hash)
        status = str(get.status)
        if "SUCCESS" in status:
            return SubmitResult(success=True, hash=tx_hash, status=status)
        if "FAILED" in status:
            return SubmitResult(
                success=False,
                hash=tx_hash,
                status=status,
                error=getattr(get, "result_xdr", "transaction failed"),
            )
        if "NOT_FOUND" not in status:
            return SubmitResult(success=False, hash=tx_hash, status=status, error=status)
    return SubmitResult(success=False, hash=tx_hash, status="TIMEOUT", error="timed out")


def _app_kind_scval(app_kind: str) -> stellar_xdr.SCVal:
    if app_kind not in {"Inkternity", "Andromica", "Pintheon", "Other"}:
        raise ValueError(f"unknown app_kind: {app_kind!r}")
    return scval.to_enum(app_kind, None)


def _invoke(
    *,
    server: SorobanServer,
    source_keypair: Keypair,
    contract_id: str,
    function_name: str,
    parameters: list,
    network_passphrase: str,
    base_fee: int = 1_000_000,
) -> SubmitResult:
    source_account = server.load_account(source_keypair.public_key)
    tx = (
        TransactionBuilder(
            source_account=source_account,
            network_passphrase=network_passphrase,
            base_fee=base_fee,
        )
        .append_invoke_contract_function_op(
            contract_id=contract_id,
            function_name=function_name,
            parameters=parameters,
        )
        .set_timeout(60)
        .build()
    )
    tx = server.prepare_transaction(tx)
    tx.sign(source_keypair)
    send = server.send_transaction(tx)
    if "ERROR" in str(send.status):
        return SubmitResult(
            success=False,
            hash=send.hash,
            status=str(send.status),
            error=getattr(send, "error_result_xdr", "send failed"),
        )
    return _wait_for_tx(server, send.hash)


def _simulate(
    *,
    server: SorobanServer,
    source_pub: str,
    contract_id: str,
    function_name: str,
    parameters: list,
    network_passphrase: str,
):
    """Read-only view simulation. Returns the result_value SCVal, or None
    if the contract returned `Option::None` (Soroban encodes this as Void)."""
    source_account = server.load_account(source_pub)
    tx = (
        TransactionBuilder(
            source_account=source_account,
            network_passphrase=network_passphrase,
            base_fee=100,
        )
        .append_invoke_contract_function_op(
            contract_id=contract_id,
            function_name=function_name,
            parameters=parameters,
        )
        .set_timeout(30)
        .build()
    )
    sim = server.simulate_transaction(tx)
    if sim.error:
        raise RuntimeError(f"simulate failed: {sim.error}")
    if not sim.results:
        return None
    raw_xdr = sim.results[0].xdr
    if raw_xdr is None:
        return None
    return stellar_xdr.SCVal.from_xdr(raw_xdr)


# ── State-changing calls ─────────────────────────────────────────────────────


def submit_register(
    *,
    rpc_url: str,
    network_passphrase: str,
    contract_id: str,
    app_keypair: Keypair,
    member_pubkey: bytes,
    app_kind: str,
    fingerprint: bytes,
    expires_at: int,
    nonce: int,
    auth_payload: bytes,
    auth_signature: bytes,
) -> SubmitResult:
    if len(member_pubkey) != 32:
        raise ValueError("member_pubkey must be 32 bytes")
    if len(fingerprint) != 32:
        raise ValueError("fingerprint must be 32 bytes")
    if len(auth_signature) != 64:
        raise ValueError("auth_signature must be 64 bytes")

    server = SorobanServer(rpc_url)
    params = [
        scval.to_address(app_keypair.public_key),
        scval.to_bytes(member_pubkey),
        _app_kind_scval(app_kind),
        scval.to_bytes(fingerprint),
        scval.to_string("ed25519"),
        scval.to_uint64(expires_at),
        scval.to_uint64(nonce),
        scval.to_bytes(auth_payload),
        scval.to_bytes(auth_signature),
    ]
    return _invoke(
        server=server,
        source_keypair=app_keypair,
        contract_id=contract_id,
        function_name="register_app_ca",
        parameters=params,
        network_passphrase=network_passphrase,
    )


def submit_rotate(
    *,
    rpc_url: str,
    network_passphrase: str,
    contract_id: str,
    app_keypair: Keypair,
    new_fingerprint: bytes,
    new_expires_at: int,
    nonce: int,
    auth_payload: bytes,
    auth_signature: bytes,
) -> SubmitResult:
    server = SorobanServer(rpc_url)
    params = [
        scval.to_address(app_keypair.public_key),
        scval.to_bytes(new_fingerprint),
        scval.to_uint64(new_expires_at),
        scval.to_uint64(nonce),
        scval.to_bytes(auth_payload),
        scval.to_bytes(auth_signature),
    ]
    return _invoke(
        server=server,
        source_keypair=app_keypair,
        contract_id=contract_id,
        function_name="rotate_app_ca",
        parameters=params,
        network_passphrase=network_passphrase,
    )


def submit_revoke_by_app(
    *,
    rpc_url: str,
    network_passphrase: str,
    contract_id: str,
    app_keypair: Keypair,
) -> SubmitResult:
    server = SorobanServer(rpc_url)
    params = [scval.to_address(app_keypair.public_key)]
    return _invoke(
        server=server,
        source_keypair=app_keypair,
        contract_id=contract_id,
        function_name="revoke_by_app",
        parameters=params,
        network_passphrase=network_passphrase,
    )


def submit_revoke_by_member(
    *,
    rpc_url: str,
    network_passphrase: str,
    contract_id: str,
    submitter_keypair: Keypair,   # any funded account can submit; auth is via sig
    app_address: str,
    nonce: int,
    auth_payload: bytes,
    auth_signature: bytes,
) -> SubmitResult:
    server = SorobanServer(rpc_url)
    params = [
        scval.to_address(app_address),
        scval.to_uint64(nonce),
        scval.to_bytes(auth_payload),
        scval.to_bytes(auth_signature),
    ]
    return _invoke(
        server=server,
        source_keypair=submitter_keypair,
        contract_id=contract_id,
        function_name="revoke_by_member",
        parameters=params,
        network_passphrase=network_passphrase,
    )


# ── Read-only views ──────────────────────────────────────────────────────────


def is_trusted(
    *,
    rpc_url: str,
    network_passphrase: str,
    contract_id: str,
    source_pub: str,
    app_address: str,
    fingerprint: bytes,
) -> bool:
    server = SorobanServer(rpc_url)
    raw = _simulate(
        server=server,
        source_pub=source_pub,
        contract_id=contract_id,
        function_name="is_trusted",
        parameters=[scval.to_address(app_address), scval.to_bytes(fingerprint)],
        network_passphrase=network_passphrase,
    )
    return bool(scval.to_native(raw)) if raw is not None else False


def get_app_ca_raw(
    *,
    rpc_url: str,
    network_passphrase: str,
    contract_id: str,
    source_pub: str,
    app_address: str,
):
    """Return the raw SCVal of the `Option<AppCaRecord>` for inspection.
    Callers that want a structured view can use scval.to_native() to
    materialize the struct as nested dicts."""
    server = SorobanServer(rpc_url)
    return _simulate(
        server=server,
        source_pub=source_pub,
        contract_id=contract_id,
        function_name="get_app_ca",
        parameters=[scval.to_address(app_address)],
        network_passphrase=network_passphrase,
    )
