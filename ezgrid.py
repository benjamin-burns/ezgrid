#!/usr/bin/env python3
from argparse import ArgumentParser
from itertools import product
import os
import json
import subprocess
import petname
from rich.console import Console
from rich.pretty import pprint
from ezgridUtils import multiply_slurm_time

# TODO: tool to quickly run specific ezgrid id or group of ezgrid ids

# Parse command line arguments
parser = ArgumentParser(
    prog="ezgrid",
    description="Grid search utility for SLURM workflows",
    epilog="Developed by Benjamin Burns - 2025"
)
parser.add_argument("jsonFile", type=str, help="Path to ezgrid configuration file")
parser.add_argument("-o", "--overwrite", required=False, action="store_true", help="Enable save overwrite")
parser.add_argument("-s", "--skip", required=False, action="store_true", help="Skip confirmation step")
args = parser.parse_args()

# Check if JSON file exists
if not os.path.exists(args.jsonFile):
    raise ValueError(f"JSON file {args.jsonFile} does not exist")

# Parse JSON
with open(args.jsonFile, 'r') as file:
    parsed = json.load(file)

# Check for essential JSON arguments
assert "gridSearchName" in parsed and parsed["gridSearchName"] is not None, "gridSearchName not provided"
assert "saveDir" in parsed and parsed["saveDir"] is not None, "saveDir not provided"
assert "script" in parsed and parsed["script"] is not None, "script not provided"
assert "hyperparameters" in parsed and len(parsed["hyperparameters"]) > 0, "hyperparameters not provided"
assert "configsPerTask" in parsed and parsed["configsPerTask"] > 0, "configsPerTask not provided"
assert "timePerConfig" in parsed, "timePerConfig not provided"
assert "slurm" in parsed, "slurm not provided" # The user is responsible for ensuring all necessary SLURM arguments are provided

# Check file conflicts
if not os.path.isdir(parsed["saveDir"]):
    raise ValueError(f"Save directory {parsed['saveDir']} does not exist")

saveLoc = os.path.join(parsed["saveDir"], parsed["gridSearchName"])
if not args.overwrite and os.path.isdir(saveLoc):
    raise ValueError(f"Save location {saveLoc} already exists")

if not os.path.exists(parsed["script"]):
    raise ValueError(f"{parsed['script']} not found")

if ("setup" in parsed and parsed["setup"] is not None) and not os.path.exists(parsed["setup"]):
    raise ValueError(f"{parsed['setup']} not found")

if ("wrapup" in parsed and parsed["wrapup"] is not None) and not os.path.exists(parsed["wrapup"]):
    raise ValueError(f"{parsed['wrapup']} not found")

# Create grid search folder
os.makedirs(saveLoc, exist_ok=True)

# Create JSONL file with program configs
combinations = [dict(zip(parsed["hyperparameters"].keys(), values)) for values in product(*parsed["hyperparameters"].values())]
usedNames = set()
for combo in combinations:
    uniqueName = False
    while not uniqueName:
        candidateName = petname.generate(words=3, separator="-")
        if candidateName not in usedNames:
            uniqueName = True
            usedNames.add(candidateName)
    combo["ezgrid_id"] = candidateName

configLoc = os.path.join(saveLoc, "ezgrid_configs.jsonl")
with open(configLoc, "w") as f:
    for item in combinations:
        f.write(json.dumps(item) + "\n")

combinationsDict = {combo["ezgrid_id"]: {k: v for k,v in combo.items() if k != "ezgrid_id"} for combo in combinations}
with open(os.path.join(saveLoc, "ezgrid_ids.json"), "w") as f:
    json.dump(combinationsDict, f, indent=2)

# Create sbatch submission script
sbatchContent = "#!/bin/bash\n"
sbatchContent += f"#SBATCH --time={multiply_slurm_time(parsed['timePerConfig'], parsed['configsPerTask'])}"
if parsed["configsPerTask"] == 1:
    sbatchContent += f"#SBATCH --array=0-{len(combinations) - 1}"
else:
    # TODO
    raise NotImplementedError()
sbatchContent += f"%{parsed['maxSimultaneousTasks']}\n"
for slurmArg, slurmVal in parsed["slurm"].items():
    if slurmArg in ["output", "error"]:
        continue
    sbatchContent += f"#SBATCH --{slurmArg}={slurmVal}\n"
sbatchContent += f"#SBATCH --output=/dev/null\n#SBATCH --error=/dev/null\n"
sbatchContent += f'\nHPARAM_LINE=$(sed -n "$((SLURM_ARRAY_TASK_ID + 1))p" {configLoc})\n\n'
varlist = ""
for jsonArg in combinations[0].keys():
    varlist += f"{jsonArg} "
sbatchContent += f'read {varlist} <<< $(python3 -c "\nimport json, sys\n'
sbatchContent += f"d = json.loads('$HPARAM_LINE')\nprint("
arglist = ""
for jsonArg in combinations[0].keys():
    arglist += f"d['{jsonArg}'], "
arglist = arglist[:-2]
sbatchContent += f'{arglist})\n")\n\n'
configDir = os.path.join(saveLoc, "${ezgrid_id}")
sbatchContent += f"mkdir {configDir}\n"
logDir = os.path.join(configDir, "logs")
sbatchContent += f"mkdir {logDir}\n"
sbatchContent += f"exec > {os.path.join(logDir, 'outputLog')}.out\n"
sbatchContent += f"exec 2> {os.path.join(logDir, 'errorLog')}.err\n\n"
pythonCall = f'python {parsed["script"]}'
for jsonArg in combinations[0].keys():
    if jsonArg == "ezgrid_id" and not parsed["passConfigIdToScript"]:
        continue
    pythonCall += f' --{jsonArg}="${jsonArg}"'
pythonCall += "\n\n"
sbatchContent += pythonCall

with open(f"{parsed['gridSearchName']}.sbatch", "w") as f:
    f.write(sbatchContent)

totalConfigs = 1
for hyper, levels in parsed["hyperparameters"].items():
    totalConfigs *= len(levels)

days, hms = parsed["timePerConfig"].split("-") if "-" in parsed["timePerConfig"] else ("0", parsed["timePerConfig"])
hours, minutes, seconds = map(int, hms.split(":"))
taskTime = int(days) * 24 + hours + minutes / 60 + seconds / 3600
timeEstimate = totalConfigs * taskTime / parsed["maxSimultaneousTasks"]

daysEstimate = timeEstimate // 24
if daysEstimate == 0:
    timeText = ""
elif daysEstimate == 1:
    timeText = "1 day, "
else:
    timeText = f"{daysEstimate} days, "

hoursEstimate = timeEstimate % 24
if hoursEstimate == 0:
    timeText = timeText[:-2]
elif hoursEstimate == 1:
    timeText += "1 hour"
else:
    timeText += f"{hoursEstimate} hours"

console = Console()
console.print("")
console.print("======================", style="bold yellow", justify="center")
console.print("EZ-GRID", style="bold yellow", justify="center")
console.print("======================", style="bold yellow", justify="center")
console.print("")
console.print(f"Preparing to run [bold yellow]{parsed['gridSearchName']}[/] grid search...")

if args.skip:
    console.print("[bold red]Confirmation step skipped[/]")
else:
    console.print("Before we start, let\'s review your configuration. Quit the program at any time during this stage to cancel job submission.")
    console.print("To skip this review step, use the [i blue]--skip[/] option next time you execute EZ-Grid.")
    console.print("")
    console.input("Press enter to continue...")
    console.print("")
    console.print(f"Script to run with various configurations: [bold yellow]{parsed['script']}[/]")
    console.print(f"Number of configurations per task: [bold yellow]{parsed['configsPerTask']}[/]")
    console.print(f"Maximum number of simultaneous tasks: [bold yellow]{parsed['maxSimultaneousTasks']}[/]")
    console.print("")
    console.input("Press enter to continue...")
    console.print("")
    console.print("Review the SLURM settings below:")
    pprint(parsed["slurm"], expand_all=True, console=console)
    console.print("")
    console.input("Press enter to continue...")
    console.print("")
    console.print("Review the hyperparameters below:")
    pprint(parsed["hyperparameters"], expand_all=True, console=console)
    console.print("")
    console.input("Press enter to continue...")
    console.print("")
    console.print(f"Results will be saved to [bold yellow]{parsed['saveDir']}[/]")
    console.print("")
    console.input("Press enter to continue...")
    console.print("")
    console.print(f"You are about to run a grid search for [bold yellow]{totalConfigs}[/] hyperparameter combinations.")
    console.print(f"Ignoring queue time, this grid search has an upper bound of [bold yellow]{timeText}[/].")
    console.print("")
    console.input("[bold red]Press enter to begin the grid search...")
    console.print("")

subprocess.run(["sbatch", f"{parsed['gridSearchName']}.sbatch"])
