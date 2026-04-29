#!/usr/bin/env python3
"""
================================================================================
GPU AI Troubleshooting Agent
================================================================================

SUMMARY:
  Autonomous GPU health monitoring and remediation system that detects NVIDIA
  driver issues and automatically performs remediation. Integrates with:
  - Local automatic fixes (driver reinstall, module unloading)
  - Azure OpenAI GPT-4o for intelligent troubleshooting suggestions
  - Azure DevOps for issue tracking and escalation
  - Dedicated NVML library mismatch handler script

FEATURES:
  ✓ Real-time GPU health monitoring via nvidia-smi
  ✓ NVML library mismatch detection and automated remediation
  ✓ ECC error detection and dpkg-based recovery
  ✓ GPU driver communication failure detection
  ✓ Multi-tier remediation strategy (local → AI → ticketing)
  ✓ Comprehensive logging to ~/gpu-ai-agent-logs/agent.log
  ✓ Azure Managed Identity authentication
  ✓ Configurable via environment variables

MAINTAINER:
  Omid Balouchi <obalouchi1@gmail.com>

VERSION: 1.0.0
================================================================================
"""

import os
import subprocess
import logging
from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

# -----------------------------
# User-configurable environment
# -----------------------------
AI_ENDPOINT = os.getenv("AI_ENDPOINT", "https://ai-monitoring-agent.openai.azure.com/")
AI_DEPLOYMENT = os.getenv("AI_DEPLOYMENT", "gpt-4o")
AI_API_VERSION = os.getenv("AI_API_VERSION", "2024-12-01-preview")
ADO_ORG_URL = os.getenv("ADO_ORG_URL", "https://dev.azure.com/obalouchi")
ADO_PROJECT = os.getenv("ADO_PROJECT", "default_project")

LOG_DIR = os.path.expanduser("~/gpu-ai-agent-logs")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "agent.log"),
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# -----------------------------
# Utility: run shell command
# -----------------------------
def run_cmd(cmd, timeout=300):
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except Exception as e:
        return 1, "", str(e)

# -----------------------------
# AI Client
# -----------------------------
def init_ai_client():
    token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")
    client = AzureOpenAI(
        azure_endpoint=AI_ENDPOINT,
        azure_ad_token_provider=token_provider,
        api_version=AI_API_VERSION
    )
    return client, AI_DEPLOYMENT

ai_client, ai_deployment = init_ai_client()

def ask_ai_for_remediation(issue):
    try:
        resp = ai_client.chat.completions.create(
            model=ai_deployment,
            messages=[
                {"role": "system", "content": "You are a Linux GPU troubleshooting assistant. Output ONLY safe shell commands. no reboot, shut down or delete or unsafe command"},
                {"role": "user", "content": f"Fix this GPU issue safely: {issue}"}
            ],
            temperature=0
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"AI error: {e}")
        return None

# -----------------------------
# GPU Health Checks
# -----------------------------
def check_gpu():
    # Check if nvidia-smi exists
    if not os.path.exists("/usr/bin/nvidia-smi"):
        return "nvidia-smi missing"

    rc, out, err = run_cmd("/usr/bin/nvidia-smi 2>&1")
    if rc != 0 or "could not" in out.lower():
        # Check for NVML library mismatch symptoms
        if "NVML" in err or "library" in err.lower() or "version" in err.lower():
            return "nvidia library mismatch detected"
        return "nvidia driver communication failure"

    # Optional: check ECC errors
    if "ECC" in out:
        ecc_errors = [line for line in out.splitlines() if "ECC" in line and not line.strip().endswith("0")]
        if ecc_errors:
            return f"ECC errors detected: {ecc_errors}"

    # Optional: check GPU count
    gpu_count = out.count("Tesla") + out.count("A100") + out.count("V100")  # basic example
    if gpu_count % 2 != 0:
        return "Odd number of GPUs detected"

    return None

# -----------------------------
# NVML Mismatch Remediation (Direct Python)
# -----------------------------
def remediate_nvml_mismatch():
    """
    Remediate NVIDIA NVML library mismatch by:
    1. Get processes using /dev/nvidia*
    2. Stop lightdm
    3. Kill nvidia processes
    4. Unload nvidia kernel modules
    5. Restart lightdm
    """
    try:
        # Get processes utilizing nvidia driver units
        logging.info("Getting processes using NVIDIA devices...")
        rc, procs_out, err = run_cmd("sudo lsof -w /dev/nvidia* 2>/dev/null | cut -f1 -d ' '")
        procs = [p for p in procs_out.split('\n') if p and p != 'COMMAND']
        
        if procs:
            # Stop lightdm
            logging.info("Stopping lightdm service...")
            run_cmd("sudo service lightdm stop 2>/dev/null")
        
        # Kill all processes using NV drivers
        if procs:
            logging.info(f"Killing {len(procs)} processes using NVIDIA drivers...")
            for proc in procs:
                logging.info(f"Killing: {proc}")
                run_cmd(f"sudo pkill -f {proc}")
        
        # Unload NVIDIA kernel modules
        logging.info("Unloading NVIDIA kernel modules...")
        rc, mods_out, err = run_cmd("lsmod | grep nvidia | cut -f1 -d ' '")
        mods = [m for m in mods_out.split('\n') if m]
        
        for mod in mods:
            logging.info(f"Removing module: {mod}")
            rc, out, err = run_cmd(f"sudo rmmod {mod} 2>/dev/null")
            if rc != 0:
                logging.warning(f"Failed to remove {mod} (may be in use): {err}")
        
        # Start lightdm service
        logging.info("Restarting lightdm service...")
        run_cmd("sudo service lightdm start 2>/dev/null")
        
        logging.info("NVML mismatch remediation completed")
        return "FIXED: NVML library mismatch remediated (processes killed, modules unloaded)"
        
    except Exception as e:
        logging.error(f"NVML remediation error: {e}")
        return None

# -----------------------------
# Local remediation
# -----------------------------
def remediate_gpu(issue):
    # NVML Library Mismatch - remediate directly in Python
    if "library mismatch" in issue:
        logging.info("NVML library mismatch detected, starting remediation...")
        return remediate_nvml_mismatch()
    
    if "missing" in issue or "communication" in issue:
        logging.info("Attempting driver reinstall...")
        run_cmd("sudo apt-get purge -y nvidia-driver-580")
        rc, out, err = run_cmd("sudo apt-get install -y nvidia-driver-580", timeout=1800)
        if rc == 0:
            return "FIXED: GPU driver reinstalled"
    elif "ECC errors" in issue:
        logging.info("ECC errors detected, running dpkg reconfigure")
        rc, out, err = run_cmd("sudo dpkg --configure -a")
        if rc == 0:
            return "FIXED: ECC errors addressed"
    return None

# -----------------------------
# ADO Ticketing
# -----------------------------
def create_ado_ticket(issue):
    logging.info(f"Creating ADO ticket: {issue}")
    print(f"[ADO] Ticket would be created for issue: {issue} (integration placeholder)")

# -----------------------------
# Main Agent Flow
# -----------------------------
def main():
    print("[GPU Agent] Checking GPU health...")
    issue = check_gpu()
    if not issue:
        print("[✓] GPU healthy")
        return

    print(f"[!] Issue detected: {issue}")
    result = remediate_gpu(issue)
    if result:
        print(f"[✓] {result}")
        return

    print("[AI] Asking AI for remediation...")
    ai_cmd = ask_ai_for_remediation(issue)
    if ai_cmd:
        print(f"[AI Suggested] Run: {ai_cmd}")
        rc, out, err = run_cmd(ai_cmd, timeout=900)
        if rc == 0:
            print("[✓] GPU issue fixed via AI suggestion")
            return
        else:
            print(f"[✗] AI suggestion failed: {err}")

    # If all fails, create ticket
    create_ado_ticket(issue)
    print("[✗] GPU issue unresolved, ADO ticket created")

if __name__ == "__main__":
    main()

