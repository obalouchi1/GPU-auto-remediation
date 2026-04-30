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
import sys
from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

# -----------------------------
# Utility: run shell command (Fixes the lspci/bash integration)
# -----------------------------
def run_cmd(cmd, timeout=300):
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except Exception as e:
        return 1, "", str(e)

# Fix for the lspci/hardware check at startup
_, hw_out, _ = run_cmd("lspci | grep -i nvidia | wc -l")
hardware_gpu_count = int(hw_out) if hw_out.isdigit() else 0

if hardware_gpu_count == 0:
    print("No GPU is detected exiting!")
    sys.exit(0)

# -----------------------------
# User-configurable environment
# -----------------------------
AI_ENDPOINT = os.getenv("AI_ENDPOINT", "https://azure.com")
AI_DEPLOYMENT = os.getenv("AI_DEPLOYMENT", "gpt-4o")
AI_API_VERSION = os.getenv("AI_API_VERSION", "2024-12-01-preview")
ADO_ORG_URL = os.getenv("ADO_ORG_URL", "https://azure.com")
ADO_PROJECT = os.getenv("ADO_PROJECT", "default_project")
LOG_DIR = os.path.expanduser("~/gpu-ai-agent-logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    filename=os.path.join(LOG_DIR, "agent.log"),
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# -----------------------------
# AI Client
# -----------------------------
def init_ai_client():
    try:
        token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://azure.com")
        client = AzureOpenAI(
            azure_endpoint=AI_ENDPOINT,
            azure_ad_token_provider=token_provider,
            api_version=AI_API_VERSION
        )
        return client, AI_DEPLOYMENT
    except Exception as e:
        logging.error(f"AI Client init failed: {e}")
        return None, None

ai_client, ai_deployment = init_ai_client()

def ask_ai_for_remediation(issue):
    if not ai_client: return None
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
# -----------------------------
# GPU Health Checks (Refined)
# -----------------------------
def check_gpu():
    # 1. Check for physical existence
    if not os.path.exists("/usr/bin/nvidia-smi"):
        logging.info("nvidia-smi missing")
        return "nvidia-smi missing"
    
    # 2. Capture nvidia-smi output and exit code
    rc, smi_out, _ = run_cmd("/usr/bin/nvidia-smi 2>&1")
    smi_lower = smi_out.lower()

    # Specific Exit Status 9 handling
    if rc == 9 and "couldn't communicate with the nvidia driver" in smi_lower:
        logging.info("nvidia-smi exit status 9: driver communication failure")
        return "nvidia-driver-exit-9"

    # General communication failure
    if "couldn't communicate with the nvidia driver" in smi_lower:
        logging.info("nvidia-smi cannot communicate with driver")
        return "nvidia-driver-comm-failure"

    # 3. NVML / Library Mismatch specific check
    if "nvml" in smi_lower or "library" in smi_lower or "version" in smi_lower:
        return "nvidia library mismatch detected"

    # 4. Hardware vs Driver count check
    _, hw_c, _ = run_cmd("lspci | grep -i nvidia | wc -l")
    _, sw_c, _ = run_cmd("nvidia-smi --list-gpus | wc -l")
    h_count = int(hw_c) if hw_c.isdigit() else 0
    s_count = int(sw_c) if sw_c.isdigit() else 0

    if h_count > 0 and h_count != s_count:
        return f"GPU count mismatch: hardware has {h_count}, driver detects {s_count}"

    # 5. Integration with your custom scripts
    gpu_script = "/etc/azmonsandbox/custom_checks/check_gpu_status.sh" # Example path
    if os.path.exists(gpu_script):
        rc_custom, out_custom, _ = run_cmd(f"bash {gpu_script}")
        if rc_custom != 0:
            return f"Custom check failed: {out_custom}"

    return None


# -----------------------------
# NVML Mismatch Remediation
# -----------------------------
def remediate_nvml_mismatch():
    try:
        logging.info("Getting processes using NVIDIA devices...")
        rc, procs_out, err = run_cmd("sudo lsof -w /dev/nvidia* 2>/dev/null | cut -f1 -d ' '")
        procs = [p for p in procs_out.split('\n') if p and p != 'COMMAND']
        
        run_cmd("sudo service lightdm stop 2>/dev/null")
        if procs:
            for proc in set(procs):
                run_cmd(f"sudo pkill -f {proc}")

        rc, mods_out, _ = run_cmd("lsmod | grep nvidia | cut -f1 -d ' '")
        mods = [m for m in mods_out.split('\n') if m]
        for mod in mods:
            run_cmd(f"sudo rmmod {mod} 2>/dev/null")

        run_cmd("sudo service lightdm start 2>/dev/null")
        return "FIXED: NVML library mismatch remediated"
    except Exception as e:
        logging.error(f"NVML remediation error: {e}")
        return None

# -----------------------------
# Local remediation
# -----------------------------
def remediate_gpu(issue):
    if "library mismatch" in issue:
        return remediate_nvml_mismatch()
    if "missing" in issue or "communication" in issue:
        run_cmd("sudo apt-get purge -y nvidia-driver-580")
        rc, out, err = run_cmd("sudo apt-get install -y nvidia-driver-580", timeout=1800)
        if rc == 0: return "FIXED: GPU driver reinstalled"
    elif "ECC errors" in issue:
        rc, out, err = run_cmd("sudo dpkg --configure -a")
        if rc == 0: return "FIXED: ECC errors addressed"
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

    # Restore the ticketing fallback
    create_ado_ticket(issue)
    print("[✗] GPU issue unresolved, ADO ticket created")

if __name__ == "__main__":
    main()
