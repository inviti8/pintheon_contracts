# Token Metadata with stellar.toml

This guide explains how to associate metadata (including images) with your Soroban token using the `stellar.toml` standard.

## 1. Set Up Your Domain

### Prerequisites:
- A domain name you own (e.g., `example.com`)
- Ability to modify DNS records
- HTTPS support (Let's Encrypt recommended)

### Steps:
1. **Purchase a domain** (if you don't have one)
   - Use a registrar like Namecheap, Google Domains, or Cloudflare

2. **Set up HTTPS**
   - Use Let's Encrypt for free SSL certificates
   - Most hosting providers offer one-click SSL setup
   - For manual setup:
     ```bash
     # Install certbot (Ubuntu/Debian)
     sudo apt install certbot python3-certbot-nginx
     
     # Get certificate
     sudo certbot --nginx -d yourdomain.com
     ```

## 2. Configure the Home Domain

### For Stellar Classic Assets:
1. **Set home_domain on issuing account**

   **Using Stellar CLI (Recommended):**
   ```bash
   # For testnet
   stellar --testnet tx new set-options \
     --source-account YOUR_ISSUER_SECRET \
     --home-domain yourdomain.com \
     --sign-with-key YOUR_ISSUER_SECRET

   # For mainnet
   stellar --pubnet tx new set-options \
     --source-account YOUR_ISSUER_SECRET \
     --home-domain yourdomain.com \
     --sign-with-key YOUR_ISSUER_SECRET
   ```

   **Verify the home domain was set:**
   ```bash
   # Check account details
   stellar --testnet account info YOUR_ISSUER_PUBLIC_KEY
   ```

   **Using Stellar SDK (Alternative):**
   ```python
   from stellar_sdk import Server, Keypair, TransactionBuilder, Network
   
   server = Server(horizon_url="https://horizon.stellar.org")
   source_keypair = Keypair.from_secret("YOUR_ISSUER_SECRET")
   
   account = server.load_account(source_keypair.public_key)
   
   transaction = TransactionBuilder(
       source_account=account,
       network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
       base_fee=100  # Stroops
   ).append_set_options_op(
       home_domain="yourdomain.com"
   ).build()
   
   transaction.sign(source_keypair)
   response = server.submit_transaction(transaction)
   ```

### For Soroban Smart Contracts:
1. **Set contract metadata**
   - Include the domain in your contract's initialization
   - Store it in the contract's storage:
     ```rust
     // In your contract code
     pub struct Contract;
     
     #[contractimpl]
     impl Contract {
         pub fn initialize(env: Env, domain: String) {
             // Store the domain in contract storage
             env.storage().set("domain", &domain);
         }
     }
     ```

## 3. Create and Host stellar.toml

### File Location:
- Must be served from: `https://yourdomain.com/.well-known/stellar.toml`
- Must be served with `Content-Type: text/plain`
- Must be accessible via HTTPS

### Example stellar.toml:
```toml
# Required: Basic information
VERSION="2.0.0"
NETWORK_PASSPHRASE="Public Global Stellar Network ; September 2015"

# Your organization details
DOCUMENTATION={
  ORG_NAME="Your Organization",
  ORG_DBA="Your DBA",
  ORG_URL="https://yourdomain.com",
  ORG_LOGO="https://yourdomain.com/logo.png",
  ORG_DESCRIPTION="Description of your organization",
  ORG_PHYSICAL_ADDRESS="123 Main St, City, Country",
  ORG_PHYSICAL_ADDRESS_ATTESTATION="https://yourdomain.com/address-verification",
  ORG_PHONE_NUMBER="+1234567890",
  ORG_OFFICIAL_EMAIL="contact@yourdomain.com"
}

# Your token(s)
[[CURRENCIES]]
code = "OPUS"
issuer = "YOUR_ISSUER_PUBLIC_KEY"
status = "live"
display_decimals = 7
name = "Opus Token"
desc = "Description of what Opus Token represents"
image = "https://yourdomain.com/images/opus-logo.png"

# Additional metadata (optional but recommended)
url = "https://yourdomain.com/tokens/opus"
fixed_number = 1000000000  # Total supply if fixed

# Contact information for verification
[[PRINCIPALS]]
name = "John Doe"
email = "security@yourdomain.com"
keybase = "johndoe"
twitter = "@johndoe"
github = "johndoe"

# Validators (if applicable)
[[VALIDATORS]]
ALIAS="validator-1"
DISPLAY_NAME="Main Validator"
HOST="core.yourdomain.com:11625"
PUBLIC_KEY="GABCD..."
HISTORY="https://history.yourdomain.com"
```

### Nginx Configuration:
```nginx
server {
    listen 443 ssl http2;
    server_name yourdomain.com;
    
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    
    # Serve stellar.toml
    location /.well-known/stellar.toml {
        default_type text/plain;
        add_header Access-Control-Allow-Origin *;
        alias /var/www/yourdomain.com/well-known/stellar.toml;
    }
    
    # Serve token images
    location /images/ {
        alias /var/www/yourdomain.com/images/;
        expires 30d;
        add_header Cache-Control "public, max-age=2592000";
    }
}
```

## 4. Verification and Testing

### 1. Verify Home Domain
```bash
# Using Stellar SDK
from stellar_sdk import Server

server = Server(horizon_url="https://horizon.stellar.org")
account = server.accounts().account_id("YOUR_ISSUER_PUBLIC_KEY").call()
print(f"Home domain: {account.get('home_domain')}")
```

### 2. Test stellar.toml Accessibility
```bash
# Check if file is accessible
curl -I https://yourdomain.com/.well-known/stellar.toml

# Should return:
# HTTP/2 200 
# content-type: text/plain
# access-control-allow-origin: *
```

### 3. Validate stellar.toml
Use the Stellar Laboratory or a TOML linter to ensure your file is properly formatted.

## Best Practices

1. **Image Guidelines**
   - Format: PNG or SVG
   - Size: 256x256 or 512x512 pixels
   - File size: Under 100KB
   - Transparent background recommended

2. **Security**
   - Always use HTTPS
   - Implement proper CORS headers
   - Set appropriate cache headers
   - Keep your SSL certificates up to date

3. **Performance**
   - Use a CDN for global distribution
   - Enable HTTP/2
   - Compress your TOML file

4. **Monitoring**
   - Set up monitoring for your stellar.toml endpoint
   - Monitor SSL certificate expiration
   - Track access logs for suspicious activity

## Troubleshooting

### Common Issues:
1. **CORS Errors**
   - Ensure your server sends the correct CORS headers
   - Test with: `curl -I https://yourdomain.com/.well-known/stellar.toml`

2. **SSL Issues**
   - Verify your certificate chain is complete
   - Check for mixed content warnings
   - Test with: `openssl s_client -connect yourdomain.com:443 -servername yourdomain.com`

3. **File Not Found**
   - Verify file permissions
   - Check web server configuration
   - Test with: `curl -v https://yourdomain.com/.well-known/stellar.toml`

## References
- [Stellar.toml Documentation](https://developers.stellar.org/docs/issuing-assets/publishing-asset-info/)
- [SEP-0001: stellar.toml](https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0001.md)
- [Stellar Laboratory](https://laboratory.stellar.org/#account-creator?network=public)
