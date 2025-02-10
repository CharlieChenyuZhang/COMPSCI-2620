from setuptools import setup, find_packages

setup(
    name="chat-server",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        'pytest',
        'bcrypt'
    ],
)