import pathlib
from setuptools import setup, find_packages

HERE = pathlib.Path(__file__).parent

README = (HERE / "README.md").read_text()

setup(
    name="fast-trade",
    version="0.0.01",
    description="Automate and backtest on ohlcv data quickly",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/jrmeier/fast-trade",
    keywords=["backtesting", "fast trade", "ta", "pandas", "finance", "numpy", "analysis", "technical analysis"],
    author="Jed Meier",
    author_email="fast_trade@jedm.dev",
    license="MIT",
    python_requires='>=3',
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
    ],
    packages=find_packages(include=['fast_trade']),
    include_package_data=True,
    install_requires=[
        "finta==0.4.1",
        "numpy==1.18.1",
        "pandas==1.0.1",
        "python-dateutil==2.8.1",
        "pytz==2019.3",
        "six==1.14.0"
        ]
)