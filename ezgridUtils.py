import shutil
import subprocess
import os

def multiply_slurm_time(time_str, multiplier):
    from datetime import timedelta

    # Parse time string into components
    if "-" in time_str:
        days_str, hms = time_str.split("-")
        days = int(days_str)
    else:
        hms = time_str
        days = 0

    hours, minutes, seconds = map(int, hms.split(":"))

    # Convert to timedelta
    total = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)

    # Multiply and normalize
    total *= multiplier
    total_seconds = int(total.total_seconds())

    # Break back into SLURM format
    new_days = total_seconds // 86400
    rem = total_seconds % 86400
    new_hours = rem // 3600
    rem %= 3600
    new_minutes = rem // 60
    new_seconds = rem % 60

    return f"{new_days}-{new_hours:02}:{new_minutes:02}:{new_seconds:02}"

def get_arguments(combo):
    return " ".join([f"--{k}={v}" for k, v in combo.items() if k != "ezgrid_id"])

def submit_with_afterok(sbatch_path, job_id):
    temp_path = sbatch_path + ".tmp"
    shutil.copyfile(sbatch_path, temp_path)

    with open(temp_path, 'r') as f:
        lines = f.readlines()

    # Find the end of the #SBATCH block
    insert_index = 0
    for i, line in enumerate(lines):
        if line.startswith("#SBATCH"):
            insert_index = i + 1
        elif line.strip().startswith("#") or line.strip() == "":
            continue
        else:
            break

    # Insert the dependency line within the SBATCH block
    lines.insert(insert_index, f"#SBATCH --dependency=afterok:{job_id}\n")

    with open(temp_path, 'w') as f:
        f.writelines(lines)

    subprocess.run(["sbatch", temp_path], capture_output=True, text=True)
    os.remove(temp_path)
