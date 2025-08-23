#!/usr/bin/env node

const {
  Keypair,
  Networks,
  SorobanRpc,
  TransactionBuilder,
  Operation,
  Asset,
  Contract,
  Address,
  nativeToScVal,
  scValToNative,
} = require('@stellar/stellar-sdk');
const fs = require('fs');
const path = require('path');

// Configuration
const RPC_URL = 'https://soroban-testnet.stellar.org:443';
const NETWORK_PASSPHRASE = Networks.TESTNET;

async function deployContract(wasmPath, constructorArgs = []) {
  try {
    console.log('🚀 Starting contract deployment with JS SDK...');
    
    // Initialize RPC client
    const server = new SorobanRpc.Server(RPC_URL);
    
    // Generate or load keypair
    const keypair = Keypair.random();
    console.log(`📋 Generated account: ${keypair.publicKey()}`);
    
    // Fund account
    console.log('💰 Funding account...');
    const friendbotUrl = `https://friendbot.stellar.org?addr=${keypair.publicKey()}`;
    await fetch(friendbotUrl);
    
    // Wait for account to be funded
    await new Promise(resolve => setTimeout(resolve, 5000));
    
    // Load account
    const account = await server.getAccount(keypair.publicKey());
    console.log(`✅ Account loaded, sequence: ${account.sequenceNumber()}`);
    
    // Read WASM file
    const wasmBuffer = fs.readFileSync(wasmPath);
    console.log(`📦 WASM file loaded: ${wasmBuffer.length} bytes`);
    
    // Step 1: Upload WASM
    console.log('📤 Uploading WASM...');
    const uploadTx = new TransactionBuilder(account, {
      fee: '1000000',
      networkPassphrase: NETWORK_PASSPHRASE,
    })
      .addOperation(Operation.uploadContractWasm({ wasm: wasmBuffer }))
      .setTimeout(300)
      .build();
    
    uploadTx.sign(keypair);
    
    const uploadResult = await server.sendTransaction(uploadTx);
    console.log(`📤 Upload transaction: ${uploadResult.hash}`);
    
    if (uploadResult.status !== 'SUCCESS') {
      throw new Error(`Upload failed: ${uploadResult.errorResult}`);
    }
    
    // Get WASM hash from result
    const wasmHash = uploadResult.returnValue;
    console.log(`🔗 WASM hash: ${wasmHash}`);
    
    // Step 2: Deploy contract
    console.log('🚀 Deploying contract...');
    
    // Reload account for new sequence number
    const account2 = await server.getAccount(keypair.publicKey());
    
    const deployTx = new TransactionBuilder(account2, {
      fee: '1000000',
      networkPassphrase: NETWORK_PASSPHRASE,
    })
      .addOperation(Operation.createContract({
        wasmHash: wasmHash,
        address: keypair.publicKey(),
        salt: Buffer.alloc(32), // Random salt
      }))
      .setTimeout(300)
      .build();
    
    deployTx.sign(keypair);
    
    const deployResult = await server.sendTransaction(deployTx);
    console.log(`🚀 Deploy transaction: ${deployResult.hash}`);
    
    if (deployResult.status !== 'SUCCESS') {
      throw new Error(`Deploy failed: ${deployResult.errorResult}`);
    }
    
    const contractAddress = deployResult.returnValue;
    console.log(`✅ Contract deployed at: ${contractAddress}`);
    
    // Step 3: Initialize contract if constructor args provided
    if (constructorArgs.length > 0) {
      console.log('🔧 Initializing contract...');
      
      const account3 = await server.getAccount(keypair.publicKey());
      
      const initTx = new TransactionBuilder(account3, {
        fee: '1000000',
        networkPassphrase: NETWORK_PASSPHRASE,
      })
        .addOperation(Operation.invokeContract({
          contract: contractAddress,
          function: '__constructor',
          args: constructorArgs,
        }))
        .setTimeout(300)
        .build();
      
      initTx.sign(keypair);
      
      const initResult = await server.sendTransaction(initTx);
      console.log(`🔧 Init transaction: ${initResult.hash}`);
      
      if (initResult.status !== 'SUCCESS') {
        throw new Error(`Initialization failed: ${initResult.errorResult}`);
      }
    }
    
    return {
      contractAddress,
      wasmHash,
      deployerAccount: keypair.publicKey(),
    };
    
  } catch (error) {
    console.error('❌ Deployment failed:', error.message);
    throw error;
  }
}

// Main execution
async function main() {
  const wasmPath = process.argv[2];
  if (!wasmPath) {
    console.error('Usage: node deploy_with_js.js <wasm_file_path>');
    process.exit(1);
  }
  
  if (!fs.existsSync(wasmPath)) {
    console.error(`WASM file not found: ${wasmPath}`);
    process.exit(1);
  }
  
  try {
    const result = await deployContract(wasmPath);
    console.log('\n🎉 Deployment successful!');
    console.log(`Contract Address: ${result.contractAddress}`);
    console.log(`WASM Hash: ${result.wasmHash}`);
    console.log(`Deployer: ${result.deployerAccount}`);
  } catch (error) {
    console.error('\n💥 Deployment failed:', error.message);
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}

module.exports = { deployContract };
