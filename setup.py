from setuptools import setup, find_packages

VERSION = '0.7.0'
DESCRIPTION = 'IceDB'
LONG_DESCRIPTION = 'Parquet merge engine'

# Setting up
setup(
    # the name must match the folder name 'verysimplemodule'
    name="icedb",
    version=VERSION,
    author="Dan Goodman",
    author_email="dan@danthegoodman.com",
    description=DESCRIPTION,
    long_description=LONG_DESCRIPTION,
    packages=find_packages(),
    install_requires=[
        "boto3==1.26.151",
        "botocore==1.29.151",
        "duckdb==0.9.2",
        "pyarrow==12.0.1"
    ],
    keywords=['olap', 'icedb', 'data lake', 'parquet', 'data warehouse', 'analytics'],
    classifiers= []
)
