import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="fast-trade-jrmeier",  # Replace with your own username
    version="0.0.1",
    author="Jed Meier",
    author_email="fast_trade@jedm.dev",
    description="A performance focused, extensible backtesting framework for ohlcv data.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/jrmeier/fast-trade",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)
