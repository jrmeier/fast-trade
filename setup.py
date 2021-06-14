import pathlib
from setuptools import setup, find_packages

HERE = pathlib.Path(__file__).parent

README = (HERE / "README.md").read_text()

setup(
    name="fast-trade",
    version="0.3.1",
    description="About low code backtesting library utilizing pandas and technical analysis indicators",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/jrmeier/fast-trade",
    py_modules=["fast_trade"],
    keywords=[
        "backtesting",
        "currency",
        "ta",
        "pandas",
        "finance",
        "numpy",
        "analysis",
        "technical analysis",
    ],
    author="Jed Meier",
    author_email="fast_trade@jedm.dev",
    license="GNU AGPLv3",
    python_requires=">=3",
    entry_points={"console_scripts": ["ft = fast_trade.cli:main"]},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Financial and Insurance Industry",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Topic :: Scientific/Engineering :: Mathematics",
        "Topic :: Software Development :: Libraries",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)",
        "Operating System :: OS Independent",
        "Natural Language :: English",
    ],
    packages=find_packages(include=["fast_trade"]),
    include_package_data=True,
    install_requires=[
        "finta >= 1.3",
        "matplotlib >= 3.4.1",
        "requests",
    ],
)
