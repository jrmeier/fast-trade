# read a directly of json files to run the evolver on
import json
import os
from .evolver import run_evolver
# read the job file
ARCHIVE_PATH = os.getenv("ARCHIVE_PATH", "ft_archive")


# run a job file, basically just a list of json files to run the evolver on
def run_job(job_file):
    with open(job_file, "r") as f:
        jobs = json.load(f)

    for job in jobs:
        with open(job["file"], "r") as f:
            job_config = json.load(f)
        run_evolver(job_config)


if __name__ == "__main__":
    job = run_job("./ExampleJobs.json")
    # print(job)
