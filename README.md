# GPU AI Troubleshooting Agent - Setup Guide

**Maintainer:** Omid Balouchi <obalouchi1@gmail.com>

---

## Quick Start

```bash
# 1. Install dependencies
pip install openai azure-identity

# 2. Set environment variables (required)
export AI_ENDPOINT="https://your-resource.openai.azure.com/"
export AI_DEPLOYMENT="gpt-4o"

# 3. Run
python3 gpu-ai-agent.py
```

---

## What It Does

1. **Checks GPU health** - Monitors NVIDIA status
2. **Detects issues** - NVML mismatches, driver failures, ECC errors
3. **Auto-fixes** - Runs remediation locally
4. **Asks AI** - Uses GPT-4o for smart solutions if local fix fails
5. **Creates tickets** - Escalates to Azure DevOps if everything fails

---

## Configuration Variables

### Required (Must Set)

| Variable | Purpose | Example |
|----------|---------|---------|
| `AI_ENDPOINT` | Azure OpenAI endpoint | `https://my-ai.openai.azure.com/` |
| `AI_DEPLOYMENT` | GPT-4o deployment name | `gpt-4o` |

### Optional (Nice to Have)

| Variable | Purpose | Default |
|----------|---------|---------|
| `AI_API_VERSION` | OpenAI API version | `2024-12-01-preview` |
| `ADO_ORG_URL` | Azure DevOps org URL | `https://dev.azure.com/obalouchi` |
| `ADO_PROJECT` | Azure DevOps project | `default_project` |
| `ADO_PAT_TOKEN` | DevOps Personal Access Token | (empty) |

---

## Setup Methods

### Method 1: Environment Variables

```bash
export AI_ENDPOINT="https://your-resource.openai.azure.com/"
export AI_DEPLOYMENT="gpt-4o"
export ADO_ORG_URL="https://dev.azure.com/your-org"
export ADO_PROJECT="gpu-monitoring"
export ADO_PAT_TOKEN="your-pat-token"

python3 gpu-ai-agent.py
```

### Method 2: Create .env File

```bash
cat > .env << 'EOF'
AI_ENDPOINT=https://your-resource.openai.azure.com/
AI_DEPLOYMENT=gpt-4o
AI_API_VERSION=2024-12-01-preview
ADO_ORG_URL=https://dev.azure.com/your-org
ADO_PROJECT=gpu-monitoring
ADO_PAT_TOKEN=your-pat-token
EOF

source .env
python3 gpu-ai-agent.py
```

---

## Getting Azure Credentials

### Azure OpenAI

1. Go to https://portal.azure.com
2. Create "Azure OpenAI Service" resource
3. Deploy GPT-4o model
4. Get endpoint & deployment name from resource overview

**Find your endpoint:**
- Portal → OpenAI resource → Keys and Endpoint
- Copy the Endpoint URL
- Copy your deployment name (e.g., "gpt-4o")

### Azure DevOps (For Ticket Creation)

1. Create organization: https://dev.azure.com
2. Create a project (e.g., "gpu-monitoring")
3. Generate Personal Access Token (PAT):
   - Click your profile icon (top-left)
   - Settings → Personal access tokens
   - New Token → Name it, select "Work Items" (read & write)
   - Copy the token (won't show again!)

**Your org URL:**
- `https://dev.azure.com/your-organization-name`

**Your project name:**
- The name you created (e.g., "gpu-monitoring")

---

## How It Works

```
GPU Health Check
    ↓
Issue Detected?
    ├─ No → Done ✓
    ├─ NVML Mismatch → Remediate (kill processes, unload modules)
    ├─ Driver Issue → Reinstall driver
    ├─ ECC Errors → dpkg reconfigure
    └─ Other Issue → Ask AI (GPT-4o)
            ├─ AI suggests fix
            │   ├─ Works → Done ✓
            │   └─ Fails → Create ADO Ticket
            └─ No PAT token → Log only
```

---

## View Logs

```bash
# Real-time logs
tail -f ~/gpu-ai-agent-logs/agent.log

# View last 50 lines
tail -50 ~/gpu-ai-agent-logs/agent.log

# Search for errors
grep ERROR ~/gpu-ai-agent-logs/agent.log
```

---

## Troubleshooting

### "nvidia-smi not found"
```bash
sudo apt-get install nvidia-driver-580
nvidia-smi  # Test
```

### "Failed to initialize AI client"
```bash
# Verify credentials
az login
az account show

# Test endpoint
curl -I https://your-endpoint.openai.azure.com/
```

### "ADO_PAT_TOKEN not set"
- Optional warning - system still works without it
- Tickets won't be created, issues logged only
- Set token to enable ticketing

### Permission denied for NVML remediation
```bash
# Add sudoers permissions
sudo visudo

# Add this line (replace 'user' with your username):
user ALL=(ALL) NOPASSWD: /usr/bin/lsof, /usr/bin/pkill, /usr/bin/lsmod, /usr/bin/rmmod, /usr/sbin/service
```

---

## Running Modes

### Once (Manual)
```bash
python3 gpu-ai-agent.py
```

### As Cron Job (Every 5 minutes)
```bash
crontab -e

# Add this line:
*/5 * * * * cd /path/to/gpu-ai-agent && source .env && python3 gpu-ai-agent.py >> /var/log/gpu-agent.log 2>&1
```

### As Systemd Service (Continuous)
```bash
sudo tee /etc/systemd/system/gpu-ai-agent.service > /dev/null <<EOF
[Unit]
Description=GPU AI Troubleshooting Agent
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
EnvironmentFile=$(pwd)/.env
ExecStart=/usr/bin/python3 $(pwd)/gpu-ai-agent.py
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable gpu-ai-agent
sudo systemctl start gpu-ai-agent
sudo systemctl status gpu-ai-agent
```

---

## Example .env File

```bash
# Azure OpenAI (Required)
AI_ENDPOINT=https://my-ai-resource.openai.azure.com/
AI_DEPLOYMENT=gpt-4o
AI_API_VERSION=2024-12-01-preview

# Azure DevOps (Optional - for ticket creation)
ADO_ORG_URL=https://dev.azure.com/mycompany
ADO_PROJECT=gpu-monitoring
ADO_PAT_TOKEN=pnncd7dq5xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxzq
```

---

## Files

| File | Purpose |
|------|---------|
| `gpu-ai-agent.py` | Main agent (all-in-one) |
| `requirements.txt` | Python dependencies |
| `HOW_IT_WORKS.md` | Quick overview |
| `.env` | Your configuration (don't commit) |

---

## Requirements

- Python 3.7+
- openai package
- azure-identity package
- NVIDIA GPU with drivers
- Linux (Ubuntu 18.04+)
- sudo access for remediation

---

## Security Notes

1. **Never commit .env to git:**
   ```bash
   echo ".env" >> .gitignore
   ```

2. **Keep PAT token secure:**
   - Regenerate if exposed
   - Use minimal permissions (work items only)

3. **Restrict script permissions:**
   ```bash
   chmod 700 gpu-ai-agent.py
   chmod 600 .env
   ```

---

## Support

**Issues?** Check logs:
```bash
tail -f ~/gpu-ai-agent-logs/agent.log
```

**Questions?** Contact: Omid Balouchi <obalouchi1@gmail.com>
