#!/usr/bin/env python3
from argparse import ArgumentParser
from itertools import product
import os
import sys
import json
import subprocess
from math import ceil
import petname
from rich.console import Console
from rich.pretty import pprint
from ezgridUtils import multiply_slurm_time, get_arguments, submit_with_afterok

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

if "setup" in parsed:
    assert "path" in parsed["setup"] and "execution" in parsed["setup"], "setup missing path or execution"
    if not os.path.exists(parsed["setup"]["path"]):
        raise ValueError(f"Setup script {parsed['setup']['path']} not found")

if "wrapup" in parsed and not os.path.exists(parsed["wrapup"]):
    raise ValueError(f"Wrapup script {parsed['wrapup']} not found")

# Create grid search folder
os.makedirs(saveLoc, exist_ok=True)

# Create JSONL file with program configs
combinations = [dict(zip(parsed["hyperparameters"].keys(), values)) for values in product(*parsed["hyperparameters"].values())]

if "conditional" in parsed and len(parsed["conditional"].keys()) > 0:
    for hyper, conditions in parsed["conditional"].items():
        if len(conditions.keys()) > 0:
            for condition, newHypers in conditions.items():
                if len(newHypers.keys()) > 0:
                    for newHyper, levels in newHypers.items():
                        newCombinations = []
                        assert newHyper not in parsed["hyperparameters"].keys(), f"Cannot override global hyperparameter {newHyper} in {hyper} conditional clause. Remove {newHyper} from the hyperparameter clause to condition it on other hyperparameters"
                        assert len(levels) > 0, f"No values provided for hyperparameter {newHyper} conditioned on {hyper}={condition}"
                        for combo in combinations:
                            if combo[hyper] == condition:
                                for level in levels:
                                    newCombo = combo.copy()
                                    newCombo[newHyper] = level
                                    newCombinations.append(newCombo)
                            else:
                                newCombinations.append(combo)
                        combinations = newCombinations.copy()

usedNames = set()
for combo in combinations:
    uniqueName = False
    while not uniqueName:
        candidateName = petname.generate(words=3, separator="-")
        if candidateName not in usedNames:
            uniqueName = True
            usedNames.add(candidateName)
    combo["ezgrid_id"] = candidateName

for combo in combinations:
    execute = f'python {parsed["script"]} {get_arguments(combo)}'
    if parsed["passConfigIdToScript"]:
        execute += f" --ezgrid_id={combo['ezgrid_id']}"
    combo["ezgrid_execute"] = execute

configLoc = os.path.join(saveLoc, "ezgrid_configs.jsonl")
with open(configLoc, "w") as f:
    for item in combinations:
        f.write(json.dumps(item) + "\n")

combinationsDict = {combo["ezgrid_id"]: {k: v for k,v in combo.items() if k not in ["ezgrid_id", "ezgrid_execute"]} for combo in combinations}
with open(os.path.join(saveLoc, "ezgrid_ids.json"), "w") as f:
    json.dump(combinationsDict, f, indent=2)

# Create sbatch submission script
sbatchContent = "#!/bin/bash\n"
sbatchContent += f"#SBATCH --time={multiply_slurm_time(parsed['timePerConfig'], parsed['configsPerTask'])}\n"
sbatchContent += f"#SBATCH --array=0-{ceil(len(combinations) / parsed['configsPerTask']) - 1}"
sbatchContent += f"%{parsed['maxSimultaneousTasks']}\n"
for slurmArg, slurmVal in parsed["slurm"].items():
    if slurmArg in ["output", "error"]:
        continue
    sbatchContent += f"#SBATCH --{slurmArg}={slurmVal}\n"
sbatchContent += f"#SBATCH --output=/dev/null\n#SBATCH --error=/dev/null\n"
sbatchContent += f'\nCONFIGS_PER_TASK={parsed["configsPerTask"]}\n'
sbatchContent += "START_INDEX=$((SLURM_ARRAY_TASK_ID * CONFIGS_PER_TASK))\nEND_INDEX=$((START_INDEX + CONFIGS_PER_TASK - 1))\n\n"
sbatchContent += "for i in $(seq $START_INDEX $END_INDEX); do\n"
sbatchContent += f'\tHPARAM_LINE=$(sed -n "$((i + 1))p" {configLoc})\n'
sbatchContent += f'\t[ -z "$HPARAM_LINE" ] && break\n\n'
sbatchContent += f'\tread ezgrid_id ezgrid_execute <<< $(python3 -c "\nimport json, sys\n'
sbatchContent += f"d = json.loads('$HPARAM_LINE')\nprint("
arglist = ""
for jsonArg in ["ezgrid_id", "ezgrid_execute"]:
    arglist += f"d['{jsonArg}'], "
arglist = arglist[:-2]
sbatchContent += f'{arglist})\n")\n\n'
configDir = os.path.join(saveLoc, "${ezgrid_id}")
sbatchContent += f"\tmkdir {configDir}\n"
logDir = os.path.join(configDir, "logs")
sbatchContent += f"\tmkdir {logDir}\n"
sbatchContent += f"\texec > {os.path.join(logDir, 'outputLog')}.out\n"
sbatchContent += f"\texec 2> {os.path.join(logDir, 'errorLog')}.err\n\n"
pythonCall = "$ezgrid_execute"
sbatchContent += f'\techo {pythonCall} > {os.path.join(configDir, "ezgridCall.txt")}\n\n'
pythonCall = "\teval " + pythonCall + "\n"
sbatchContent += pythonCall
sbatchContent += "done\n"

with open(f"{parsed['gridSearchName']}.sbatch", "w") as f:
    f.write(sbatchContent)

totalConfigs = len(combinations)
days, hms = parsed["timePerConfig"].split("-") if "-" in parsed["timePerConfig"] else ("0", parsed["timePerConfig"])
hours, minutes, seconds = map(int, hms.split(":"))
configTime = int(days) * 24 + hours + minutes / 60 + seconds / 3600
nTasks = ceil(totalConfigs / parsed["configsPerTask"])
taskTime = configTime * parsed["configsPerTask"]
waves = ceil(nTasks / parsed["maxSimultaneousTasks"])
timeEstimate = waves * taskTime

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
    saveMessage = f"Results will be saved to [bold yellow]{parsed['saveDir']}[/]"
    if args.overwrite:
        saveMessage += "[bold red] with overwrite enabled[/]"
    console.print(saveMessage)
    console.print("")
    console.input("Press enter to continue...")
    console.print("")
    if "setup" in parsed or "wrapup" in parsed:
        if "setup" in parsed:
            console.print(f'The following command will be executed before the grid search: [bold yellow]{parsed["setup"]["execution"]} {parsed["setup"]["path"]}[/]')
        if "wrapup" in parsed:
            console.print(f'The following job will be submitted after the grid search: [bold yellow]{parsed["wrapup"]}')
        console.print("")
        console.input("Press enter to continue...")
        console.print("")
    console.print(f"You are about to run a grid search for [bold yellow]{totalConfigs}[/] hyperparameter combinations.")
    console.print(f"Ignoring queue time, this grid search has an upper bound of [bold yellow]{timeText}[/].")
    console.print("")
    console.input("[bold red]Press enter to begin the grid search...")
    console.print("")

if "setup" in parsed:
    setup = f'{parsed["setup"]["execution"]} {parsed["setup"]["path"]}'
    command = f"bash -c '{setup} && sbatch {parsed['gridSearchName']}.sbatch'"
else:
    command = f"sbatch {parsed['gridSearchName']}.sbatch"

result = subprocess.run(command, shell=True, capture_output=True, text=True)
if result.returncode == 0:
    job_id = result.stdout.split()[-1]
    console.print(f"[bold yellow]EZ-Grid Job {job_id} submitted successfully![/]")
    if "wrapup" in parsed:
        submit_with_afterok(parsed['wrapup'], job_id)
else:
    console.print(f"[bold red]There was an issue submitting this job :([/]")
    sys.exit(1)

# TODO: adjust ids and configs output and their save location, update documentation with file creation and where to expect files to be created
