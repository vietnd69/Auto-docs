---
name: enforce_python_venv
description: Ensure the Agent always executes Python code and manages packages within a local virtual environment (.venv), strictly avoiding the system's global environment.
author: System
tags: [python, venv, execution, pip, environment-management]
triggers:
  - User requests to run a .py file.
  - User requests to install/uninstall libraries (pip install/uninstall).
  - User requests to run Python CLI tools (e.g., pytest, black, django-admin, uvicorn).
  - Need to run a .py file.
---

# Agent Skill: Enforce Python Virtual Environment (.venv)

## 1. Objective
Force the Agent to use the **Direct Path** to the Python executable inside the `.venv` directory. This maintains project isolation and prevents issues caused by the loss of the activation state across different non-interactive terminal sessions.

## 2. Triggers
Activate this skill BEFORE executing any shell/terminal command containing keywords such as: `python`, `python3`, `pip`, `pip3`, `pytest`, or when interacting with any Python packages.

## 3. Execution Instructions

The Agent MUST strictly follow these steps:

### Step 1: OS Detection
- Identify the current operating system (Windows, Linux, or macOS) to format the executable path correctly.

### Step 2: Check Virtual Environment Existence
- Check if a `.venv` (or `venv`, `env`) directory exists at the root of the project workspace.
- **If it DOES NOT exist:** Automatically create the virtual environment first:
  - Command: `python -m venv .venv` (or `python3 -m venv .venv`).
  - Wait for the creation process to finish before proceeding to Step 3.
- **If it DOES exist:** Proceed directly to Step 3.

### Step 3: Direct Path Execution (Mandatory)
Absolutely **DO NOT** use environment activation commands like `source .venv/bin/activate` or `.venv/Scripts/activate`, as the Agent's sub-shell may not retain the state for subsequent commands. You must use the direct path to the executable:

* **For Windows:**
  - Run script: `.venv/Scripts/python.exe <filename>.py`
  - Manage pip: `.venv/Scripts/python.exe -m pip install <package_name>`
  - Run module: `.venv/Scripts/python.exe -m <module_name>`

### Step 4: Post-Execution (Recommended)
- If a `pip install` or `pip uninstall` command was just executed, automatically update the requirements file to reflect the changes:
  - Windows: `.venv\Scripts\python.exe -m pip freeze > requirements.txt`

## 4. Constraints
- **NEVER** run `pip install` directly without the `.venv` path prefix.
- **NEVER** modify or install packages to the system's global Python environment.
- If a `Permission denied` error occurs (on Unix-like systems), automatically grant execution permissions (e.g., `chmod +x .venv/bin/python`) before retrying.

## 5. Few-Shot Examples

### Example 1: Install a new package
**User Input:** "Install the numpy library for me."
**Agent Action:**
```bash
.venv\Scripts\python.exe -m pip install numpy
.venv\Scripts\python.exe -m pip freeze > requirements.txt