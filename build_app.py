"""
ArchiScraper Build Script

This script builds ArchiScraper into a standalone Windows executable.
It automatically installs PyInstaller if not present and bundles the icon.

Usage:
    python build_app.py

Output:
    dist/ArchiScraper.exe
"""

import subprocess
import sys
import os

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


def build_executable():
    """Build the ArchiScraper executable using PyInstaller."""
    
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
        # Windows uses ; as separator, Unix uses :
        separator = ";" if sys.platform == "win32" else ":"
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
    print("Building ArchiScraper executable...")
    print("=" * 60)
    print(f"\nCommand: {' '.join(cmd)}\n")
    
    # Run PyInstaller
    result = subprocess.run(cmd, cwd=script_dir)
    
    if result.returncode == 0:
        exe_path = os.path.join(script_dir, "dist", "ArchiScraper.exe")
        print("\n" + "=" * 60)
        print("✓ BUILD SUCCESSFUL!")
        print("=" * 60)
        print(f"\nExecutable location:")
        print(f"  {exe_path}")
        print("\nYou can now distribute this file or upload it to GitHub Releases.")
        return True
    else:
        print("\n✗ Build failed. Check the output above for errors.")
        return False


def main():
    print("=" * 60)
    print("ArchiScraper Build Script")
    print("=" * 60)
    print()
    
    # Step 1: Ensure PyInstaller is installed
    if not check_and_install_pyinstaller():
        sys.exit(1)
    
    # Step 2: Build the executable
    if not build_executable():
        sys.exit(1)
    
    print("\n✓ All done!")


if __name__ == "__main__":
    main()
