"""
ArchiScraper Build Script

This script builds ArchiScraper into a standalone executable.
It automatically installs PyInstaller if not present and bundles the icon.
Cross-platform support: Works on Windows, macOS, and Linux.

Usage:
    python build_app.py

Output:
    Windows: dist/ArchiScraper.exe
    macOS:   dist/ArchiScraper (binary) or dist/ArchiScraper.app (bundle)
    Linux:   dist/ArchiScraper
"""

import subprocess
import sys
import os
import platform


def get_os_info():
    """Detect the current operating system and return relevant build info."""
    current_os = platform.system()
    
    if current_os == "Windows":
        return {
            "name": "Windows",
            "separator": ";",  # Windows uses semicolon for --add-data
            "exe_name": "ArchiScraper.exe",
            "exe_description": "dist/ArchiScraper.exe"
        }
    elif current_os == "Darwin":
        return {
            "name": "macOS",
            "separator": ":",  # macOS/Unix uses colon for --add-data
            "exe_name": "ArchiScraper",
            "exe_description": "dist/ArchiScraper (binary) or dist/ArchiScraper.app (bundle)"
        }
    else:  # Linux and other Unix-like systems
        return {
            "name": "Linux",
            "separator": ":",  # Linux/Unix uses colon for --add-data
            "exe_name": "ArchiScraper",
            "exe_description": "dist/ArchiScraper"
        }


def check_and_install_pyinstaller():
    """Install PyInstaller if not already installed."""
    try:
        import PyInstaller
        print(f"✓ PyInstaller {PyInstaller.__version__} is installed")
        return True
    except ImportError:
        print("PyInstaller not found. Installing...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("✓ PyInstaller installed successfully")
            return True
        else:
            print(f"✗ Failed to install PyInstaller: {result.stderr}")
            return False


def check_and_install_pillow():
    """Install Pillow if not already installed (needed for icon processing)."""
    try:
        import PIL
        print(f"✓ Pillow {PIL.__version__} is installed")
        return True
    except ImportError:
        print("Pillow not found. Installing...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "Pillow"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("✓ Pillow installed successfully")
            return True
        else:
            print(f"✗ Failed to install Pillow: {result.stderr}")
            return False


def build_executable():
    """Build the ArchiScraper executable using PyInstaller."""
    
    # Get OS-specific configuration
    os_info = get_os_info()
    print(f"✓ Detected platform: {os_info['name']}")
    
    # Paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    main_script = os.path.join(script_dir, "scripts", "ArchiScraperApp.py")
    icon_file = os.path.join(script_dir, "icon.png")
    
    # Verify files exist
    if not os.path.exists(main_script):
        print(f"✗ Error: Main script not found at {main_script}")
        return False
    
    if not os.path.exists(icon_file):
        print(f"⚠ Warning: Icon file not found at {icon_file}")
        print("  The executable will be built without a custom icon.")
        icon_arg = []
        add_data_arg = []
    else:
        print(f"✓ Found icon: {icon_file}")
        icon_arg = ["--icon", icon_file]
        # Use OS-specific separator for --add-data
        separator = os_info["separator"]
        add_data_arg = ["--add-data", f"{icon_file}{separator}."]
    
    # Build command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole",      # No console window
        "--onefile",        # Single executable file
        "--name", "ArchiScraper",
        *icon_arg,
        *add_data_arg,
        "--clean",          # Clean cache before building
        main_script
    ]
    
    print("\n" + "=" * 60)
    print(f"Building ArchiScraper executable for {os_info['name']}...")
    print("=" * 60)
    print(f"\nCommand: {' '.join(cmd)}\n")
    
    # Run PyInstaller
    result = subprocess.run(cmd, cwd=script_dir)
    
    if result.returncode == 0:
        exe_path = os.path.join(script_dir, "dist", os_info["exe_name"])
        print("\n" + "=" * 60)
        print("✓ BUILD SUCCESSFUL!")
        print("=" * 60)
        print(f"\nExecutable location:")
        print(f"  {os_info['exe_description']}")
        if os.path.exists(exe_path):
            print(f"\nFull path: {exe_path}")
        print("\nYou can now distribute this file or upload it to GitHub Releases.")
        return True
    else:
        print("\n✗ Build failed. Check the output above for errors.")
        return False


def main():
    print("=" * 60)
    print("ArchiScraper Build Script (Cross-Platform)")
    print("=" * 60)
    print()
    
    # Step 1: Ensure PyInstaller is installed
    if not check_and_install_pyinstaller():
        sys.exit(1)
    
    # Step 2: Ensure Pillow is installed (for icon processing)
    if not check_and_install_pillow():
        sys.exit(1)
    
    # Step 3: Build the executable
    if not build_executable():
        sys.exit(1)
    
    print("\n✓ All done!")


if __name__ == "__main__":
    main()
