"""Static protected-target data.

This module is code, not a bundled data file, so packaging cannot lose it and a
missing resource cannot silently disable protection. Users may *extend* the
process list at runtime, but nothing can shrink it below these defaults.
"""

from __future__ import annotations

# Core operating system, session and security processes. Named in lowercase.
PROTECTED_PROCESS_NAMES: frozenset[str] = frozenset(
    name.lower()
    for name in (
        # Kernel and session
        "System",
        "System Idle Process",
        "Registry",
        "MemCompression",
        "Secure System",
        "Idle",
        # Critical user-mode subsystems
        "smss.exe",
        "csrss.exe",
        "wininit.exe",
        "winlogon.exe",
        "services.exe",
        "lsass.exe",
        "lsaiso.exe",
        "svchost.exe",
        "fontdrvhost.exe",
        "dwm.exe",
        "audiodg.exe",
        "spoolsv.exe",
        "sihost.exe",
        "ctfmon.exe",
        "conhost.exe",
        "sppsvc.exe",
        # Shell and start experience (terminating these breaks the desktop)
        "explorer.exe",
        "taskhostw.exe",
        "startmenuexperiencehost.exe",
        "searchhost.exe",
        "searchapp.exe",
        "shellexperiencehost.exe",
        "runtimebroker.exe",
        # Windows security
        "msmpeng.exe",
        "mpdefendercoreservice.exe",
        "securityhealthservice.exe",
        "securityhealthsystray.exe",
        "nissrv.exe",
        "msmpeng.exe",
        "mssense.exe",
        "msseces.exe",
        "sensecncproxy.exe",
        "senseir.exe",
        "sgrmbroker.exe",
        # Servicing and update
        "trustedinstaller.exe",
        "tiworker.exe",
        "wuauclt.exe",
        "mousocoreworker.exe",
        "usoclient.exe",
        "windowsupdateelevatedinstaller.exe",
        "wmisvc.exe",
        "wmiprvse.exe",
    )
)

# Substrings that identify a security product by process name or publisher.
# Deliberately broad: a false positive here costs an unavailable recommendation,
# a false negative costs the user their antivirus.
SECURITY_VENDOR_MARKERS: tuple[str, ...] = (
    "msmpeng",
    "mpdefender",
    "securityhealth",
    "nissrv",
    "defender",
    "windows defender",
    "antivirus",
    "avast",
    "avgnt",
    "avguard",
    "avira",
    "bdagent",
    "bdservicehost",
    "bitdefender",
    "kaspersky",
    "avp.exe",
    "ekrn",
    "egui",
    "norton",
    "navw",
    "symantec",
    "mcafee",
    "mcshield",
    "sophos",
    "csfalcon",
    "csagent",
    "crowdstrike",
    "sentinelagent",
    "sentinelone",
    "mbam",
    "malwarebytes",
    "webroot",
    "wrsvc",
    "trend micro",
    "tmcc",
    "fsav",
    "fsecure",
    "gdata",
    "eset",
    "nod32",
    "emsisoft",
    "a2service",
    "vipre",
    "zonealarm",
    "comodo",
    "360tray",
    "huorong",
)

# Registry roots that may never be written by a normal optimization action.
# Hive names are uppercase and compared case-insensitively.
PROTECTED_REGISTRY_ROOTS: tuple[tuple[str, str], ...] = (
    ("HKLM", r"SAM"),
    ("HKLM", r"SECURITY"),
    ("HKLM", r"SYSTEM"),
    ("HKLM", r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"),
    ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies"),
    ("HKLM", r"SOFTWARE\Policies"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Policies"),
    # Direct Run-key writes are protected on purpose: startup changes must go
    # through the sanctioned StartupApproved mechanism so they stay reversible.
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Run"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
    ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
    ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"),
    ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"),
)

# Relative to %WINDIR% / %LOCALAPPDATA%, resolved at construction time.
PROTECTED_DIRECTORY_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("SYSTEMROOT", r""),
    ("SYSTEMROOT", r"System32"),
    ("SYSTEMROOT", r"SysWOW64"),
    ("SYSTEMROOT", r"WinSxS"),
    ("SYSTEMROOT", r"Boot"),
    ("PROGRAMFILES", r""),
    ("PROGRAMFILES_X86", r""),
    ("PROGRAMDATA", r"Microsoft"),
    ("SYSTEMDRIVE", r"Recovery"),
    ("SYSTEMDRIVE", r"$Recycle.Bin"),
    ("LOCALAPPDATA", r"Microsoft"),
)

# Specific subdirectories that are inside a protected root but are legitimate
# cleanup targets. Most specific rule wins; these are evaluated first.
QUARANTINE_EXCEPTION_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("SYSTEMROOT", r"Temp"),
    ("SYSTEMROOT", r"SoftwareDistribution\Download"),
    ("SYSTEMROOT", r"Logs\CBS"),
    ("LOCALAPPDATA", r"Temp"),
)

# Roots a file may be quarantined from without extra friction. Anything else is
# still possible but carries a higher risk level and needs explicit approval.
QUARANTINE_ROOT_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("SYSTEMROOT", r"Temp"),
    ("SYSTEMROOT", r"SoftwareDistribution\Download"),
    ("LOCALAPPDATA", r"Temp"),
    ("TEMP", r""),
)

__all__ = [
    "PROTECTED_DIRECTORY_TEMPLATES",
    "PROTECTED_PROCESS_NAMES",
    "PROTECTED_REGISTRY_ROOTS",
    "QUARANTINE_EXCEPTION_TEMPLATES",
    "QUARANTINE_ROOT_TEMPLATES",
    "SECURITY_VENDOR_MARKERS",
]
