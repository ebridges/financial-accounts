# Path to the version file
file_path = "version.txt"
VERSION = None
with open(file_path, "r") as file:
    VERSION = file.readline().strip()
if not VERSION:
    raise ValueError(f'{file_path} is empty - no version found.')
