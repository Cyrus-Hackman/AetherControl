"""
AetherControl Desktop Server
"""
from setuptools import setup, find_packages

setup(
    name="aethercontrol-server",
    version="1.0.0",
    description="AetherControl Remote Desktop Server for Deepin OS",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "PyQt6>=6.6.0",
        "qasync>=0.27.1",
        "msgpack>=1.0.7",
        "cryptography>=41.0.0",
        "zeroconf>=0.128.0",
        "mss>=9.0.1",
        "av>=11.0.0",
        "psutil>=5.9.0",
        "numpy>=1.24.0",
        "Pillow>=10.0.0",
    ],
    extras_require={
        "wayland": ["pipewire-capture"],
        "dbus": ["dbus-python>=1.3.2"],
        "uinput": ["python-uinput>=0.11.2"],
    },
    entry_points={
        "console_scripts": [
            "aethercontrol=aether_server.main:main",
        ],
    },
)
