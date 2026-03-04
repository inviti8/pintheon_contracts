# Local Stellar Node Setup with Docker

## 🎯 Objective
Create a Python script to automate local Stellar RPC node setup using official Docker images for reliable Soroban contract deployment.

## 📋 Requirements

### 🔧 Core Functionality
1. **Docker Management**
   - Check if Docker is installed and running
   - Detect if `stellar/soroban-rpc` image exists locally
   - Download image if missing
   - Create persistent storage volumes
   - Start/stop/restart container management

2. **Configuration Setup**
   - Generate `stellar-core.toml` configuration file
   - Set up proper network parameters (mainnet/testnet)
   - Configure persistent storage paths
   - Handle port mapping (8000/8001)

3. **Sync Monitoring**
   - Monitor sync progress
   - Detect when node is fully synced
   - Provide health check functionality
   - Show estimated time remaining

4. **Integration**
   - Update `deploy_contracts.py` to use local RPC URL
   - Handle fallback to public endpoints
   - Provide status reporting

### 📚 Official Documentation References

#### **Stellar RPC Docker Image**
- **Official Repository**: https://github.com/stellar/stellar-rpc
- **Docker Hub**: https://hub.docker.com/r/stellar/soroban-rpc
- **Documentation**: https://developers.stellar.org/docs/data/apis/rpc/

#### **Configuration References**
- **stellar-core.toml**: https://github.com/stellar/stellar-core/blob/master/docs/stellar-core.md
- **Network Passphrases**: https://developers.stellar.org/docs/start/network/

#### **Alternative RPC Providers**
- **Official Provider List**: https://developers.stellar.org/docs/data/apis/rpc/providers/

## 🏗️ Implementation Plan

### Phase 1: Docker Setup
```python
# Core functions to implement:
- check_docker_installation()
- check_image_exists(image_name)
- pull_docker_image(image_name)
- create_required_directories()
- generate_stellar_config(network)
```

### Phase 2: Container Management
```python
# Container operations:
- start_stellar_container(network, config_path)
- stop_stellar_container(container_name)
- restart_stellar_container(container_name)
- check_container_status(container_name)
```

### Phase 3: Sync Monitoring
```python
# Sync and health monitoring:
- check_sync_status(rpc_url)
- monitor_sync_progress()
- wait_until_synced(timeout=3600)  # 1 hour max
- get_node_health(rpc_url)
```

### Phase 4: Integration
```python
# Integration with deployment script:
- update_deploy_script_rpc_url()
- test_local_rpc_connection()
- fallback_to_public_endpoints()
```

## 🐳 Docker Commands to Automate

### Image Pull
```bash
docker pull stellar/soroban-rpc:latest
```

### Container Start (Mainnet)
```bash
docker run -d \
  --name soroban-rpc-mainnet \
  -p 8000:8000 -p 8001:8001 \
  -v /home/user/soroban-rpc:/config \
  -v soroban-data:/var/lib/stellar \
  stellar/soroban-rpc \
  --captive-core-config-path="/config/stellar-core.toml" \
  --captive-core-storage-path="/var/lib/stellar/captive-core" \
  --db-path="/var/lib/stellar/soroban-rpc-db.sqlite" \
  --network-passphrase="Public Global Stellar Network ; September 2015" \
  --history-archive-urls="https://history.stellar.org/prd/core-live/core_live_001" \
  --admin-endpoint="0.0.0.0:8001" \
  --endpoint="0.0.0.0:8000"
```

### Container Start (Testnet)
```bash
docker run -d \
  --name soroban-rpc-testnet \
  -p 8000:8000 -p 8001:8001 \
  -v /home/user/soroban-rpc:/config \
  -v soroban-data:/var/lib/stellar \
  stellar/soroban-rpc \
  --network-passphrase="Test SDF Network ; September 2015" \
  --history-archive-urls="https://history.stellar.org/prd/core-testnet/core_testnet_001"
```

## 📁 File Structure
```
philos_contracts/
├── setup_local_stellar.py          # Main automation script
├── soroban-rpc/                 # Config directory
│   └── stellar-core.toml         # Generated config file
├── deployments.json               # Current deployments
└── deploy_contracts.py           # Updated to use local RPC
```

## 🚀 Usage Flow
1. Run `python setup_local_stellar.py --network mainnet`
2. Script detects Docker, pulls image, generates config
3. Starts container and monitors sync
4. Updates `deploy_contracts.py` with local RPC URL
5. Provides status updates and health checks
6. Ready for contract deployment

## ⚡ Benefits
- **Reliable**: No public endpoint congestion
- **Fast**: Local network access
- **Unlimited**: No rate limiting
- **Private**: Your own infrastructure
- **Persistent**: Data preserved across restarts
- **Automated**: One-command setup
