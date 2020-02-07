# flake8: noqa
"""
This is to convert the large logs with the extra data to since column
smaller logs which are just as accurate and take up much less space.
"""
import zipfile
import os
import csv
import sys


# find the directory with all the run directorys
# traverse the directory
# go in to each directory and grab the logs
# write a new file with the same
# move on to the next file


def standardize_log_files(logs_dir):
    run_dirs = []

    for root, dirs, files in os.walk(logs_dir):
        for name in dirs:
            if "run_" in name:
                full_path = os.path.abspath(os.path.join(root, name))
                run_dirs.append(full_path)

    # now go to each directory and process the logs
    for run_dir in run_dirs:
        process_run_dir(run_dir)


def process_run_dir(run_dir):
    log_files = []
    skip_files = []
    for root, dirs, files in os.walk(run_dir):
        for efile in files:
            if "_log" in efile and efile not in skip_files:
                log_files.append(os.path.abspath(os.path.join(root,efile)))


    for log_file in log_files:
        try:
            process_log_file(log_file, run_dir)
        except Exception as e:
            print(log_file)

def process_log_file(log_file, run_dir):
    # unzip the file
    csv_filename = log_file.split("/")[-1].split(".zip")[0]
    
    csv_path = log_file.split("/")[:-1]
    csv_path = "/".join(csv_path)
    csv_path = f"{csv_path}/{csv_filename}"

    with zipfile.ZipFile(log_file, "r") as zip_file:
        zip_file.extractall(run_dir)
    
    # read the file as csv
    with open(csv_path, "r") as raw_file:
        csv_reader = list(csv.reader(raw_file))
    
    os.remove(csv_path)
    os.remove(log_file)

    header = csv_reader.pop(0)
    new_data = []
    for row in csv_reader:
        action = row[header.index('action')]
        if action == "enter":
            action = "e"
        if action == "exit":
            action = "x"
        if action == "hold":
            action = "h"
        new_data.append(action)
    
    # create a new csv
    with open(csv_path, "w") as new_csv_file:
        csv_writer = csv.writer(new_csv_file)
        csv_writer.writerows(new_data)
    
    # zip the csv
    with zipfile.ZipFile(log_file, "w") as log_zip:
        log_zip.write(
            csv_path, compress_type=zipfile.ZIP_DEFLATED, arcname=csv_filename,
        )

    os.remove(csv_path)

if __name__ == "__main__":
    csv.field_size_limit(sys.maxsize)
    # logs_dir = "/Users/jedmeier/logs/21"
    # standardize_log_files(logs_dir)
    # log_file = "/Users/jedmeier/logs/logs/run_01_03_2020_01_59_08/XEMETH_log.csv.zip"
    # process_log_file(log_file, run_dir)

    run_dirs = [
        "/Users/jedmeier/logs/21/logs/run_01_19_2020_10_36_53",
        "/Users/jedmeier/logs/21/logs/run_01_18_2020_13_08_45",
        "/Users/jedmeier/logs/21/logs/run_01_20_2020_22_55_25",
        "/Users/jedmeier/logs/21/logs/run_01_20_2020_07_44_30",
        "/Users/jedmeier/logs/21/logs/run_01_18_2020_00_32_48",
        "/Users/jedmeier/logs/21/logs/run_01_20_2020_03_26_29",
        "/Users/jedmeier/logs/21/logs/run_01_19_2020_06_09_26",
        "/Users/jedmeier/logs/21/logs/run_01_17_2020_16_16_48",
        "/Users/jedmeier/logs/21/logs/run_01_17_2020_08_05_19",
        "/Users/jedmeier/logs/21/logs/run_01_20_2020_19_14_13"
    ]

    for run_dir in run_dirs:
        process_run_dir(run_dir)